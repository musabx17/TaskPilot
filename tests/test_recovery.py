import sys
from pathlib import Path

# Add project root to sys.path for test discovery
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from database import init_db
from models import Task, TaskStatus, TaskPriority
from scheduler import TaskScheduler


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_recovery.db")
    init_db(db_file)
    return db_file


@pytest.fixture
def scheduler(temp_db):
    return TaskScheduler(db_path=temp_db)


def test_transient_failure_triggers_retry(scheduler):
    task_id = "t-retry"
    task = Task(id=task_id, title="Network call", retry_count=0, max_retries=2)
    scheduler.add_task(task)

    def failing_action():
        raise ConnectionError("connection reset by peer: timeout")

    result = scheduler.execute_task(task_id, failing_action)
    assert result is False

    updated = scheduler.get_task(task_id)
    assert updated.status == TaskStatus.RETRYING
    assert updated.retry_count == 1


def test_exhausted_retries_marks_task_failed(scheduler):
    task_id = "t-exhausted"
    task = Task(id=task_id, title="Failing call", retry_count=2, max_retries=2)
    scheduler.add_task(task)

    def failing_action():
        raise ConnectionError("connection reset by peer: timeout")

    result = scheduler.execute_task(task_id, failing_action)
    assert result is False

    updated = scheduler.get_task(task_id)
    assert updated.status == TaskStatus.FAILED


def test_non_transient_error_marks_failed_immediately(scheduler):
    task_id = "t-syntax"
    task = Task(id=task_id, title="Bad logic", retry_count=0, max_retries=3)
    scheduler.add_task(task)

    def bad_logic_action():
        raise ValueError("Invalid configuration provided")

    result = scheduler.execute_task(task_id, bad_logic_action)
    assert result is False

    updated = scheduler.get_task(task_id)
    assert updated.status == TaskStatus.FAILED


def test_automatic_replanning_on_skip(scheduler):
    today = "2026-10-24"
    task1 = Task(id="s1", title="Task 1", estimated_duration=60, importance=TaskPriority.HIGH, scheduled_date=today)
    task2 = Task(id="s2", title="Task 2", estimated_duration=30, importance=TaskPriority.MEDIUM, scheduled_date=today)

    scheduler.add_task(task1)
    scheduler.add_task(task2)

    # Initial plan
    initial_plan = scheduler.generate_daily_plan(target_date=today, day_start="09:00", day_end="12:00", break_minutes=0)
    assert initial_plan.slots[0].task.id == "s1"
    assert initial_plan.slots[0].start_time == "09:00"
    assert initial_plan.slots[1].task.id == "s2"
    assert initial_plan.slots[1].start_time == "10:00"

    # User skips task 1
    new_plan = scheduler.skip_task("s1", reason="Postponed to weekend", auto_replan=True)
    assert new_plan is not None

    # Task 2 should now be pulled forward to 09:00!
    assert len(new_plan.slots) == 1
    assert new_plan.slots[0].task.id == "s2"
    assert new_plan.slots[0].start_time == "09:00"

    # Verify task 1 status
    assert scheduler.get_task("s1").status == TaskStatus.SKIPPED


def test_reschedule_task_and_replan(scheduler):
    today = "2026-10-24"
    tomorrow = "2026-10-25"
    task = Task(id="r1", title="Reschedule me", estimated_duration=45, scheduled_date=today)
    scheduler.add_task(task)

    # Reschedule without auto-replan leaves it as PENDING
    scheduler.reschedule_task("r1", new_date=tomorrow, new_duration=60, auto_replan=False)
    updated = scheduler.get_task("r1")
    assert updated.scheduled_date == tomorrow
    assert updated.estimated_duration == 60
    assert updated.status == TaskStatus.PENDING

    # Reschedule with auto-replan generates a plan for tomorrow and schedules it
    plan = scheduler.reschedule_task("r1", new_date=tomorrow, new_duration=60, auto_replan=True)
    assert plan is not None
    assert len(plan.slots) == 1
    assert plan.slots[0].task.id == "r1"
    assert scheduler.get_task("r1").status == TaskStatus.SCHEDULED
