# Steps to run:
# 1. source .venv/bin/activate #تفعّيل البيئة الافتراضية 
# 2. pip install -r requirements.txt #تثبيت المتطلبات
# 3. pip show streamlit #للتحقق من تثبيت streamlit
# 4. streamlit run app.py --server.port 8501 --server.address 0.0.0.0 #تشغيل التطبيق 
# --------------------------------------------------------

# Imports
import sqlite3
import pandas as pd
import streamlit as st
import json
from datetime import datetime, timedelta
from smart_scheduler.models import Task, CalendarSlot
from smart_scheduler.scheduler import Scheduler, Event
from smart_scheduler.db_utils import insert_task
from dateutil import parser 


st.set_page_config(page_title="Smart Scheduler Preview", layout="wide")
st.title("Smart Scheduling — Streamlit + FullCalendar prototype")

# --- Sidebar controls ---
st.sidebar.header("Window & Actions")
today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
default_start = today + timedelta(hours=8)
default_end = today + timedelta(days=2, hours=20)

window_start = st.sidebar.date_input("Window start (date)", value=default_start.date())
start_time = st.sidebar.time_input("Window start (time)", value=default_start.time())
window_end = st.sidebar.date_input("Window end (date)", value=default_end.date())
end_time = st.sidebar.time_input("Window end (time)", value=default_end.time())

# combine date+time into datetimes
ws = datetime.combine(window_start, start_time)
we = datetime.combine(window_end, end_time)

st.sidebar.write(f"Scheduling window: **{ws}** → **{we}**")

# --- Task input form ---
st.sidebar.markdown("### ✏️ Add a new task manually")

with st.sidebar.form("add_task_form"):
    task_title = st.text_input("Task title", placeholder="e.g., Study AI course")
    duration_hours = st.number_input("Duration (hours)", min_value=0.5, step=0.5)
    priority = st.selectbox("Priority", ["Low", "Medium", "High"])
    recurring = st.selectbox("Recurring", [None, "daily", "weekly", "monthly"])
    preferred_time = st.selectbox("Preferred time", [None, "morning", "afternoon", "evening"])
    task_date = st.date_input("Task start date", value=ws.date())
    task_time = st.time_input("Task start time", value=ws.time())
    allow_split = st.checkbox("Allow split task?", value=True)

    has_deadline = st.checkbox("Add a deadline?", value=False)
    if has_deadline:
        deadline_date = st.date_input("Deadline date", value=ws.date())
        deadline_time = st.time_input("Deadline time", value=ws.time())
    else:
        deadline_date = None
        deadline_time = None

    submitted = st.form_submit_button("➕ Add Task")

# --- ensure session keys exist
if "tasks" not in st.session_state:
    st.session_state["tasks"] = []
if "busy_events" not in st.session_state:
    st.session_state["busy_events"] = []

# def load_tasks_from_db():
#     conn = sqlite3.connect("smart_scheduler.db")
#     cur = conn.cursor()
#     cur.execute("SELECT id, title, start_time, end_time, duration_min, priority, deadline, recurring, preferred_time, allow_split FROM tasks")
#     rows = cur.fetchall()
#     conn.close()

#     tasks = []
#     for row in rows:
#         tasks.append(Task(
#             id=row[0], title=row[1], start_time=row[2], end_time=row[3],
#             duration_min=row[4], priority=row[5], deadline=row[6],
#             recurring=row[7], preferred_time=row[8], allow_split=row[9]
#         ))
#     return tasks

