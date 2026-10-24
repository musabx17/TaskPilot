"""
Data models and enumerations for TaskPilot.
Includes task schemas, scheduling slots, plan representations, and user settings.
"""

from enum import Enum
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def weight(self) -> int:
        mapping = {
            TaskPriority.LOW: 1,
            TaskPriority.MEDIUM: 2,
            TaskPriority.HIGH: 3,
            TaskPriority.CRITICAL: 4,
        }
        return mapping[self]


# Alias TaskImportance to TaskPriority for terminology compatibility
TaskImportance = TaskPriority


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class Task(BaseModel):
    id: str
    title: str = Field(..., min_length=1)
    description: Optional[str] = ""
    deadline: Optional[str] = None  # Format: YYYY-MM-DD or YYYY-MM-DD HH:MM
    estimated_duration: int = Field(default=30, ge=5, le=1440)  # in minutes
    importance: TaskPriority = TaskPriority.MEDIUM
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    scheduled_date: Optional[str] = None  # Format: YYYY-MM-DD
    scheduled_start: Optional[str] = None  # Format: HH:MM
    scheduled_end: Optional[str] = None  # Format: HH:MM
    retry_count: int = 0
    max_retries: int = 3
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="before")
    @classmethod
    def sync_priority_and_importance(cls, data):
        if isinstance(data, dict):
            # Strip title and ensure it is not purely whitespace
            if "title" in data and isinstance(data["title"], str):
                cleaned = data["title"].strip()
                if not cleaned:
                    raise ValueError("Task title cannot be empty or purely whitespace.")
                data["title"] = cleaned

            # Sync priority and importance if one is provided
            if "priority" in data and "importance" not in data:
                data["importance"] = data["priority"]
            elif "importance" in data and "priority" not in data:
                data["priority"] = data["importance"]
        return data


class TaskLog(BaseModel):
    id: Optional[int] = None
    task_id: str
    status: TaskStatus
    message: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ScheduleConflict(BaseModel):
    task_id: str
    task_title: str
    estimated_duration: int
    importance: TaskPriority
    reason: str


class ScheduledTaskSlot(BaseModel):
    task: Task
    start_time: str  # HH:MM
    end_time: str  # HH:MM
    duration_minutes: int


class DailySchedulePlan(BaseModel):
    date: str  # YYYY-MM-DD
    day_start: str  # HH:MM
    day_end: str  # HH:MM
    total_available_minutes: int
    total_scheduled_minutes: int
    remaining_minutes: int
    slots: List[ScheduledTaskSlot] = []
    conflicts: List[ScheduleConflict] = []


class UserSettings(BaseModel):
    day_start_time: str = "09:00"
    day_end_time: str = "17:00"
    break_minutes: int = 5  # buffer between tasks
    auto_replan: bool = True

    @model_validator(mode="after")
    def validate_study_window(self):
        try:
            h1, m1 = map(int, self.day_start_time.split(":"))
            h2, m2 = map(int, self.day_end_time.split(":"))
            start_m = h1 * 60 + m1
            end_m = h2 * 60 + m2
            if not (0 <= start_m < 1440 and 0 <= end_m <= 1440):
                raise ValueError("Times must be valid 24h format between 00:00 and 24:00")
            if start_m >= end_m:
                raise ValueError(
                    f"Start time ({self.day_start_time}) must be earlier than end time ({self.day_end_time})"
                )
        except ValueError as e:
            raise ValueError(f"Invalid study window configuration: {e}")
        return self


# --- Structured AI Models ---
class SubTaskItem(BaseModel):
    title: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = ""
    estimated_duration: int = Field(default=30, ge=5, le=480)
    importance: TaskPriority = TaskPriority.MEDIUM


class TaskBreakdownResponse(BaseModel):
    original_task: str
    explanation: str
    subtasks: List[SubTaskItem]


class PrioritySuggestionResponse(BaseModel):
    priority: TaskPriority
    reasoning: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class TaskBreakdownResult(BaseModel):
    original_task: str
    explanation: str
    subtasks: List[SubTaskItem]
    provider_used: str  # "gemini" or "deterministic_fallback"
    model_name: Optional[str] = None
    is_fallback: bool = False


class PrioritySuggestionResult(BaseModel):
    priority: TaskPriority
    reasoning: str
    confidence: float = 1.0
    provider_used: str  # "gemini" or "deterministic_fallback"
    model_name: Optional[str] = None
    is_fallback: bool = False

