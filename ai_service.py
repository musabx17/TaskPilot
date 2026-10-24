"""
AI Service for TaskPilot.
Provides structured LLM provider isolation (Google Gemini) with robust deterministic
fallback for task breakdown, priority recommendations, and failure diagnosis.
Works 100% offline when no API key is provided, and gracefully recovers from
rate limits, timeouts, and malformed outputs.
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from models import (
    TaskPriority,
    DailySchedulePlan,
    SubTaskItem,
    TaskBreakdownResponse,
    PrioritySuggestionResponse,
    TaskBreakdownResult,
    PrioritySuggestionResult,
)

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    @abstractmethod
    def suggest_priority(self, title: str, description: str = "") -> PrioritySuggestionResponse:
        pass

    @abstractmethod
    def breakdown_task(
        self, title: str, description: str = "", total_duration: int = 60
    ) -> TaskBreakdownResponse:
        pass


class DeterministicProvider(LLMProvider):
    """
    100% offline, local heuristic provider.
    Zero external network calls, zero API keys required.
    """

    def suggest_priority(self, title: str, description: str = "") -> PrioritySuggestionResponse:
        combined = f"{title} {description}".lower()
        if any(term in combined for term in ["urgent", "critical", "outage", "emergency", "blocker", "exam", "final"]):
            return PrioritySuggestionResponse(
                priority=TaskPriority.CRITICAL,
                reasoning="Deterministic rule: Contains critical urgency indicators (e.g. outage, exam, blocker).",
                confidence=1.0,
            )
        if any(term in combined for term in ["important", "deadline", "soon", "high", "fix", "submit", "assignment", "lab"]):
            return PrioritySuggestionResponse(
                priority=TaskPriority.HIGH,
                reasoning="Deterministic rule: Contains high-priority deliverables or deadlines.",
                confidence=0.9,
            )
        if any(term in combined for term in ["minor", "cleanup", "refactor", "low", "someday", "optional", "read"]):
            return PrioritySuggestionResponse(
                priority=TaskPriority.LOW,
                reasoning="Deterministic rule: Identified as optional or low-impact task.",
                confidence=0.85,
            )
        return PrioritySuggestionResponse(
            priority=TaskPriority.MEDIUM,
            reasoning="Deterministic rule: Standard operational task without immediate urgency markers.",
            confidence=0.8,
        )

    def breakdown_task(
        self, title: str, description: str = "", total_duration: int = 60
    ) -> TaskBreakdownResponse:
        # Divide into balanced subtasks based on total duration
        part1 = max(15, int(total_duration * 0.25))
        part2 = max(20, int(total_duration * 0.50))
        part3 = max(15, total_duration - (part1 + part2))

        subtasks = [
            SubTaskItem(
                title=f"Plan & Prep: {title[:60]}",
                description="Review requirements, collect inputs, and define completion criteria.",
                estimated_duration=part1,
                importance=TaskPriority.HIGH,
            ),
            SubTaskItem(
                title=f"Core Execution: {title[:60]}",
                description="Execute the primary objective, code implementation, or study deep-work.",
                estimated_duration=part2,
                importance=TaskPriority.HIGH,
            ),
            SubTaskItem(
                title=f"Verification & Wrap-up: {title[:60]}",
                description="Review results, run validation tests, and finalize notes/deliverables.",
                estimated_duration=part3,
                importance=TaskPriority.MEDIUM,
            ),
        ]

        return TaskBreakdownResponse(
            original_task=title,
            explanation="Deterministic decomposition into planning, execution, and verification phases.",
            subtasks=subtasks,
        )


def clean_json_text(raw: str) -> str:
    """Strips markdown code fences and whitespace from raw LLM text."""
    if not raw or not raw.strip():
        raise ValueError("Empty or whitespace-only response received from model")
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


class GeminiProvider(LLMProvider):
    """
    Google Gemini provider using official google-genai SDK.
    Requires GEMINI_API_KEY environment variable.
    Enforces structured Pydantic output schemas.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key or not self.api_key.strip():
            raise ValueError("GEMINI_API_KEY is not configured")

        self.model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key.strip())
        except ImportError as e:
            raise ImportError("google-genai package is not installed. Install via pip install google-genai") from e

    def suggest_priority(self, title: str, description: str = "") -> PrioritySuggestionResponse:
        prompt = (
            f"Analyze this task for prioritization in a daily study/work scheduler:\n"
            f"Title: {title}\n"
            f"Description: {description or 'None'}\n\n"
            f"Return the suggested priority (LOW, MEDIUM, HIGH, CRITICAL), a short 1-sentence reasoning, "
            f"and confidence between 0.0 and 1.0."
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": PrioritySuggestionResponse,
            },
        )

        if hasattr(response, "parsed") and isinstance(response.parsed, PrioritySuggestionResponse):
            return response.parsed
        # Fallback to model validation on raw text if needed
        return PrioritySuggestionResponse.model_validate_json(clean_json_text(response.text or ""))

    def breakdown_task(
        self, title: str, description: str = "", total_duration: int = 60
    ) -> TaskBreakdownResponse:
        prompt = (
            f"Decompose the following task into 2 to 4 actionable, non-overlapping subtasks.\n"
            f"Total target duration: {total_duration} minutes.\n"
            f"Task Title: {title}\n"
            f"Task Description: {description or 'None'}\n\n"
            f"Constraints:\n"
            f"- Each subtask must have a clear title, description, estimated_duration (in minutes, min 5), "
            f"and importance (LOW, MEDIUM, HIGH, CRITICAL).\n"
            f"- The sum of subtask durations should approximately equal {total_duration} minutes.\n"
            f"- Provide a short 1-sentence explanation of the breakdown strategy."
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": TaskBreakdownResponse,
            },
        )

        if hasattr(response, "parsed") and isinstance(response.parsed, TaskBreakdownResponse):
            return response.parsed
        return TaskBreakdownResponse.model_validate_json(clean_json_text(response.text or ""))