# --- handle submit ---
if submitted:
    title = task_title.strip()
    duration_min = int(duration_hours * 60)
    start_dt = datetime.combine(task_date, task_time)
    end_dt = start_dt + timedelta(minutes=duration_min)
    deadline = datetime.combine(deadline_date, deadline_time) if has_deadline else None

    new_task = Task(
        id=None,
        title=title,
        priority=priority,
        duration_min=duration_min,
        deadline=deadline,
        recurring=recurring,
        preferred_time=preferred_time,
        allow_split=allow_split,
        start_time=start_dt,
        end_time=end_dt
    )

    # --- AI Conflict Detection ---
    conn = sqlite3.connect("smart_scheduler.db")
    cur = conn.cursor()
    cur.execute("SELECT title, start_time, end_time FROM tasks")
    existing_tasks = cur.fetchall()
    conn.close()

    conflicts = []
    parsed_tasks = []

    for title_exist, start_exist, end_exist in existing_tasks:
        if not start_exist or not end_exist:
            continue
        try:
            start_exist_dt = parser.parse(str(start_exist))
            end_exist_dt = parser.parse(str(end_exist))
            parsed_tasks.append((title_exist, start_exist_dt, end_exist_dt))
        except Exception as e:
            print(f"⚠️ خطأ في قراءة التاريخ: {e}")
            continue

        # ✅ التحقق من وجود تداخل فعلي
        if (start_dt < end_exist_dt) and (end_dt > start_exist_dt):
            conflicts.append((title_exist, start_exist_dt, end_exist_dt))

    # --- 🧠 مرحلة الذكاء الصناعي واقتراح الحلول ---
    if conflicts:
        st.error("❌ يوجد تداخل مع مهام أخرى:")
        for c in conflicts:
            st.write(f"- {c[0]} ({c[1].strftime('%H:%M')} → {c[2].strftime('%H:%M')})")

        st.markdown("### 🤖 مقترحات ذكية للجدولة:")

        # 🧩 اقتراح 1: إيجاد أول وقت فاضي يناسب مدة المهمة
        parsed_tasks.sort(key=lambda x: x[1])  # ترتيب المهام حسب البداية
        free_slot = None
        for i in range(len(parsed_tasks) - 1):
            current_end = parsed_tasks[i][2]
            next_start = parsed_tasks[i + 1][1]
            gap = (next_start - current_end).total_seconds() / 60
            if gap >= duration_min + 10:  # فجوة كافية + 10 دقائق راحة
                free_slot = (current_end + timedelta(minutes=10), current_end + timedelta(minutes=10 + duration_min))
                break

        # fallback: بعد آخر مهمة لو مفيش فجوة مناسبة
        if not free_slot:
            latest_end = max(c[2] for c in parsed_tasks)
            free_slot = (latest_end + timedelta(minutes=10), latest_end + timedelta(minutes=10 + duration_min))

        suggestion_1_start, suggestion_1_end = free_slot
        st.info(f"🕓 اقتراح 1: وقت فاضي — {suggestion_1_start.strftime('%H:%M')} → {suggestion_1_end.strftime('%H:%M')}")

        # 🌅 اقتراح 2: في الفترة المفضلة للمستخدم
        suggestion_2 = None
        if preferred_time:
            base_date = datetime.combine(task_date, datetime.min.time())
            if preferred_time == "morning":
                pref_start = base_date.replace(hour=8)
            elif preferred_time == "afternoon":
                pref_start = base_date.replace(hour=13)
            else:
                pref_start = base_date.replace(hour=18)
            suggestion_2 = (pref_start, pref_start + timedelta(minutes=duration_min))
            st.info(f"🌅 اقتراح 2: فترة {preferred_time} — {suggestion_2[0].strftime('%H:%M')} → {suggestion_2[1].strftime('%H:%M')}")

        # 🧩 اقتراح 3: تقسيم المهمة
        if allow_split and duration_min > 60:
            part1 = duration_min // 2
            st.info(f"🧩 اقتراح 3: تقسيم المهمة إلى جزأين ({part1} دقيقة + {duration_min - part1} دقيقة).")

        # 🧠 اختيار المستخدم
        chosen = st.radio(
            "اختر أحد الحلول المقترحة:",
            options=[
                "اقتراح 1: وقت فاضي",
                f"اقتراح 2: فترة {preferred_time}" if preferred_time else "اقتراح 2: تلقائي",
                "اقتراح 3: تقسيم المهمة" if allow_split else "تخطي"
            ]
        )

        # ✅ عند الضغط على "اعتماد الاقتراح"
        if st.button("💾 اعتماد الاقتراح المحدد"):
            conn = sqlite3.connect("smart_scheduler.db")
            cur = conn.cursor()

            if "اقتراح 1" in chosen:
                start_dt, end_dt = suggestion_1_start, suggestion_1_end

            elif "اقتراح 2" in chosen and suggestion_2:
                start_dt, end_dt = suggestion_2

            elif "اقتراح 3" in chosen and allow_split:
                part1 = duration_min // 2
                first_start = suggestion_1_start
                first_end = first_start + timedelta(minutes=part1)
                second_start = first_end + timedelta(minutes=10)
                second_end = second_start + timedelta(minutes=duration_min - part1)

                cur.execute("""INSERT INTO tasks (title, start_time, end_time, duration_min, priority, deadline, recurring, preferred_time, allow_split)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (title + " (part 1)", first_start, first_end, part1, priority, deadline, recurring, preferred_time, allow_split))
                cur.execute("""INSERT INTO tasks (title, start_time, end_time, duration_min, priority, deadline, recurring, preferred_time, allow_split)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (title + " (part 2)", second_start, second_end, duration_min - part1, priority, deadline, recurring, preferred_time, allow_split))
                conn.commit()
                conn.close()
                st.success("✅ تم اعتماد اقتراح التقسيم بنجاح.")
                st.session_state["tasks"] = load_tasks_from_db()
                st.experimental_rerun()
                st.stop()

            # حفظ الاقتراح العادي
            cur.execute("""INSERT INTO tasks (title, start_time, end_time, duration_min, priority, deadline, recurring, preferred_time, allow_split)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (title, start_dt, end_dt, duration_min, priority, deadline, recurring, preferred_time, allow_split))
            conn.commit()
            conn.close()
            st.success("✅ تم حفظ الاقتراح المختار بنجاح.")
            st.session_state["tasks"] = load_tasks_from_db()
            st.experimental_rerun()
            st.stop()

        st.stop()  # يمنع الإضافة التلقائية

    # --- في حالة عدم وجود تعارض، أضف المهمة عادي ---
    new_id = insert_task(new_task)
    new_task.id = new_id
    st.session_state["tasks"].append(new_task)
    st.session_state.setdefault("scheduled", []).append((new_task, start_dt, end_dt, ""))

    st.success(f"✅ تمت إضافة المهمة '{title}' في {start_dt.strftime('%H:%M')} بنجاح (ID={new_id})")


# --- Load example tasks ---
if st.sidebar.button("Load example tasks & busy events"):
    busy_events = [
        Event("Team Meeting", start=ws.replace(hour=9), end=ws.replace(hour=10)),
        Event("Client Call", start=ws.replace(hour=10), end=ws.replace(hour=11)),
        Event("Gym", start=(ws + timedelta(days=1)).replace(hour=18), end=(ws + timedelta(days=1)).replace(hour=19)),
    ]
    tasks = [
            Task(id=1, title="Write report", priority="High", duration_min=120, deadline=ws + timedelta(hours=17), recurring=None, preferred_time="morning", allow_split=True),
            Task(id=2, title="Study ML", priority="Medium", duration_min=180, deadline=ws + timedelta(days=2, hours=18), recurring=None, preferred_time=None, allow_split=True),
            Task(id=3, title="Daily Workout", priority="Medium", duration_min=60, deadline=None, recurring="daily", preferred_time="morning", allow_split=True),
            Task(id=4, title="Prepare slides", priority="High", duration_min=90, deadline=ws + timedelta(hours=16), recurring=None, preferred_time="morning", allow_split=False),
    ]

    # store in session state
    st.session_state['tasks'] = tasks
    st.session_state['busy_events'] = busy_events
    st.success("Example data loaded into session state.")


if 'tasks' not in st.session_state or not st.session_state['tasks']:
    st.info("Press 'Load example tasks & busy events' from sidebar.")
    st.stop()

tasks = st.session_state['tasks']
busy_events = st.session_state['busy_events']

# --- Button to run scheduler ---
if st.button("Generate schedule suggestions (run scheduler)"):
    slots = []
    cur = ws
    while cur < we:
        next_hour = cur + timedelta(hours=1)
        is_busy = any(e.start <= cur < e.end for e in busy_events)
        slots.append(CalendarSlot(start=cur, end=next_hour, is_free=not is_busy))
        cur = next_hour

    scheduler = Scheduler(tasks, slots)
    scheduled_list = scheduler.suggest_schedule(max_chunk_min=120)
    conflicts = scheduler.detect_conflicts(scheduled_list)
    st.session_state['scheduled'] = scheduled_list
    st.session_state['suggestions'] = [f"Conflict between {a} and {b}" for a, b in conflicts]
    st.success("✅ Scheduler ran successfully!")

# --- Calendar preview ---
scheduled = st.session_state.get('scheduled', [])
suggestions = st.session_state.get('suggestions', [])
events = []

for ev in busy_events:
    events.append({
        "title": f"[Busy] {ev.title}",
        "start": ev.start.isoformat(),
        "end": ev.end.isoformat(),
        "color": "#999999",
    })
for t, s, e, note in scheduled:
    events.append({
        "title": f"{t.title}" + (f" ({note})" if note else ""),
        "start": s.isoformat(),
        "end": e.isoformat(),
        "color": "#0b6f3a" if not note else "#f39c12",
    })

calendar_html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <link href="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.css" rel="stylesheet" />
  <script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js"></script>
  <style>
    html, body {{ margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; }}
    #calendar {{ max-width: 1100px; margin: 0 auto; }}
  </style>
</head>
<body>
  <div id='calendar'></div>
  <script>
    document.addEventListener('DOMContentLoaded', function() {{
      const calendarEl = document.getElementById('calendar');
      const events = {json.dumps(events)};
      const calendar = new FullCalendar.Calendar(calendarEl, {{
        initialView: 'timeGridWeek',
        headerToolbar: {{
          left: 'prev,next today',
          center: 'title',
          right: 'timeGridWeek,timeGridDay,listWeek'
        }},
        events: events,
        height: 'auto',
        nowIndicator: true,
        slotMinTime: '06:00:00',
        slotMaxTime: '22:00:00',
        allDaySlot: false
      }});
      calendar.render();
    }});
  </script>
</body>
</html>
"""
st.markdown("## Calendar preview")
st.components.v1.html(calendar_html, height=720, scrolling=True)

st.markdown("## Suggestions / Warnings")
if suggestions:
    for s in suggestions:
        st.write("- " + s)
else:
    st.write("- ✅ لا اقتراحات أو تعارضات.")

st.markdown("## 📋 المهام المخزنة في قاعدة البيانات")

def fetch_tasks():
    conn = sqlite3.connect("smart_scheduler.db")
    df = pd.read_sql_query("SELECT * FROM tasks", conn)
    conn.close()
    return df

if st.button("📂 عرض كل المهام المخزنة"):
    df = fetch_tasks()
    if not df.empty:
        st.dataframe(df)
    else:
        st.warning("🚫 لا توجد مهام بعد في قاعدة البيانات.")