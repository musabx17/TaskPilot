import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to sys.path for test discovery
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from pydantic import ValidationError
from database import init_db, get_db
from models import Task, TaskPriority, TaskStatus, UserSettings
from scheduler import TaskScheduler
from ai_service import AIService, clean_json_text


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_qa_security.db")
    init_db(db_file)
    return db_file


@pytest.fixture
def scheduler(temp_db):
    return TaskScheduler(db_path=temp_db)


# =============================================================================
# 1. SQL SAFETY & INJECTION RESILIENCE
# =============================================================================
def test_sql_injection_safety(scheduler, temp_db):
    """Verify that malicious SQL payloads in task titles, descriptions, and IDs are safely parameterized."""
    malicious_title = "'); DROP TABLE tasks; --"
    malicious_id = "sqli-1' OR '1'='1"
    malicious_desc = "Testing SQL injection: ' UNION SELECT * FROM tasks --"

    task = Task(
        id=malicious_id,
        title=malicious_title,
        description=malicious_desc,
        importance=TaskPriority.CRITICAL,
        estimated_duration=30,
    )
    scheduler.add_task(task)

    # Verify task was stored as literal strings
    retrieved = scheduler.get_task(malicious_id)
    assert retrieved is not None
    assert retrieved.title == malicious_title
    assert retrieved.description == malicious_desc

    # Verify tables still exist and are unharmed
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks")
        count = cursor.fetchone()[0]
        assert count == 1


# =============================================================================
# 2. INPUT VALIDATION & BOUNDARY TESTS
# =============================================================================
def test_whitespace_only_title_rejected():
    """Verify that whitespace-only titles are strictly rejected."""
    with pytest.raises(ValueError, match="Task title cannot be empty or purely whitespace"):
        Task(id="bad-1", title="    ", estimated_duration=30)


def test_invalid_duration_boundaries():
    """Verify duration bounds: 5 <= duration <= 1440."""
    with pytest.raises(ValidationError):
        Task(id="bad-2", title="Negative duration", estimated_duration=0)

    with pytest.raises(ValidationError):
        Task(id="bad-3", title="Huge duration", estimated_duration=2000)


def test_user_settings_window_validation():
    """Verify that inverted study window (day_start >= day_end) raises validation error."""
    with pytest.raises(ValueError, match="must be earlier than end time"):
        UserSettings(day_start_time="17:00", day_end_time="09:00")

    with pytest.raises(ValueError, match="must be earlier than end time"):
        UserSettings(day_start_time="12:00", day_end_time="12:00")


# =============================================================================
# 3. MISSED-TASK RECOVERY & FUTURE DATE ISOLATION
# =============================================================================
def test_missed_task_recovery_and_future_isolation(scheduler):
    """
    1. Tasks from yesterday that were missed (PENDING/SCHEDULED) MUST be recovered into today's plan.
    2. Tasks explicitly scheduled for tomorrow MUST NOT be pulled into today's plan.
    """
    today = "2026-10-24"
    yesterday = "2026-10-23"
    tomorrow = "2026-10-25"

    # Task missed from yesterday
    missed_task = Task(
        id="missed-1",
        title="Missed OS Lecture Review",
        estimated_duration=45,
        importance=TaskPriority.HIGH,
        scheduled_date=yesterday,
        status=TaskStatus.SCHEDULED,
    )
    # Task scheduled for today
    today_task = Task(
        id="today-1",
        title="Today Critical Task",
        estimated_duration=60,
        importance=TaskPriority.CRITICAL,
        scheduled_date=today,
    )
    # Task scheduled for tomorrow
    future_task = Task(
        id="future-1",
        title="Future Project Task",
        estimated_duration=90,
        importance=TaskPriority.HIGH,
        scheduled_date=tomorrow,
    )

    scheduler.add_task(missed_task)
    scheduler.add_task(today_task)
    scheduler.add_task(future_task)

    plan = scheduler.generate_daily_plan(
        target_date=today,
        day_start="09:00",
        day_end="17:00",
        break_minutes=5,
    )

    scheduled_ids = [slot.task.id for slot in plan.slots]

    # Missed task from yesterday and today's task are scheduled
    assert "missed-1" in scheduled_ids
    assert "today-1" in scheduled_ids
    # Future task is strictly isolated from today's plan
    assert "future-1" not in scheduled_ids


