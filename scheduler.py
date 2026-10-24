"""
Task scheduler, deterministic prioritization engine, and daily plan optimizer for TaskPilot.
Includes automatic replanning on skip/delay, non-overlapping slot allocation,
and conflict detection when tasks exceed study time.
"""

from typing import List, Optional, Callable, Dict, Any, Tuple
from datetime import datetime, timezone, date
from models import (
    Task,
    TaskStatus,
    TaskPriority,
    DailySchedulePlan,
    ScheduledTaskSlot,
    ScheduleConflict,
    UserSettings,
)
from database import get_db, init_db, get_user_settings
from ai_service import AIService


def time_to_minutes(time_str: str) -> int:
    """Converts HH:MM string to minutes from midnight."""
    h, m = map(int, time_str.split(":"))
    return h * 60 + m


def minutes_to_time(minutes: int) -> str:
    """Converts minutes from midnight to HH:MM format."""
    h = (minutes // 60) % 24
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


class TaskScheduler:
    def __init__(self, db_path: Optional[str] = None, ai_service: Optional[AIService] = None):
        self.db_path = db_path
        self.ai_service = ai_service or AIService()
        init_db(self.db_path) if self.db_path else init_db()

    def _db_kwargs(self) -> Dict[str, Any]:
        return {"db_path": self.db_path} if self.db_path else {}

    def add_task(self, task: Task) -> Task:
        """Persists a new task into SQLite."""
        with get_db(**self._db_kwargs()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tasks (
                    id, title, description, deadline, estimated_duration,
                    importance, priority, status, scheduled_date, scheduled_start,
                    scheduled_end, retry_count, max_retries, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.title,
                    task.description,
                    task.deadline,
                    task.estimated_duration,
                    task.importance.value,
                    task.priority.value,
                    task.status.value,
                    task.scheduled_date,
                    task.scheduled_start,
                    task.scheduled_end,
                    task.retry_count,
                    task.max_retries,
                    task.created_at,
                    task.updated_at,
                ),
            )
            # Log creation
            cursor.execute(
                "INSERT INTO task_logs (task_id, status, message, timestamp) VALUES (?, ?, ?, ?)",
                (task.id, task.status.value, "Task created", task.created_at),
            )
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieves a single task by its unique ID."""
        with get_db(**self._db_kwargs()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return Task(**dict(row))

    def update_task(self, task: Task) -> Task:
        """Updates all mutable fields of an existing task."""
        now = datetime.now(timezone.utc).isoformat()
        with get_db(**self._db_kwargs()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tasks SET
                    title = ?, description = ?, deadline = ?, estimated_duration = ?,
                    importance = ?, priority = ?, status = ?, scheduled_date = ?,
                    scheduled_start = ?, scheduled_end = ?, retry_count = ?,
                    max_retries = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    task.title,
                    task.description,
                    task.deadline,
                    task.estimated_duration,
                    task.importance.value,
                    task.priority.value,
                    task.status.value,
                    task.scheduled_date,
                    task.scheduled_start,
                    task.scheduled_end,
                    task.retry_count,
                    task.max_retries,
                    now,
                    task.id,
                ),
            )
        return task

    def delete_task(self, task_id: str) -> bool:
        """Deletes a task and its associated audit logs."""
        with get_db(**self._db_kwargs()) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM task_logs WHERE task_id = ?", (task_id,))
            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return cursor.rowcount > 0

    def list_all_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        """Retrieves all tasks, optionally filtered by status."""
        with get_db(**self._db_kwargs()) as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC", (status.value,))
            else:
                cursor.execute("SELECT * FROM tasks ORDER BY created_at DESC")
            return [Task(**dict(row)) for row in cursor.fetchall()]

    def list_pending_tasks(self) -> List[Task]:
        """Lists pending or retrying tasks ordered deterministically by priority."""
        with get_db(**self._db_kwargs()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM tasks
                WHERE status IN (?, ?)
                ORDER BY
                    CASE priority
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        ELSE 4
                    END ASC,
                    created_at ASC
                """,
                (TaskStatus.PENDING.value, TaskStatus.RETRYING.value),
            )
            return [Task(**dict(row)) for row in cursor.fetchall()]

    def prioritize_tasks(self, tasks: List[Task], target_date: str) -> List[Task]:
        """
        Deterministic prioritization algorithm:
        Sort Key Tuple:
        1. Urgency bucket: Overdue (0), Due Today (1), Due Tomorrow (2), Future (3), No Deadline (4)
        2. Inverted Importance Weight: Critical (-4), High (-3), Medium (-2), Low (-1)
        3. Estimated Duration: Shorter tasks break ties (Shortest Job First)
        4. Task Title & ID: Stable alphabetical tie-breakers
        """
        def get_sort_key(task: Task) -> Tuple[int, int, int, str, str]:
            # 1. Urgency based on deadline
            if task.deadline and task.deadline.strip():
                try:
                    deadline_date = task.deadline.strip().split()[0]
                    if deadline_date < target_date:
                        urgency = 0  # Overdue
                    elif deadline_date == target_date:
                        urgency = 1  # Due today
                    else:
                        urgency = 2  # Future deadline
                except Exception:
                    urgency = 3
            else:
                urgency = 4  # No deadline specified

            # 2. Importance weight
            imp_weight = -task.importance.weight

            # 3. Estimated duration (SJF)
            duration = task.estimated_duration

            # 4 & 5. Deterministic tie-breaker
            return (urgency, imp_weight, duration, task.title, task.id)

        return sorted(tasks, key=get_sort_key)

    def generate_daily_plan(
        self,
        target_date: Optional[str] = None,
        day_start: Optional[str] = None,
        day_end: Optional[str] = None,
        break_minutes: Optional[int] = None,
        persist_slots: bool = True,
    ) -> DailySchedulePlan:
        """
        Generates a non-overlapping daily schedule.
        Allocates tasks within study hours and reports explicit conflicts when tasks cannot fit.
        """
        settings = get_user_settings(self.db_path) if self.db_path else get_user_settings()
        target_date = target_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_start = day_start or settings.day_start_time
        day_end = day_end or settings.day_end_time
        break_minutes = break_minutes if break_minutes is not None else settings.break_minutes

        start_min = time_to_minutes(day_start)
        end_min = time_to_minutes(day_end)
        total_available = max(0, end_min - start_min)

        # Retrieve tasks eligible for planning on this date:
        # Includes tasks scheduled for today, missed/overdue tasks from previous days,
        # or unassigned backlog tasks. Excludes tasks scheduled for future dates.
        with get_db(**self._db_kwargs()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM tasks
                WHERE status IN (?, ?, ?)
                  AND (
                      (scheduled_date IS NOT NULL AND scheduled_date <= ?)
                      OR (scheduled_date IS NULL)
                  )
                """,
                (
                    TaskStatus.PENDING.value,
                    TaskStatus.SCHEDULED.value,
                    TaskStatus.RETRYING.value,
                    target_date,
                ),
            )
            candidates = [Task(**dict(row)) for row in cursor.fetchall()]

        sorted_candidates = self.prioritize_tasks(candidates, target_date)

        slots: List[ScheduledTaskSlot] = []
        conflicts: List[ScheduleConflict] = []

        # Guard against zero or inverted study window
        if end_min <= start_min:
            for task in sorted_candidates:
                conflicts.append(
                    ScheduleConflict(
                        task_id=task.id,
                        task_title=task.title,
                        estimated_duration=task.estimated_duration,
                        importance=task.importance,
                        reason=f"Invalid daily study window ({day_start} - {day_end}). End time must be after start time.",
                    )
                )
            return DailySchedulePlan(
                date=target_date,
                day_start=day_start,
                day_end=day_end,
                total_available_minutes=0,
                total_scheduled_minutes=0,
                remaining_minutes=0,
                slots=[],
                conflicts=conflicts,
            )

        current_min = start_min
        total_scheduled = 0

        for task in sorted_candidates:
            duration = task.estimated_duration
            if current_min + duration <= end_min:
                slot_start = minutes_to_time(current_min)
                slot_end = minutes_to_time(current_min + duration)

                # Update in-memory task
                task.scheduled_date = target_date
                task.scheduled_start = slot_start
                task.scheduled_end = slot_end
                task.status = TaskStatus.SCHEDULED

                slots.append(
                    ScheduledTaskSlot(
                        task=task,
                        start_time=slot_start,
                        end_time=slot_end,
                        duration_minutes=duration,
                    )
                )

                if persist_slots:
                    self.update_task(task)

                current_min += duration + break_minutes
                total_scheduled += duration
            else:
                remaining_in_window = max(0, end_min - current_min)
                excess = duration - remaining_in_window
                conflicts.append(
                    ScheduleConflict(
                        task_id=task.id,
                        task_title=task.title,
                        estimated_duration=duration,
                        importance=task.importance,
                        reason=(
                            f"Requires {duration}m, but only {remaining_in_window}m remain in study window "
                            f"({day_start} - {day_end}). Exceeds daily capacity by {excess}m."
                        ),
                    )
                )

        remaining_minutes = max(0, total_available - total_scheduled)
        return DailySchedulePlan(
            date=target_date,
            day_start=day_start,
            day_end=day_end,
            total_available_minutes=total_available,
            total_scheduled_minutes=total_scheduled,
            remaining_minutes=remaining_minutes,
            slots=slots,
            conflicts=conflicts,
        )

    def complete_task(self, task_id: str, auto_replan: bool = True) -> Optional[DailySchedulePlan]:
        """Marks a task as completed and automatically replans remaining tasks."""
        task = self.get_task(task_id)
        if not task:
            return None

        self.update_task_status(task_id, TaskStatus.COMPLETED, "Task completed by user")
        if auto_replan:
            target_date = task.scheduled_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return self.generate_daily_plan(target_date=target_date)
        return None

    def skip_task(self, task_id: str, reason: str = "User skipped", auto_replan: bool = True) -> Optional[DailySchedulePlan]:
        """Skips a task and replans to pull upcoming tasks forward into the freed slot."""
        task = self.get_task(task_id)
        if not task:
            return None

        self.update_task_status(task_id, TaskStatus.SKIPPED, f"Skipped: {reason}")
        if auto_replan:
            target_date = task.scheduled_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return self.generate_daily_plan(target_date=target_date)
        return None

    def reschedule_task(
        self,
        task_id: str,
        new_date: Optional[str] = None,
        new_duration: Optional[int] = None,
        auto_replan: bool = True,
    ) -> Optional[DailySchedulePlan]:
        """Reschedules a task with updated date or duration, triggering automatic replanning."""
        task = self.get_task(task_id)
        if not task:
            return None

        if new_date:
            task.scheduled_date = new_date
        if new_duration:
            task.estimated_duration = new_duration

        task.status = TaskStatus.PENDING
        task.scheduled_start = None
        task.scheduled_end = None
        self.update_task(task)
        self.update_task_status(task_id, TaskStatus.PENDING, f"Rescheduled to {new_date or task.scheduled_date}")

        if auto_replan:
            target_date = new_date or task.scheduled_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return self.generate_daily_plan(target_date=target_date)
        return None

    def update_task_status(self, task_id: str, status: TaskStatus, message: Optional[str] = None) -> None:
        """Updates task status in SQLite and writes an audit log entry."""
        now = datetime.now(timezone.utc).isoformat()
        with get_db(**self._db_kwargs()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now, task_id),
            )
            cursor.execute(
                "INSERT INTO task_logs (task_id, status, message, timestamp) VALUES (?, ?, ?, ?)",
                (task_id, status.value, message, now),
            )

    def execute_task(self, task_id: str, action: Callable[[], Any]) -> bool:
        """Executes a task handler with built-in recovery and AI-assisted analysis on failure."""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        self.update_task_status(task_id, TaskStatus.RUNNING, "Task execution started")
        try:
            action()
            self.update_task_status(task_id, TaskStatus.COMPLETED, "Task completed successfully")
            return True
        except Exception as exc:
            return self.handle_failure(task, str(exc))

    def handle_failure(self, task: Task, error_message: str) -> bool:
        """Handles task execution failure and decides whether to retry or mark failed."""
        analysis = self.ai_service.analyze_failure(task.id, error_message)
        now = datetime.now(timezone.utc).isoformat()

        if task.retry_count < task.max_retries and analysis["recommended_action"] == "RETRY_WITH_BACKOFF":
            new_retry_count = task.retry_count + 1
            with get_db(**self._db_kwargs()) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE tasks SET status = ?, retry_count = ?, updated_at = ? WHERE id = ?",
                    (TaskStatus.RETRYING.value, new_retry_count, now, task.id),
                )
                cursor.execute(
                    "INSERT INTO task_logs (task_id, status, message, timestamp) VALUES (?, ?, ?, ?)",
                    (task.id, TaskStatus.RETRYING.value, f"Retry attempt {new_retry_count}: {error_message}", now),
                )
            return False
        else:
            self.update_task_status(task.id, TaskStatus.FAILED, f"Failed: {error_message}")
            return False
