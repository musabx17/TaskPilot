import sys
from pathlib import Path

# Add project root to sys.path for test discovery
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import uuid
from database import init_db
from models import Task, TaskPriority, TaskStatus
from scheduler import TaskScheduler


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_scheduler.db")
    init_db(db_file)
    return db_file


@pytest.fixture
def scheduler(temp_db):
    return TaskScheduler(db_path=temp_db)


def test_add_and_get_task(scheduler):
    task_id = str(uuid.uuid4())
    task = Task(
        id=task_id,
        title="Test Task",
        description="Testing scheduler add_task",
        priority=TaskPriority.HIGH,
        estimated_duration=45,
    )
    scheduler.add_task(task)

    retrieved = scheduler.get_task(task_id)
    assert retrieved is not None
    assert retrieved.id == task_id
    assert retrieved.title == "Test Task"
    assert retrieved.priority == TaskPriority.HIGH
    assert retrieved.importance == TaskPriority.HIGH
    assert retrieved.status == TaskStatus.PENDING
    assert retrieved.estimated_duration == 45


def test_list_pending_tasks_order(scheduler):
    low_task = Task(id="t-low", title="Low", priority=TaskPriority.LOW)
    crit_task = Task(id="t-crit", title="Critical", priority=TaskPriority.CRITICAL)
    high_task = Task(id="t-high", title="High", priority=TaskPriority.HIGH)

    scheduler.add_task(low_task)
    scheduler.add_task(crit_task)
    scheduler.add_task(high_task)

    pending = scheduler.list_pending_tasks()
    task_ids = [t.id for t in pending]
    assert task_ids == ["t-crit", "t-high", "t-low"]


def test_execute_task_success(scheduler):
    task_id = "t-success"
    task = Task(id=task_id, title="Success task")
    scheduler.add_task(task)

    ran = False

    def action():
        nonlocal ran
        ran = True

    result = scheduler.execute_task(task_id, action)
    assert result is True
    assert ran is True

    updated_task = scheduler.get_task(task_id)
    assert updated_task.status == TaskStatus.COMPLETED


def test_deterministic_prioritization_with_deadlines(scheduler):
    # Today is 2026-10-24
    today = "2026-10-24"
    tasks = [
        Task(id="1", title="Low Overdue", importance=TaskPriority.LOW, deadline="2026-10-20"),
        Task(id="2", title="Crit Tomorrow", importance=TaskPriority.CRITICAL, deadline="2026-10-25"),
        Task(id="3", title="High Today", importance=TaskPriority.HIGH, deadline="2026-10-24"),
        Task(id="4", title="Crit Today", importance=TaskPriority.CRITICAL, deadline="2026-10-24"),
    ]
    sorted_tasks = scheduler.prioritize_tasks(tasks, target_date=today)
    order = [t.id for t in sorted_tasks]

    # Task 1 is overdue (urgency=0)
    # Tasks 4 and 3 are due today (urgency=1), with 4 (Critical) before 3 (High)
    # Task 2 is future (urgency=2)
    assert order == ["1", "4", "3", "2"]


def test_daily_plan_non_overlapping_slots(scheduler):
    today = "2026-10-24"
    scheduler.add_task(Task(id="t1", title="Task 1", estimated_duration=60, importance=TaskPriority.HIGH, scheduled_date=today))
    scheduler.add_task(Task(id="t2", title="Task 2", estimated_duration=30, importance=TaskPriority.MEDIUM, scheduled_date=today))

    plan = scheduler.generate_daily_plan(
        target_date=today,
        day_start="09:00",
        day_end="12:00",
        break_minutes=10,
        persist_slots=True,
    )

    assert len(plan.slots) == 2
    assert plan.slots[0].start_time == "09:00"
    assert plan.slots[0].end_time == "10:00"
    # Break 10 minutes: 10:00 -> 10:10
    assert plan.slots[1].start_time == "10:10"
    assert plan.slots[1].end_time == "10:40"
    assert plan.total_scheduled_minutes == 90
    assert plan.total_available_minutes == 180  # 3 hours = 180 min
    assert plan.remaining_minutes == 90


def test_conflict_detection_when_study_time_exceeded(scheduler):
    today = "2026-10-24"
    # Available time from 09:00 to 11:00 = 120 minutes
    scheduler.add_task(Task(id="c1", title="Big Task", estimated_duration=90, importance=TaskPriority.CRITICAL, scheduled_date=today))
    scheduler.add_task(Task(id="c2", title="Second Task", estimated_duration=60, importance=TaskPriority.HIGH, scheduled_date=today))

    plan = scheduler.generate_daily_plan(
        target_date=today,
        day_start="09:00",
        day_end="11:00",
        break_minutes=0,
    )

    # c1 fits (09:00 to 10:30, 90 mins).
    # c2 requires 60 mins, but only 30 mins remain. Must NOT be silently discarded!
    assert len(plan.slots) == 1
    assert plan.slots[0].task.id == "c1"
    assert len(plan.conflicts) == 1
    assert plan.conflicts[0].task_id == "c2"
    assert "Requires 60m, but only 30m remain" in plan.conflicts[0].reason