# =============================================================================
# 4. OVERLAP PREVENTION GUARANTEE
# =============================================================================
def test_non_overlapping_slot_mathematical_guarantee(scheduler):
    """Verify that every consecutive slot satisfies end_time <= start_time of next slot."""
    today = "2026-10-24"
    for i in range(5):
        scheduler.add_task(
            Task(
                id=f"slot-{i}",
                title=f"Task {i}",
                estimated_duration=40,
                importance=TaskPriority.MEDIUM,
                scheduled_date=today,
            )
        )

    plan = scheduler.generate_daily_plan(
        target_date=today,
        day_start="08:00",
        day_end="18:00",
        break_minutes=10,
    )

    assert len(plan.slots) == 5
    for i in range(len(plan.slots) - 1):
        assert plan.slots[i].end_time <= plan.slots[i + 1].start_time


# =============================================================================
# 5. OVERFLOW & ZERO SILENT DROPS
# =============================================================================
def test_zero_silent_task_drops_on_capacity_overflow(scheduler):
    """When tasks exceed window, they must be retained as explicit conflicts."""
    today = "2026-10-24"
    # Total window: 09:00 to 10:00 = 60 minutes
    scheduler.add_task(Task(id="fit-1", title="Fits in 60m", estimated_duration=50, scheduled_date=today))
    scheduler.add_task(Task(id="overflow-1", title="Cannot fit", estimated_duration=40, scheduled_date=today))

    plan = scheduler.generate_daily_plan(
        target_date=today,
        day_start="09:00",
        day_end="10:00",
        break_minutes=0,
    )

    assert len(plan.slots) == 1
    # overflow-1 (40m) has shorter duration than fit-1 (50m), so Shortest Job First prioritizes it
    assert plan.slots[0].task.id == "overflow-1"
    assert len(plan.conflicts) == 1
    assert plan.conflicts[0].task_id == "fit-1"
    assert "Requires 50m, but only 20m remain" in plan.conflicts[0].reason


# =============================================================================
# 6. COMPLETED TASK PERSISTENCE ACROSS RE-PLANS
# =============================================================================
def test_completed_tasks_never_rescheduled(scheduler):
    """Completed tasks must remain completed and never occupy future active slots."""
    today = "2026-10-24"
    t1 = Task(id="done-1", title="Already done", estimated_duration=30, scheduled_date=today)
    scheduler.add_task(t1)
    scheduler.complete_task("done-1", auto_replan=True)

    # Verify status is COMPLETED
    assert scheduler.get_task("done-1").status == TaskStatus.COMPLETED

    # Plan for today should have 0 active slots
    plan = scheduler.generate_daily_plan(target_date=today)
    assert len(plan.slots) == 0


# =============================================================================
# 7. AI SERVICE: MALFORMED RESPONSES & CLEANING
# =============================================================================
def test_clean_json_text_utility():
    """Verify clean_json_text strips markdown fences and whitespace."""
    raw_markdown = "```json\n{\"test\": true}\n```"
    assert clean_json_text(raw_markdown) == "{\"test\": true}"

    raw_generic = "```\n{\"key\": 123}\n```"
    assert clean_json_text(raw_generic) == "{\"key\": 123}"

    with pytest.raises(ValueError, match="Empty or whitespace-only"):
        clean_json_text("   ")


def test_ai_fallback_on_empty_response():
    """When model returns empty response, AIService falls back deterministically."""
    mock_gemini = MagicMock()
    mock_gemini.breakdown_task.side_effect = ValueError("Empty or whitespace-only response received from model")

    service = AIService()
    service.gemini_provider = mock_gemini

    result = service.breakdown_task("Large Assignment", total_duration=90)
    assert result.is_fallback is True
    assert result.provider_used == "deterministic_fallback"
    assert len(result.subtasks) == 3
