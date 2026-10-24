import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to sys.path for test discovery
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from models import (
    Task,
    TaskPriority,
    TaskStatus,
    SubTaskItem,
    TaskBreakdownResponse,
    PrioritySuggestionResponse,
)
from ai_service import AIService, DeterministicProvider, GeminiProvider
from scheduler import TaskScheduler
from database import init_db


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_ai.db")
    init_db(db_file)
    return db_file


@pytest.fixture
def scheduler(temp_db):
    return TaskScheduler(db_path=temp_db)


def test_ai_service_offline_default():
    """Verify that AIService defaults to offline mode when no API key is provided."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        service = AIService()
        assert not service.is_ai_configured
        suggestion = service.get_priority_suggestion("Prepare urgent database fix")
        assert suggestion.is_fallback is True
        assert suggestion.provider_used == "deterministic_fallback"
        assert suggestion.priority == TaskPriority.CRITICAL


def test_deterministic_priority_heuristics():
    """Test all deterministic keyword urgency branches."""
    provider = DeterministicProvider()

    # Outage / Emergency / Exam -> CRITICAL
    crit = provider.suggest_priority("Resolve emergency production outage")
    assert crit.priority == TaskPriority.CRITICAL
    assert "urgent" in crit.reasoning.lower() or "critical" in crit.reasoning.lower()

    # Submit / Assignment / Lab -> HIGH
    high = provider.suggest_priority("Submit Operating Systems Lab")
    assert high.priority == TaskPriority.HIGH

    # Cleanup / Optional / Minor -> LOW
    low = provider.suggest_priority("Optional code cleanup and styling")
    assert low.priority == TaskPriority.LOW

    # Default -> MEDIUM
    med = provider.suggest_priority("Check standard weekly emails")
    assert med.priority == TaskPriority.MEDIUM


def test_deterministic_task_breakdown_pydantic_validation():
    """Verify that deterministic decomposition returns valid SubTaskItems."""
    provider = DeterministicProvider()
    resp = provider.breakdown_task("Build Authentication Microservice", total_duration=90)

    assert isinstance(resp, TaskBreakdownResponse)
    assert len(resp.subtasks) == 3
    # Check that durations sum up approximately to 90
    total = sum(s.estimated_duration for s in resp.subtasks)
    assert total == 90
    for s in resp.subtasks:
        assert isinstance(s, SubTaskItem)
        assert s.estimated_duration >= 5


def test_gemini_missing_credentials_raises_cleanly():
    """GeminiProvider raises ValueError if initialized with empty key."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
            GeminiProvider(api_key="")


def test_gemini_timeout_or_network_error_fallback():
    """When Gemini client raises Timeout or Network error, AIService falls back gracefully."""
    mock_gemini = MagicMock(spec=GeminiProvider)
    mock_gemini.suggest_priority.side_effect = TimeoutError("Connection to Google API timed out after 10s")
    mock_gemini.breakdown_task.side_effect = ConnectionError("503 Service Unavailable")

    service = AIService()
    service.gemini_provider = mock_gemini

    # Priority fallback check
    p_result = service.get_priority_suggestion("Urgent exam preparation")
    assert p_result.is_fallback is True
    assert p_result.provider_used == "deterministic_fallback"
    assert p_result.priority == TaskPriority.CRITICAL

    # Breakdown fallback check
    b_result = service.breakdown_task("Develop Compiler Parser", total_duration=60)
    assert b_result.is_fallback is True
    assert b_result.provider_used == "deterministic_fallback"
    assert len(b_result.subtasks) == 3


def test_gemini_rate_limit_fallback():
    """Simulate 429 quota exceeded error (free tier rate limit) falling back safely."""
    mock_gemini = MagicMock(spec=GeminiProvider)
    mock_gemini.suggest_priority.side_effect = RuntimeError("429 Resource has been exhausted (quota limit reached)")

    service = AIService()
    service.gemini_provider = mock_gemini

    result = service.get_priority_suggestion("Fix login bug")
    assert result.is_fallback is True
    assert result.provider_used == "deterministic_fallback"
    assert result.priority == TaskPriority.HIGH


def test_gemini_malformed_response_fallback():
    """Simulate Gemini returning malformed data or schema mismatch."""
    mock_gemini = MagicMock(spec=GeminiProvider)
    # Returning invalid schema / empty subtasks
    mock_gemini.breakdown_task.side_effect = ValueError("Failed to parse JSON into TaskBreakdownResponse")

    service = AIService()
    service.gemini_provider = mock_gemini

    result = service.breakdown_task("Complex Project", total_duration=80)
    assert result.is_fallback is True
    assert result.provider_used == "deterministic_fallback"
    assert len(result.subtasks) >= 2


def test_ai_subtasks_strict_scheduler_validation(scheduler):
    """
    Ensure AI subtasks cannot bypass scheduler validation:
    They must be instantiated as valid Task models and placed into
    deterministic, collision-free time slots.
    """
    service = AIService()
    breakdown = service.breakdown_task("Data Structures Assignment", total_duration=60)

    today = "2026-10-24"
    # Insert subtasks through scheduler validation
    for sub in breakdown.subtasks:
        task = Task(
            id=f"sub-{sub.title[:10]}",
            title=sub.title,
            description=sub.description,
            estimated_duration=sub.estimated_duration,
            importance=sub.importance,
            status=TaskStatus.PENDING,
            scheduled_date=today,
        )
        scheduler.add_task(task)

    plan = scheduler.generate_daily_plan(
        target_date=today,
        day_start="09:00",
        day_end="12:00",
        break_minutes=5,
    )

    # All subtasks must have valid non-overlapping slots
    assert len(plan.slots) == len(breakdown.subtasks)
    assert plan.slots[0].start_time == "09:00"
    for i in range(len(plan.slots) - 1):
        # End time of slot i + break <= start time of slot i+1
        assert plan.slots[i].end_time <= plan.slots[i + 1].start_time
