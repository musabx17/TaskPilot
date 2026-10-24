"""
Database connection, schema migration, and persistence helpers for TaskPilot.
All SQL operations use parameterized queries.
"""

import sqlite3
import os
import uuid
from typing import Generator, Optional, List, Dict, Any
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

from models import Task, TaskPriority, TaskStatus, UserSettings

DEFAULT_DB_PATH = os.getenv("DATABASE_PATH", "taskpilot.db")


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db(db_path: str = DEFAULT_DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initializes tables for tasks, execution logs, and settings with schema migration."""
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        
        # Core tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                deadline TEXT,
                estimated_duration INTEGER DEFAULT 30,
                importance TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL,
                scheduled_date TEXT,
                scheduled_start TEXT,
                scheduled_end TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        # Execute safe column migrations for existing databases
        cursor.execute("PRAGMA table_info(tasks)")
        existing_cols = {row["name"] for row in cursor.fetchall()}
        
        needed_columns = {
            "deadline": "TEXT",
            "estimated_duration": "INTEGER DEFAULT 30",
            "importance": "TEXT DEFAULT 'MEDIUM'",
            "scheduled_date": "TEXT",
            "scheduled_start": "TEXT",
            "scheduled_end": "TEXT",
        }
        for col_name, col_type in needed_columns.items():
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type};")

        # Task transition logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks (id)
            );
        """)

        # User preferences / daily time window table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)


def get_user_settings(db_path: str = DEFAULT_DB_PATH) -> UserSettings:
    """Loads user scheduling preferences from the database."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM user_settings")
        data = {row["key"]: row["value"] for row in cursor.fetchall()}

    return UserSettings(
        day_start_time=data.get("day_start_time", "09:00"),
        day_end_time=data.get("day_end_time", "17:00"),
        break_minutes=int(data.get("break_minutes", 5)),
        auto_replan=data.get("auto_replan", "true").lower() == "true",
    )


def save_user_settings(settings: UserSettings, db_path: str = DEFAULT_DB_PATH) -> None:
    """Saves user scheduling preferences into the database."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)", ("day_start_time", settings.day_start_time))
        cursor.execute("INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)", ("day_end_time", settings.day_end_time))
        cursor.execute("INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)", ("break_minutes", str(settings.break_minutes)))
        cursor.execute("INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)", ("auto_replan", str(settings.auto_replan).lower()))


def clear_all_tasks(db_path: str = DEFAULT_DB_PATH) -> None:
    """Clears all tasks and logs from the database for a clean slate."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM task_logs")
        cursor.execute("DELETE FROM tasks")


def load_sample_data(db_path: str = DEFAULT_DB_PATH) -> int:
    """Seeds the database with realistic sample study/project tasks."""
    init_db(db_path)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    in_three_days = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d")

    samples = [
        Task(
            id=str(uuid.uuid4())[:8],
            title="Complete Hackathon Core Architecture",
            description="Implement SQLite persistence, Pydantic validation, and scheduler engine.",
            deadline=today,
            estimated_duration=90,
            importance=TaskPriority.CRITICAL,
            status=TaskStatus.PENDING,
            scheduled_date=today,
        ),
        Task(
            id=str(uuid.uuid4())[:8],
            title="Review Machine Learning Lecture 5",
            description="Review transformers, attention mechanisms, and take summary notes.",
            deadline=today,
            estimated_duration=60,
            importance=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            scheduled_date=today,
        ),
        Task(
            id=str(uuid.uuid4())[:8],
            title="Algorithm Practice - Dynamic Programming",
            description="Solve 2 LeetCode medium DP problems on knapsack and edit distance.",
            deadline=tomorrow,
            estimated_duration=45,
            importance=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            scheduled_date=today,
        ),
        Task(
            id=str(uuid.uuid4())[:8],
            title="Submit Operating Systems Lab 2",
            description="Verify virtual memory paging tests and push git tag.",
            deadline=today,
            estimated_duration=40,
            importance=TaskPriority.CRITICAL,
            status=TaskStatus.PENDING,
            scheduled_date=today,
        ),
        Task(
            id=str(uuid.uuid4())[:8],
            title="Team Sync & Milestone Demo Recording",
            description="Record a 3-minute video showing the interactive TaskPilot dashboard.",
            deadline=tomorrow,
            estimated_duration=30,
            importance=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            scheduled_date=today,
        ),
        Task(
            id=str(uuid.uuid4())[:8],
            title="Organize Study Notes and Backlog",
            description="Archive completed weekly items and prepare next week syllabus.",
            deadline=in_three_days,
            estimated_duration=30,
            importance=TaskPriority.LOW,
            status=TaskStatus.PENDING,
            scheduled_date=today,
        ),
    ]

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        for task in samples:
            cursor.execute(
                """
                INSERT OR REPLACE INTO tasks (
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
    return len(samples)
