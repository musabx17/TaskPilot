import sys
from pathlib import Path

# Add project root to sys.path for test discovery
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import uuid
from database import (
    init_db,
    load_sample_data,
    clear_all_tasks,
    get_user_settings,
    save_user_settings,
    get_db,
)
from models import Task, TaskPriority, TaskStatus, UserSettings
from scheduler import TaskScheduler


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_persistence.db")
    init_db(db_file)
    return db_file


def test_persistence_across_connections(temp_db):
    task_id = str(uuid.uuid4())
    # Connection 1: Create scheduler and write task
    scheduler1 = TaskScheduler(db_path=temp_db)
    task = Task(
        id=task_id,
        title="Persist me",
        description="Verify SQLite persistence across connection closes",
        importance=TaskPriority.CRITICAL,
        estimated_duration=50,
        deadline="2026-10-30",
    )
    scheduler1.add_task(task)

    # Connection 2: New fresh scheduler instance pointing to the same SQLite file
    scheduler2 = TaskScheduler(db_path=temp_db)
    loaded = scheduler2.get_task(task_id)

    assert loaded is not None
    assert loaded.id == task_id
    assert loaded.title == "Persist me"
    assert loaded.importance == TaskPriority.CRITICAL
    assert loaded.estimated_duration == 50
    assert loaded.deadline == "2026-10-30"


def test_sample_data_and_clear(temp_db):
    scheduler = TaskScheduler(db_path=temp_db)
    count = load_sample_data(temp_db)
    assert count > 0

    all_tasks = scheduler.list_all_tasks()
    assert len(all_tasks) == count

    clear_all_tasks(temp_db)
    remaining = scheduler.list_all_tasks()
    assert len(remaining) == 0


def test_user_settings_persistence(temp_db):
    settings = UserSettings(
        day_start_time="08:30",
        day_end_time="16:30",
        break_minutes=15,
        auto_replan=True,
    )
    save_user_settings(settings, temp_db)

    loaded = get_user_settings(temp_db)
    assert loaded.day_start_time == "08:30"
    assert loaded.day_end_time == "16:30"
    assert loaded.break_minutes == 15
    assert loaded.auto_replan is True