class AIService:
    """
    Unified AI service layer with graceful provider isolation and guaranteed fallback.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.deterministic_provider = DeterministicProvider()
        self.gemini_provider: Optional[GeminiProvider] = None
        self.model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        # Attempt to initialize Gemini if key is provided
        raw_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if raw_key and raw_key.strip():
            try:
                self.gemini_provider = GeminiProvider(api_key=raw_key.strip(), model=self.model_name)
            except Exception as e:
                logger.warning("Failed to initialize Gemini provider: %s. Using deterministic fallback.", e)
                self.gemini_provider = None

    @property
    def is_ai_configured(self) -> bool:
        """Returns True if a live hosted LLM provider (Gemini) is available."""
        return self.gemini_provider is not None

    def suggest_priority(self, title: str, description: str = "") -> str:
        """
        Backwards-compatible string priority suggestion for TaskScheduler and UI.
        Guaranteed to return one of: 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'.
        """
        result = self.get_priority_suggestion(title, description)
        return result.priority.value

    def get_priority_suggestion(self, title: str, description: str = "") -> PrioritySuggestionResult:
        """
        Structured priority suggestion with reasoning and provider provenance.
        """
        if self.gemini_provider:
            try:
                resp = self.gemini_provider.suggest_priority(title, description)
                return PrioritySuggestionResult(
                    priority=resp.priority,
                    reasoning=resp.reasoning,
                    confidence=resp.confidence,
                    provider_used="gemini",
                    model_name=self.model_name,
                    is_fallback=False,
                )
            except Exception as e:
                logger.warning("Gemini priority suggestion failed (%s). Falling back to deterministic rule.", e)

        # Deterministic fallback
        resp = self.deterministic_provider.suggest_priority(title, description)
        return PrioritySuggestionResult(
            priority=resp.priority,
            reasoning=resp.reasoning,
            confidence=resp.confidence,
            provider_used="deterministic_fallback",
            model_name="rule-engine-v1",
            is_fallback=True,
        )

    def breakdown_task(
        self, title: str, description: str = "", total_duration: int = 60
    ) -> TaskBreakdownResult:
        """
        Decomposes a task into structured subtasks with validation.
        Always returns validated subtasks, falling back to deterministic breakdown on any API error.
        """
        if self.gemini_provider:
            try:
                resp = self.gemini_provider.breakdown_task(title, description, total_duration)
                # Verify subtask validity
                if resp.subtasks:
                    return TaskBreakdownResult(
                        original_task=resp.original_task,
                        explanation=resp.explanation,
                        subtasks=resp.subtasks,
                        provider_used="gemini",
                        model_name=self.model_name,
                        is_fallback=False,
                    )
            except Exception as e:
                logger.warning("Gemini breakdown failed (%s). Falling back to deterministic decomposition.", e)

        # Deterministic fallback
        resp = self.deterministic_provider.breakdown_task(title, description, total_duration)
        return TaskBreakdownResult(
            original_task=resp.original_task,
            explanation=resp.explanation,
            subtasks=resp.subtasks,
            provider_used="deterministic_fallback",
            model_name="heuristic-decomposer-v1",
            is_fallback=True,
        )

    def analyze_failure(self, task_id: str, error_message: str) -> Dict[str, Any]:
        """
        Diagnose a task execution failure and recommend automatic recovery.
        """
        transient_indicators = ["timeout", "connection reset", "rate limit", "503", "429", "temporary", "retry"]
        is_transient = any(ind in error_message.lower() for ind in transient_indicators)

        return {
            "task_id": task_id,
            "is_transient": is_transient,
            "recommended_action": "RETRY_WITH_BACKOFF" if is_transient else "MANUAL_INTERVENTION",
            "reason": (
                "Transient network/rate-limiting error detected. Safe to automatically retry."
                if is_transient
                else "Non-transient error identified. Recommend manual parameter review."
            ),
        }

    def generate_workload_insights(self, plan: DailySchedulePlan) -> List[str]:
        """
        Actionable productivity advice based on the daily plan capacity.
        """
        insights = []
        utilization_pct = 0
        if plan.total_available_minutes > 0:
            utilization_pct = int((plan.total_scheduled_minutes / plan.total_available_minutes) * 100)

        if utilization_pct > 90:
            insights.append(
                f"High cognitive load detected ({utilization_pct}% capacity used). Consider buffering 15-minute breaks between dense sessions."
            )
        elif utilization_pct == 0:
            insights.append("Your daily study schedule is open. Add or pull pending tasks into today's plan.")
        else:
            insights.append(
                f"Balanced schedule: {plan.total_scheduled_minutes}m allocated across {len(plan.slots)} tasks ({plan.remaining_minutes}m buffer remaining)."
            )

        long_tasks = [slot for slot in plan.slots if slot.duration_minutes >= 90]
        if long_tasks:
            titles = ", ".join([f"'{s.task.title}'" for s in long_tasks[:2]])
            insights.append(f"Extended focus sessions ({titles}): Recommend breaking into 25m Pomodoro intervals or using the AI Task Breakdown tool.")

        if plan.conflicts:
            insights.append(
                f"Attention: {len(plan.conflicts)} tasks could not fit into today's window. Review conflicts or extend your daily window."
            )

        return insights
