"""
TaskPilot - Autonomous Task Scheduler & Daily Execution Engine
Streamlit Web Application — Senior Product Design & Accessible Frontend Edition
"""

import os
import streamlit as st
import uuid
from datetime import datetime, timezone, date, timedelta
from typing import Optional

from models import Task, TaskPriority, TaskStatus, UserSettings
from database import (
    init_db,
    get_user_settings,
    save_user_settings,
    load_sample_data,
    clear_all_tasks,
)
from scheduler import TaskScheduler
from ai_service import AIService

# Page configuration
st.set_page_config(
    page_title="TaskPilot — Your Daily Planner",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# DESIGN SYSTEM: Dark Navy & Charcoal Workspace with Restrained Indigo Accents
# Strict WCAG AA/AAA Contrast, Visible Focus Rings, Reduced-Motion Support
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Global Reset & Typography */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        color: #f1f5f9;
        -webkit-font-smoothing: antialiased;
    }

    /* Accessibility Focus Rings */
    button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, [tabindex]:focus-visible {
        outline: 2px solid #818cf8 !important;
        outline-offset: 3px !important;
        box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.25) !important;
    }

    /* Reduced Motion Preference */
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
            scroll-behavior: auto !important;
        }
    }

    /* Calm Dark Metric Cards */
    .metric-card {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 12px;
        padding: 18px 20px;
        text-align: left;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        transition: border-color 0.15s ease;
    }
    .metric-card:hover {
        border-color: #374151;
    }
    .metric-card-label {
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94a3b8;
        margin-bottom: 6px;
    }
    .metric-card-value {
        font-size: 1.75rem;
        font-weight: 700;
        color: #f8fafc;
        line-height: 1.2;
    }
    .metric-card-sub {
        font-size: 0.8rem;
        color: #64748b;
        margin-top: 4px;
    }

    /* Next Action Hero Card */
    .next-action-hero {
        background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%);
        border: 1px solid #4338ca;
        border-radius: 14px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 10px 25px -5px rgba(67, 56, 202, 0.25);
    }
    .next-action-tag {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(99, 102, 241, 0.2);
        color: #a5b4fc;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        padding: 4px 10px;
        border-radius: 9999px;
        border: 1px solid rgba(129, 140, 248, 0.3);
        margin-bottom: 12px;
    }

    /* Polished Task Timeline Slot Cards */
    .slot-row {
        background: #111827;
        border: 1px solid #1f2937;
        border-left: 5px solid #6366f1;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 14px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.15);
        transition: transform 0.12s ease, border-color 0.12s ease;
    }
    .slot-row:hover {
        border-color: #374151;
        background: #151e2e;
    }
    .slot-row-critical { border-left-color: #ef4444; }
    .slot-row-high { border-left-color: #f97316; }
    .slot-row-medium { border-left-color: #6366f1; }
    .slot-row-low { border-left-color: #10b981; }

    /* Accessible High-Contrast Badges */
    .badge {
        display: inline-block;
        padding: 3px 9px;
        font-size: 0.72rem;
        font-weight: 600;
        border-radius: 6px;
        letter-spacing: 0.02em;
    }
    .badge-critical { background: #450a0a; color: #fca5a5; border: 1px solid #7f1d1d; }
    .badge-high { background: #431407; color: #fdba74; border: 1px solid #7c2d12; }
    .badge-medium { background: #1e1b4b; color: #c7d2fe; border: 1px solid #3730a3; }
    .badge-low { background: #064e3b; color: #6ee7b7; border: 1px solid #065f46; }

    /* Empty States Styling */
    .empty-state-box {
        background: #0f172a;
        border: 2px dashed #1e293b;
        border-radius: 14px;
        padding: 48px 24px;
        text-align: center;
        margin: 20px 0;
    }
    .empty-state-icon {
        font-size: 2.5rem;
        margin-bottom: 12px;
    }
    .empty-state-title {
        font-size: 1.15rem;
        font-weight: 600;
        color: #f1f5f9;
        margin-bottom: 6px;
    }
    .empty-state-desc {
        font-size: 0.9rem;
        color: #94a3b8;
        max-width: 480px;
        margin: 0 auto 20px auto;
        line-height: 1.5;
    }

    /* Capacity Progress Track */
    .progress-container {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 24px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_services():
    init_db()
    ai_service = AIService()
    scheduler = TaskScheduler(ai_service=ai_service)
    return scheduler, ai_service


scheduler, ai_service = get_services()

# --- SIDEBAR: Workspace Controls ---
with st.sidebar:
    st.markdown("### 🧭 **TaskPilot**")
    st.caption("Your smart daily task planner")
    st.markdown("---")

    # --- AI API KEY SETUP ---
    st.markdown("#### 🤖 **AI Assistant (Optional)**")
    if ai_service.is_ai_configured:
        st.success("🟢 **AI Connected** — Smart features enabled!")
    else:
        st.warning("⚪ **AI not connected** — Basic mode active")

    with st.expander("🔑 Connect AI (Google Gemini)", expanded=not ai_service.is_ai_configured):
        st.caption("Enter your free Gemini API key to enable smart task breakdown and suggestions.")
        st.markdown("[Get a free API key →](https://aistudio.google.com/app/apikey)", unsafe_allow_html=False)
        api_key_input = st.text_input(
            "Gemini API Key",
            type="password",
            placeholder="Paste your API key here...",
            key="gemini_api_key_input",
            help="Your key is used only in this session and never stored permanently.",
        )
        if st.button("✅ Apply API Key", use_container_width=True, key="apply_api_key_btn"):
            if api_key_input.strip():
                os.environ["GEMINI_API_KEY"] = api_key_input.strip()
                get_services.clear()
                st.toast("🔑 API key applied! Reconnecting AI...", icon="🤖")
                st.rerun()
            else:
                st.error("Please enter a valid API key.")

    st.markdown("---")
    st.markdown("#### ⏰ **Work Hours**")
    settings = get_user_settings()

    start_str = st.text_input(
        "Start Time",
        value=settings.day_start_time,
        help="When your work day begins (e.g. 09:00)",
        key="day_start_input",
    )
    end_str = st.text_input(
        "End Time",
        value=settings.day_end_time,
        help="When your work day ends (e.g. 17:00)",
        key="day_end_input",
    )
    break_mins = st.number_input(
        "Break Between Tasks (min)",
        min_value=0,
        max_value=60,
        value=settings.break_minutes,
        step=5,
        help="Short rest gap between tasks",
        key="break_mins_input",
    )
    auto_replan_toggle = st.checkbox(
        "Auto-reschedule on changes",
        value=settings.auto_replan,
        help="Automatically update your plan when you complete or skip tasks",
        key="auto_replan_check",
    )

    if st.button("💾 Save Work Hours", use_container_width=True):
        try:
            datetime.strptime(start_str.strip(), "%H:%M")
            datetime.strptime(end_str.strip(), "%H:%M")
            updated_settings = UserSettings(
                day_start_time=start_str.strip(),
                day_end_time=end_str.strip(),
                break_minutes=int(break_mins),
                auto_replan=auto_replan_toggle,
            )
            save_user_settings(updated_settings)
            st.toast("✅ Work hours saved!", icon="💾")
            st.rerun()
        except ValueError as e:
            st.error(f"Invalid time format. Please use HH:MM (e.g. 09:00)")

    st.markdown("---")
    st.markdown("#### 📦 **Data**")
    col_sample1, col_sample2 = st.columns(2)
    with col_sample1:
        if st.button("✨ Load Examples", use_container_width=True, help="Add example tasks to get started"):
            count = load_sample_data()
            st.toast(f"Loaded {count} example tasks!", icon="✨")
            st.rerun()
    with col_sample2:
        if st.button("🗑️ Clear All", use_container_width=True, help="Delete all tasks and start fresh"):
            clear_all_tasks()
            st.toast("All tasks cleared.", icon="🗑️")
            st.rerun()

    st.markdown("---")
    st.caption("TaskPilot v1.0 • Your daily planner")


# --- MAIN HEADER & DATE CONTROLS ---
col_head1, col_head2 = st.columns([3, 1])
with col_head1:
    st.title("📅 My Daily Plan")
    st.caption("Plan your day, track your progress, and stay on top of your tasks.")

with col_head2:
    selected_date = st.date_input("Planning Date", value=date.today())
    target_date_str = selected_date.strftime("%Y-%m-%d")

# --- ABOUT / PROJECT INFO BANNER ---
with st.expander("ℹ️ About TaskPilot — What is this project?", expanded=False):
    st.markdown("""
    <style>
    .about-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 8px; }
    .about-card {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 18px 20px;
    }
    .about-card h4 { margin: 0 0 10px 0; font-size: 1rem; font-weight: 700; }
    .about-card ul { margin: 0; padding-left: 18px; color: #cbd5e1; font-size: 0.88rem; line-height: 1.7; }
    .about-card p { margin: 0; color: #cbd5e1; font-size: 0.88rem; line-height: 1.7; }
    </style>

    <div style="background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%); border: 1px solid #4338ca;
         border-radius: 14px; padding: 24px 28px; margin-bottom: 20px;">
        <h2 style="margin: 0 0 8px 0; color: #ffffff; font-size: 1.4rem;">🧭 What is TaskPilot?</h2>
        <p style="color: #cbd5e1; font-size: 0.95rem; line-height: 1.7; margin: 0;">
            <strong style="color:#a5b4fc;">TaskPilot</strong> is an AI-powered daily task scheduler built with Python and Streamlit.
            It automatically organises your to-do list into a realistic, time-blocked daily plan — so you always know
            exactly <em>what to work on next</em> and never feel overwhelmed by a long task list.
            It works fully offline and optionally connects to <strong>Google Gemini AI</strong> for smarter
            task breakdown and priority suggestions.
        </p>
    </div>

    <div class="about-grid">
        <div class="about-card">
            <h4 style="color: #86efac;">🎯 Who Is It For?</h4>
            <ul>
                <li>Students managing assignments, labs & exams</li>
                <li>Freelancers juggling multiple client projects</li>
                <li>Professionals who struggle with prioritisation</li>
                <li>Anyone who wants a smarter daily planner</li>
                <li>Teams needing lightweight task coordination</li>
            </ul>
        </div>
        <div class="about-card">
            <h4 style="color: #86efac;">✅ Key Benefits</h4>
            <ul>
                <li>Automatically fills your day — no manual scheduling</li>
                <li>AI breaks big tasks into manageable subtasks</li>
                <li>Conflict detection — warns when day is overloaded</li>
                <li>Auto-replanning when you skip or complete tasks</li>
                <li>Works 100% offline — no internet required</li>
                <li>Clean, simple UI anyone can use in seconds</li>
                <li>Free to use — open source, no subscriptions</li>
            </ul>
        </div>
        <div class="about-card">
            <h4 style="color: #fca5a5;">⚠️ Current Limitations</h4>
            <ul>
                <li>No mobile app — browser only (desktop best)</li>
                <li>AI features need a free Google Gemini API key</li>
                <li>No team collaboration or shared task boards yet</li>
                <li>No calendar sync (Google Calendar, Outlook, etc.)</li>
                <li>No recurring/repeating task support yet</li>
            </ul>
        </div>
        <div class="about-card">
            <h4 style="color: #93c5fd;">🔮 Future Scope</h4>
            <ul>
                <li>📱 Mobile-friendly responsive design</li>
                <li>📆 Google Calendar two-way sync</li>
                <li>👥 Multi-user collaboration & shared boards</li>
                <li>🔔 Push notifications & deadline reminders</li>
                <li>📊 Weekly/monthly productivity analytics</li>
                <li>🗣️ Voice input for hands-free task creation</li>
            </ul>
        </div>
    </div>

    <div style="background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 16px 20px; margin-top: 20px;">
        <p style="color: #94a3b8; font-size: 0.85rem; margin: 0; line-height: 1.6;">
            💡 <strong style="color:#f1f5f9;">Why does this matter?</strong>
            Most people don't fail because they lack motivation — they fail because they don't have a clear,
            realistic plan. TaskPilot solves this by turning a chaotic to-do list into a structured,
            time-aware daily schedule automatically. By combining deterministic scheduling logic with
            optional AI assistance, TaskPilot gives every user — technical or not — a personal productivity
            engine that adapts to their day in real time.
        </p>
    </div>
    """, unsafe_allow_html=True)


# --- GENERATE CURRENT DAILY PLAN ---
current_settings = get_user_settings()
daily_plan = scheduler.generate_daily_plan(
    target_date=target_date_str,
    day_start=current_settings.day_start_time,
    day_end=current_settings.day_end_time,
    break_minutes=current_settings.break_minutes,
    persist_slots=True,
)

all_tasks = scheduler.list_all_tasks()
completed_count = sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED)
scheduled_count = len(daily_plan.slots)
conflict_count = len(daily_plan.conflicts)
total_tasks_count = len(all_tasks)

# --- METRIC CARDS ---
st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

# Completion stats
completion_pct = int((completed_count / total_tasks_count * 100) if total_tasks_count > 0 else 0)
pending_count = sum(1 for t in all_tasks if t.status.value in ("PENDING", "SCHEDULED"))

m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-card-label">✅ Completed</div>
            <div class="metric-card-value" style="color: #34d399;">{completed_count}</div>
            <div class="metric-card-sub">{completion_pct}% of all tasks done</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m2:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-card-label">📋 Remaining</div>
            <div class="metric-card-value" style="color: #818cf8;">{pending_count}</div>
            <div class="metric-card-sub">Tasks still to do</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m3:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-card-label">📅 Scheduled Today</div>
            <div class="metric-card-value">{scheduled_count}</div>
            <div class="metric-card-sub">Tasks on today's plan</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m4:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-card-label">⏱️ Time Left Today</div>
            <div class="metric-card-value" style="color: #f8fafc;">{daily_plan.remaining_minutes}m</div>
            <div class="metric-card-sub">Free time in your day</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m5:
    conflict_color = "#f87171" if conflict_count > 0 else "#34d399"
    conflict_label = f"⚠️ {conflict_count} task(s) don't fit" if conflict_count > 0 else "All tasks scheduled!"
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-card-label">📊 Schedule Status</div>
            <div class="metric-card-value" style="color: {conflict_color}; font-size: 1.1rem;">{conflict_label}</div>
            <div class="metric-card-sub">{'Adjust hours or move tasks' if conflict_count > 0 else 'Looking good!'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

# Overall completion progress bar
if total_tasks_count > 0:
    st.progress(
        completed_count / total_tasks_count,
        text=f"🎯 Overall Progress: {completion_pct}% complete ({completed_count} of {total_tasks_count} tasks done)",
    )
    st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

# Day capacity bar
if daily_plan.total_available_minutes > 0:
    cap_val = min(1.0, daily_plan.total_scheduled_minutes / daily_plan.total_available_minutes)
    cap_pct = int(cap_val * 100)
    st.progress(
        cap_val,
        text=f"⏰ Today's Schedule: {cap_pct}% filled ({daily_plan.total_scheduled_minutes}m of {daily_plan.total_available_minutes}m between {current_settings.day_start_time}–{current_settings.day_end_time})",
    )

# --- WORKLOAD INSIGHTS EXPANDER ---
insights = ai_service.generate_workload_insights(daily_plan)
if insights:
    with st.expander("💡 Tips & Suggestions for Today", expanded=False):
        for insight in insights:
            st.info(f"• {insight}")

# --- CONFLICT NOTIFICATIONS ---
if daily_plan.conflicts:
    st.error(
        f"⚠️ **Schedule Capacity Exceeded ({len(daily_plan.conflicts)} task(s) could not fit today)**\n\n"
        "The following tasks could not fit in today's study window. "
        "TaskPilot will not silently discard them. Review below to adjust duration or extend study hours:"
    )
    for conf in daily_plan.conflicts:
        st.markdown(
            f"- **{conf.task_title}** ({conf.estimated_duration}m, Importance: `{conf.importance.value}`)\n"
            f"  *Reason:* {conf.reason}"
        )


# --- TABS ---
tab_timeline, tab_ai_assist, tab_create, tab_all = st.tabs(
    ["📅 Today's Plan", "🤖 AI Task Helper", "➕ Add New Task", "📋 All My Tasks"]
)


# =========================================================
# TAB 1: DAILY EXECUTION PLAN (NEXT-ACTION HERO & TIMELINE)
# =========================================================
with tab_timeline:
    # 1. NEXT-ACTION AREA (Prominent Focus Hero)
    if daily_plan.slots:
        next_slot = daily_plan.slots[0]
        nt = next_slot.task
        next_imp_class = f"badge-{nt.importance.value.lower()}"

        st.markdown(
            f"""
            <div class="next-action-hero">
                <div class="next-action-tag">⚡ Current Priority Focus</div>
                <h2 style="margin: 0 0 8px 0; font-size: 1.5rem; font-weight: 700; color: #ffffff;">{nt.title}</h2>
                <p style="margin: 0 0 16px 0; color: #cbd5e1; font-size: 0.95rem;">{nt.description or 'No extra notes specified.'}</p>
                <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                    <span style="font-family: monospace; font-weight: 700; font-size: 1.1rem; color: #a5b4fc;">⏱️ {next_slot.start_time} – {next_slot.end_time} ({next_slot.duration_minutes}m)</span>
                    <span class="badge {next_imp_class}">{nt.importance.value}</span>
                    <span style="font-size: 0.85rem; color: #94a3b8;">📅 Due: {nt.deadline or 'Flexible'}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Immediate Next-Action Controls
        btn_c1, btn_c2, btn_c3 = st.columns([1, 1, 2])
        with btn_c1:
            if st.button("✅ Complete Next Task", key=f"hero_done_{nt.id}", type="primary", use_container_width=True):
                scheduler.complete_task(nt.id, auto_replan=current_settings.auto_replan)
                st.toast(f"✅ Completed '{nt.title}'! Schedule updated.", icon="🎉")
                st.rerun()
        with btn_c2:
            if st.button("⏭️ Skip & Pull Next", key=f"hero_skip_{nt.id}", use_container_width=True):
                scheduler.skip_task(nt.id, reason="User skipped from next-action hero", auto_replan=current_settings.auto_replan)
                st.toast(f"⏭️ Skipped '{nt.title}'. Next task pulled forward.", icon="⏩")
                st.rerun()

        st.markdown("<hr style='border-color: #1f2937; margin: 24px 0;'>", unsafe_allow_html=True)

    # 2. SCHEDULE TIMELINE
    st.subheader(f"Schedule for {selected_date.strftime('%A, %B %d %Y')}")

    if not daily_plan.slots:
        # Accessible, polished empty state
        st.markdown(
            """
            <div class="empty-state-box">
                <div class="empty-state-icon">🧭</div>
                <div class="empty-state-title">No tasks scheduled for this day</div>
                <div class="empty-state-desc">
                    Your daily study window is completely open. Add a new task, break down a project with AI, or load sample tasks to kick off your schedule.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            if st.button("✨ Populate with Sample Tasks", key="empty_load_sample", use_container_width=True):
                load_sample_data()
                st.toast("Sample tasks loaded!", icon="✨")
                st.rerun()
        with col_e2:
            if st.button("➕ Create a New Task", key="empty_goto_create", use_container_width=True):
                st.info("Switch to the '➕ Create New Task' tab above to schedule your first item.")
    else:
        st.caption("Tasks are ordered by urgency and importance — most important first:")
        for idx, slot in enumerate(daily_plan.slots, start=1):
            t = slot.task
            imp_class = f"badge-{t.importance.value.lower()}"
            border_class = f"slot-row-{t.importance.value.lower()}"

            with st.container():
                col_time, col_info, col_act = st.columns([2, 5, 3])
                with col_time:
                    st.markdown(f"#### `#{idx}` {slot.start_time} – {slot.end_time}")
                    st.caption(f"⏱️ **{slot.duration_minutes} min** session")

                with col_info:
                    st.markdown(f"**{t.title}**")
                    if t.description:
                        st.write(t.description)
                    deadline_badge = f"📅 Due: {t.deadline}" if t.deadline else "No deadline"
                    st.markdown(
                        f"<span class='badge {imp_class}' aria-label='Importance {t.importance.value}'>{t.importance.value}</span> "
                        f"<span style='font-size: 0.8rem; color: #94a3b8;'>{deadline_badge}</span>",
                        unsafe_allow_html=True,
                    )

                with col_act:
                    b_col1, b_col2, b_col3 = st.columns(3)
                    with b_col1:
                        if st.button("✅ Done", key=f"done_{t.id}", use_container_width=True, help=f"Mark '{t.title}' completed"):
                            scheduler.complete_task(t.id, auto_replan=current_settings.auto_replan)
                            st.toast(f"✅ Completed '{t.title}'!")
                            st.rerun()

                    with b_col2:
                        if st.button("⏭️ Skip", key=f"skip_{t.id}", use_container_width=True, help="Skip task & pull upcoming forward"):
                            scheduler.skip_task(t.id, reason="User skipped from timeline", auto_replan=current_settings.auto_replan)
                            st.toast(f"⏭️ Skipped '{t.title}'. Schedule replanned!", icon="🔄")
                            st.rerun()

                    with b_col3:
                        with st.popover("🔄 Reschedule", use_container_width=True):
                            new_date_val = st.date_input("Move to date", value=date.today() + timedelta(days=1), key=f"pop_date_{t.id}")
                            new_dur_val = st.number_input("Duration (min)", min_value=5, max_value=480, value=t.estimated_duration, step=5, key=f"pop_dur_{t.id}")
                            if st.button("Confirm", key=f"conf_resched_{t.id}"):
                                scheduler.reschedule_task(
                                    t.id,
                                    new_date=new_date_val.strftime("%Y-%m-%d"),
                                    new_duration=int(new_dur_val),
                                    auto_replan=current_settings.auto_replan,
                                )
                                st.toast(f"🔄 Rescheduled '{t.title}' to {new_date_val}!", icon="📅")
                                st.rerun()

                st.markdown("<hr style='border-color: #1f2937; margin: 10px 0;'>", unsafe_allow_html=True)


# =========================================================
# TAB 2: AI ASSISTANT & STRUCTURED BREAKDOWN
# =========================================================
with tab_ai_assist:
    st.subheader("🤖 Break Down a Big Task")
    st.write(
        "Got a large project or assignment? Enter it below and the AI will split it into "
        "smaller, manageable steps that are automatically added to your schedule."
    )

    if ai_service.is_ai_configured:
        st.success("🟢 AI connected — you'll get smart, personalized task breakdowns.")
    else:
        st.info("⚪ AI not connected — using built-in smart breakdown instead. Connect your API key in the sidebar for better results.")

    with st.form("ai_breakdown_form"):
        col_b1, col_b2 = st.columns([3, 1])
        with col_b1:
            complex_title = st.text_input(
                "Large Task Title *",
                placeholder="e.g. Build Machine Learning Pipeline and Evaluation Report",
            )
            complex_desc = st.text_area(
                "Task Context & Goals (optional)",
                placeholder="Key deliverables, datasets, or grading rubrics",
            )
        with col_b2:
            complex_duration = st.number_input(
                "Total Duration (min)",
                min_value=15,
                max_value=720,
                value=90,
                step=15,
            )
            complex_sched_date = st.date_input("Target Date", value=selected_date, key="ai_target_date_input")

        generate_btn = st.form_submit_button("✨ Generate Structured Subtasks", use_container_width=True)

    if generate_btn:
        if not complex_title.strip():
            st.error("Please provide a task title to break down.")
        else:
            with st.spinner("Analyzing and decomposing task..."):
                breakdown = ai_service.breakdown_task(
                    title=complex_title.strip(),
                    description=complex_desc.strip(),
                    total_duration=int(complex_duration),
                )
                st.session_state["pending_breakdown"] = breakdown
                st.session_state["breakdown_target_date"] = complex_sched_date.strftime("%Y-%m-%d")

    if "pending_breakdown" in st.session_state:
        bd = st.session_state["pending_breakdown"]
        bd_date = st.session_state.get("breakdown_target_date", target_date_str)

        st.markdown("---")
        prov_badge = "🟢 AI Generated" if bd.provider_used == "gemini" else "⚪ Auto Generated"
        st.markdown(f"### Suggested Subtasks ({prov_badge})")
        st.info(f"**Strategy:** {bd.explanation}")

        # Render subtasks table
        subtask_data = []
        for i, sub in enumerate(bd.subtasks, start=1):
            subtask_data.append({
                "#": i,
                "Title": sub.title,
                "Duration": f"{sub.estimated_duration} min",
                "Importance": sub.importance.value,
                "Description": sub.description,
            })
        st.table(subtask_data)

        col_accept, col_dismiss = st.columns([2, 1])
        with col_accept:
            if st.button("📥 Confirm & Schedule All Subtasks", use_container_width=True, type="primary"):
                for sub in bd.subtasks:
                    sub_task = Task(
                        id=str(uuid.uuid4())[:8],
                        title=sub.title,
                        description=sub.description,
                        estimated_duration=sub.estimated_duration,
                        importance=sub.importance,
                        status=TaskStatus.PENDING,
                        scheduled_date=bd_date,
                    )
                    scheduler.add_task(sub_task)
                del st.session_state["pending_breakdown"]
                st.toast(f"Scheduled {len(bd.subtasks)} subtasks for {bd_date}!", icon="📥")
                st.rerun()

        with col_dismiss:
            if st.button("Cancel", use_container_width=True):
                del st.session_state["pending_breakdown"]
                st.rerun()


# =========================================================
# TAB 3: CREATE NEW TASK
# =========================================================
with tab_create:
    st.subheader("Add a New Task")
    with st.form("create_task_form", clear_on_submit=True):
        form_title = st.text_input("Task Title *", placeholder="e.g. Prepare Operating Systems Lab report")
        form_desc = st.text_area("Description (optional)", placeholder="Details, requirements, or links")

        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            form_duration = st.number_input(
                "Estimated Duration (minutes) *",
                min_value=5,
                max_value=720,
                value=45,
                step=5,
                help="Enter realistic time required in minutes",
            )
        with col_f2:
            form_importance = st.selectbox(
                "Importance Level *",
                options=[TaskPriority.LOW, TaskPriority.MEDIUM, TaskPriority.HIGH, TaskPriority.CRITICAL],
                index=1,
                format_func=lambda x: f"{x.value} Priority",
            )
        with col_f3:
            enable_deadline = st.checkbox("Set Deadline?", value=True)
            form_deadline = st.date_input("Deadline Date", value=date.today()) if enable_deadline else None

        col_f4, col_f5 = st.columns(2)
        with col_f4:
            form_sched_date = st.date_input("Schedule For Date", value=selected_date)

        submit_btn = st.form_submit_button("🚀 Create & Schedule Task", use_container_width=True)

        if submit_btn:
            clean_title = form_title.strip()
            if not clean_title:
                st.error("Validation error: Task title cannot be empty.")
            else:
                new_task = Task(
                    id=str(uuid.uuid4())[:8],
                    title=clean_title,
                    description=form_desc.strip(),
                    deadline=form_deadline.strftime("%Y-%m-%d") if form_deadline else None,
                    estimated_duration=int(form_duration),
                    importance=form_importance,
                    status=TaskStatus.PENDING,
                    scheduled_date=form_sched_date.strftime("%Y-%m-%d"),
                )
                scheduler.add_task(new_task)
                st.toast(f"Created '{new_task.title}'!", icon="🚀")
                st.rerun()


# =========================================================
# TAB 4: ALL TASKS & BACKLOG MANAGEMENT
# =========================================================
with tab_all:
    st.subheader("All My Tasks")

    col_flt1, col_flt2 = st.columns([2, 3])
    with col_flt1:
        status_filter = st.selectbox(
            "Filter by Status",
            options=["ALL", "PENDING", "SCHEDULED", "COMPLETED", "SKIPPED", "FAILED"],
            index=0,
        )
    with col_flt2:
        search_query = st.text_input("Search tasks by title", placeholder="Filter keywords...")

    filtered_tasks = all_tasks
    if status_filter != "ALL":
        filtered_tasks = [t for t in filtered_tasks if t.status.value == status_filter]
    if search_query.strip():
        q = search_query.strip().lower()
        filtered_tasks = [t for t in filtered_tasks if q in t.title.lower() or (t.description and q in t.description.lower())]

    st.write(f"Showing **{len(filtered_tasks)}** task(s):")

    if not filtered_tasks:
        st.markdown(
            """
            <div class="empty-state-box">
                <div class="empty-state-icon">📋</div>
                <div class="empty-state-title">No matching tasks found</div>
                <div class="empty-state-desc">Try clearing your search query or switching your status filter to 'ALL'.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for t in filtered_tasks:
            status_icon = {"COMPLETED": "✅", "PENDING": "🔵", "SCHEDULED": "📅", "SKIPPED": "⏭️", "FAILED": "❌"}.get(t.status.value, "🔵")
            deadline_info = f" · Due: {t.deadline}" if t.deadline else ""
            with st.expander(f"{status_icon} {t.title} — {t.estimated_duration} min · {t.importance.value} Priority{deadline_info}", expanded=False):
                if t.description:
                    st.markdown(f"**Notes:** {t.description}")

                info_cols = st.columns(3)
                with info_cols[0]:
                    st.markdown(f"📅 **Scheduled:** {t.scheduled_date or 'Not set'}")
                with info_cols[1]:
                    if t.scheduled_start and t.scheduled_end:
                        st.markdown(f"⏰ **Time:** {t.scheduled_start} – {t.scheduled_end}")
                with info_cols[2]:
                    st.markdown(f"🏷️ **Status:** {t.status.value.title()}")

                st.markdown("")
                act_c1, act_c2, act_c3, act_c4 = st.columns(4)
                with act_c1:
                    if t.status != TaskStatus.COMPLETED:
                        if st.button("✅ Mark Done", key=f"all_comp_{t.id}", use_container_width=True):
                            scheduler.complete_task(t.id, auto_replan=current_settings.auto_replan)
                            st.toast(f"Great job! '{t.title}' completed! 🎉")
                            st.rerun()
                with act_c2:
                    if t.status != TaskStatus.PENDING:
                        if st.button("🔄 Undo", key=f"all_pend_{t.id}", use_container_width=True):
                            t.status = TaskStatus.PENDING
                            scheduler.update_task(t)
                            st.toast(f"'{t.title}' moved back to pending.")
                            st.rerun()
                with act_c3:
                    if st.button("⏭️ Skip", key=f"all_skip_{t.id}", use_container_width=True):
                        scheduler.skip_task(t.id, reason="Skipped from task list", auto_replan=current_settings.auto_replan)
                        st.toast(f"Skipped '{t.title}'.")
                        st.rerun()
                with act_c4:
                    if st.button("🗑️ Delete", key=f"all_del_{t.id}", use_container_width=True):
                        scheduler.delete_task(t.id)
                        st.toast("Task deleted.", icon="🗑️")
                        st.rerun()
