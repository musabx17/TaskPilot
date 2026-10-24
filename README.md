# 🧭 TaskPilot

> **Taskforge Hackathon MVP** — An autonomous task scheduler and daily execution engine with deterministic prioritization, collision-free slot allocation, conflict diagnosis, and self-healing replanning.

---

## 🌟 Key Features

1. **Deterministic Prioritization**:
   - Multi-factor ordering engine based on deadline urgency, importance weights, estimated duration (SJF), and stable tie-breaking.
2. **Collision-Free Daily Plan**:
   - Calculates exact, non-overlapping time slots `[start_time, end_time]` honoring custom daily study/work windows (e.g., 09:00 - 17:00) and break buffers.
3. **Zero Silent Drops & Conflict Diagnosis**:
   - Tasks that exceed daily capacity are never silently dropped; they are flagged with explicit capacity conflict breakdowns explaining the duration overrun.
4. **Interactive Task Actions**:
   - **Complete**: Finishes tasks and frees up capacity.
   - **Skip**: Marks tasks skipped and pulls upcoming tasks forward.
   - **Reschedule**: Moves tasks to new dates or adjusts durations with immediate automatic replanning.
5. **Robust SQLite Persistence**:
   - Persists all tasks, execution logs, and user study window preferences across app reruns and browser refreshes with parameterized SQL queries.
6. **Isolated Optional AI Engine (Google Gemini + Local Fallback)**:
   - Uses the official `google-genai` Python SDK to decompose large projects into bite-sized subtasks and suggest priorities with structured Pydantic validation.
   - **Zero API Key Requirement**: Operates 100% offline out of the box using deterministic heuristic rules.
   - **Quota & Error Handling**: Gracefully intercepts free-tier rate limits (15 RPM / 1,500 RPD on `gemini-2.5-flash`), network timeouts, and malformed responses with automatic deterministic fallback.
   - **Strict Scheduler Validation**: AI recommendations never bypass scheduler validation, capacity limits, or collision checks.
7. **Comprehensive Test Suite**:
   - 22 automated tests covering scheduling, deterministic ordering, collision prevention, conflict detection, failure recovery, database persistence, and AI fallback behavior.

---

## 📁 Repository Structure

```
taskpilot/
├── app.py                 # Streamlit web application dashboard with AI Assistant workflow
├── models.py              # Pydantic schemas (Task, DailySchedulePlan, SubTaskItem, AI outputs)
├── scheduler.py           # Core deterministic scheduling, slot allocation & replanning engine
├── database.py            # SQLite schema migration, settings, and parameterized persistence
├── ai_service.py          # Isolated Gemini provider + deterministic heuristic fallback engine
├── requirements.txt       # Project dependencies
├── .env.example           # Environment template (GEMINI_API_KEY, DATABASE_PATH)
├── .gitignore             # Standard git ignore rules
├── README.md              # Project documentation & run guide
└── tests/
    ├── test_scheduler.py  # Prioritization, slot allocation, and conflict tests
    ├── test_recovery.py   # Automatic replanning on skip/delay and recovery tests
    ├── test_persistence.py # SQLite connection persistence and sample data tests
    └── test_ai_service.py # Provider isolation, timeout, 429 quota, and fallback tests
```

---

## 🚀 How to Run the Application

### 1. Activate Environment & Install Dependencies

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)

Copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

*Note: Leaving `GEMINI_API_KEY` blank defaults automatically to the offline deterministic engine.*

### 3. Launch the Streamlit Dashboard

```powershell
streamlit run app.py
```

Open your browser at **http://localhost:8501** to view the interactive dashboard.

---

## 🧪 How to Run Automated Tests

Run the full pytest suite:

```powershell
.\.venv\Scripts\pytest.exe -v
```

All 22 tests will execute covering scheduling, conflict handling, automatic replanning, SQLite persistence, and AI fallback behavior.
