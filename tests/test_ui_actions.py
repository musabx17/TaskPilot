import sys
from pathlib import Path

# Add project root to sys.path for test discovery
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from database import init_db, clear_all_tasks, load_sample_data
from models import Task, TaskPriority, TaskStatus
from scheduler import TaskScheduler


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_ui_actions.db")
    init_db(db_file)
    return db_file


@pytest.fixture
def scheduler(temp_db):
    return TaskScheduler(db_path=temp_db)


def test_ui_workflow_add_complete_skip_reschedule(scheduler):
    today = "2026-10-24"
    tomorrow = "2026-10-25"

    # 1. ACTION: ADD TASK
    task = Task(
        id="task-hero",
        title="Complete Hackathon Submission",
        description="Verify all test suites and UI styling",
        importance=TaskPriority.CRITICAL,
        estimated_duration=45,
        deadline=today,
        scheduled_date=today,
        status=TaskStatus.PENDING,
    )
    scheduler.add_task(task)

    # Verify task was added
    added = scheduler.get_task("task-hero")
    assert added is not None
    assert added.title == "Complete Hackathon Submission"

    # Generate plan - task should be the first slot
    plan = scheduler.generate_daily_plan(target_date=today, day_start="09:00", day_end="17:00")
    assert len(plan.slots) == 1
    assert plan.slots[0].task.id == "task-hero"
    assert plan.slots[0].start_time == "09:00"

    # Add second task
    task2 = Task(
        id="task-second",
        title="Record Walkthrough Video",
        importance=TaskPriority.HIGH,
        estimated_duration=30,
        deadline=today,
        scheduled_date=today,
    )
    scheduler.add_task(task2)
    plan2 = scheduler.generate_daily_plan(target_date=today, day_start="09:00", day_end="17:00", break_minutes=5)
    assert len(plan2.slots) == 2
    assert plan2.slots[0].task.id == "task-hero"
    assert plan2.slots[1].task.id == "task-second"

    # 2. ACTION: SKIP TASK (First task skipped)
    skip_plan = scheduler.skip_task("task-hero", reason="Postponed to evening", auto_replan=True)
    assert skip_plan is not None
    assert scheduler.get_task("task-hero").status == TaskStatus.SKIPPED
    # Next task should now be pulled to the first slot at 09:00!
    assert len(skip_plan.slots) == 1
    assert skip_plan.slots[0].task.id == "task-second"
    assert skip_plan.slots[0].start_time == "09:00"

    # 3. ACTION: COMPLETE TASK
    comp_plan = scheduler.complete_task("task-second", auto_replan=True)
    assert comp_plan is not None
    assert scheduler.get_task("task-second").status == TaskStatus.COMPLETED
    assert len(comp_plan.slots) == 0

    # 4. ACTION: RESCHEDULE TASK
    resched_plan = scheduler.reschedule_task("task-hero", new_date=tomorrow, new_duration=60, auto_replan=True)
    assert resched_plan is not None
    rescheduled = scheduler.get_task("task-hero")
    assert rescheduled.scheduled_date == tomorrow
    assert rescheduled.estimated_duration == 60
