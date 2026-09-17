"""
Ma'lumotlar bazasi (SQLite). Bepul, fayl asosida, hech qanday server kerak emas.
"""
import os
import datetime as dt
import aiosqlite
from config import DB_PATH, DEFAULT_WORK_START, DEFAULT_WORK_END, GRACE_MINUTES, TZ


def normalize_phone(phone: str) -> str:
    """Telefonni oxirgi 9 raqamga keltiradi: +998 90 123 45 67 -> 901234567"""
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return digits[-9:] if len(digits) >= 9 else digits


def now_local() -> dt.datetime:
    return dt.datetime.now(TZ)


async def init_db():
    # Baza papkasini yaratamiz (masalan /data) — Volume shu yerga ulanadi
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                faceid_user_id TEXT UNIQUE,
                telegram_id INTEGER,
                work_start TEXT NOT NULL,
                work_end TEXT NOT NULL,
                grace_minutes INTEGER NOT NULL DEFAULT 0,
                count_late INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,      -- 'in' yoki 'out'
                ts TEXT NOT NULL,              -- ISO local datetime
                day TEXT NOT NULL,             -- YYYY-MM-DD
                external_id TEXT UNIQUE,       -- qurilmadagi noyob id (dedupe uchun)
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            );

            CREATE INDEX IF NOT EXISTS idx_events_emp_day ON events(employee_id, day);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS unknown_names (
                name TEXT PRIMARY KEY,
                last_seen TEXT,
                cnt INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS admins (
                telegram_id INTEGER PRIMARY KEY,
                note TEXT,
                added_at TEXT
            );

            CREATE TABLE IF NOT EXISTS data_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                dtype TEXT NOT NULL,          -- text | photo | file
                dep_id INTEGER,               -- NULL = hammaga (umumiy)
                deadline TEXT,                -- YYYY-MM-DD yoki NULL
                mandatory INTEGER DEFAULT 0,  -- 1 majburiy, 0 ixtiyoriy
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS data_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                employee_id INTEGER NOT NULL,
                content TEXT,                 -- matn yoki file_id
                kind TEXT,
                submitted_at TEXT,
                UNIQUE(request_id, employee_id)
            );

            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                dep_id INTEGER,               -- NULL = hammaga
                active INTEGER DEFAULT 1,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS survey_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                qtext TEXT NOT NULL,
                image_file_id TEXT,
                ord INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS survey_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                otext TEXT NOT NULL,
                ord INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS survey_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                option_id INTEGER NOT NULL,
                employee_id INTEGER NOT NULL,
                answered_at TEXT,
                UNIQUE(question_id, employee_id)
            );

            CREATE TABLE IF NOT EXISTS late_exemptions (
                employee_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                created_at TEXT,
                UNIQUE(employee_id, day)
            );
            """
        )
        # Migratsiya: employees jadvaliga department_id ustunini qo'shamiz (bo'lmasa)
        cur = await db.execute("PRAGMA table_info(employees)")
        cols = [r[1] for r in await cur.fetchall()]
        if "department_id" not in cols:
            await db.execute("ALTER TABLE employees ADD COLUMN department_id INTEGER")
        # Yangi jadvallar (eski bazada bo'lmasligi mumkin) — kafolatli yaratamiz
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS late_exemptions (
                employee_id INTEGER NOT NULL, day TEXT NOT NULL,
                created_at TEXT, UNIQUE(employee_id, day));
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS admins (
                telegram_id INTEGER PRIMARY KEY, note TEXT, added_at TEXT);
            """
        )
        await db.commit()


# ---------------- Xodimlar ----------------

async def add_employee(first_name, last_name, phone, faceid_user_id,
                       work_start=None, work_end=None, grace_minutes=None, count_late=1):
    phone = normalize_phone(phone)
    work_start = work_start or DEFAULT_WORK_START
    work_end = work_end or DEFAULT_WORK_END
    grace = GRACE_MINUTES if grace_minutes is None else grace_minutes
    # FaceID ID ixtiyoriy (guruh o'qishda username bo'yicha topiladi)
    fid = None if faceid_user_id in (None, "", "-") else str(faceid_user_id)
    cl = 1 if count_late else 0
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO employees
               (first_name,last_name,phone,faceid_user_id,work_start,work_end,
                grace_minutes,count_late,active,created_at)
               VALUES (?,?,?,?,?,?,?,?,1,?)""",
            (first_name, last_name, phone, fid, work_start,
             work_end, grace, cl, now_local().isoformat()),
        )
        await db.commit()
        return cur.lastrowid


def full_name(emp):
    """Xodim nomi (username). last_name bo'sh bo'lsa faqat username qaytadi."""
    a = str(emp.get("first_name") or "")
    b = str(emp.get("last_name") or "")
    return (a + " " + b).strip()


async def _row_to_emp(row):
    if not row:
        return None
    keys = ["id", "first_name", "last_name", "phone", "faceid_user_id",
            "telegram_id", "work_start", "work_end", "grace_minutes",
            "count_late", "active", "created_at", "department_id"]
    return dict(zip(keys, row))


async def get_employee_by_phone(phone):
    phone = normalize_phone(phone)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM employees WHERE phone=?", (phone,))
        return await _row_to_emp(await cur.fetchone())


async def get_employee_by_telegram(tg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM employees WHERE telegram_id=?", (tg_id,))
        return await _row_to_emp(await cur.fetchone())


async def get_employee_by_faceid(faceid_user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM employees WHERE faceid_user_id=?",
                               (str(faceid_user_id),))
        return await _row_to_emp(await cur.fetchone())


async def get_employee_by_id(emp_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM employees WHERE id=?", (emp_id,))
        return await _row_to_emp(await cur.fetchone())


def _norm_name(s):
    return " ".join(str(s).lower().split())


async def get_employee_by_name(name):
    """Guruhdagi to'liq ism bo'yicha xodimni topadi (tartib va katta/kichik harfga bardoshli)."""
    target = _norm_name(name)
    ttok = set(target.split())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM employees WHERE active=1")
        rows = await cur.fetchall()
    emps = [await _row_to_emp(r) for r in rows]
    # 1) aniq moslik (ikkala tartibda ham)
    for emp in emps:
        a = _norm_name(f"{emp['first_name']} {emp['last_name']}")
        b = _norm_name(f"{emp['last_name']} {emp['first_name']}")
        if target in (a, b):
            return emp
    # 2) so'zlar bo'yicha (biri ikkinchisining ichida)
    for emp in emps:
        etok = set(_norm_name(f"{emp['first_name']} {emp['last_name']}").split())
        if ttok and (ttok <= etok or etok <= ttok):
            return emp
    return None


async def bind_telegram(emp_id, tg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE employees SET telegram_id=? WHERE id=?", (tg_id, emp_id))
        await db.commit()


async def list_employees(active_only=True):
    async with aiosqlite.connect(DB_PATH) as db:
        q = "SELECT * FROM employees"
        if active_only:
            q += " WHERE active=1"
        q += " ORDER BY LOWER(first_name), LOWER(last_name)"
        cur = await db.execute(q)
        rows = await cur.fetchall()
        return [await _row_to_emp(r) for r in rows]


async def update_employee(emp_id, **fields):
    if not fields:
        return
    allowed = {"first_name", "last_name", "phone", "faceid_user_id",
               "work_start", "work_end", "grace_minutes", "count_late", "active"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            if k == "phone":
                v = normalize_phone(v)
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(emp_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE employees SET {','.join(sets)} WHERE id=?", vals)
        await db.commit()


# ---------------- Hodisalar (events) ----------------

async def last_event_today(emp_id, day):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT event_type FROM events WHERE employee_id=? AND day=? ORDER BY ts DESC LIMIT 1",
            (emp_id, day),
        )
        r = await cur.fetchone()
        return r[0] if r else None


async def add_event(emp_id, ts: dt.datetime, external_id=None, event_type=None):
    """
    Hodisa qo'shadi. event_type berilmasa avtomatik aniqlanadi:
    oldingi hodisa 'in' bo'lsa -> 'out', aks holda -> 'in'.
    external_id orqali takrorlanish oldi olinadi.
    Qaytaradi: (event_type, inserted_bool)
    """
    day = ts.strftime("%Y-%m-%d")
    if event_type is None:
        last = await last_event_today(emp_id, day)
        event_type = "out" if last == "in" else "in"
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO events (employee_id,event_type,ts,day,external_id) VALUES (?,?,?,?,?)",
                (emp_id, event_type, ts.isoformat(), day, external_id),
            )
            await db.commit()
            return event_type, True
        except aiosqlite.IntegrityError:
            # external_id allaqachon bor -> takror
            return event_type, False


async def events_for_day(emp_id, day):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT event_type, ts FROM events WHERE employee_id=? AND day=? ORDER BY ts",
            (emp_id, day),
        )
        return await cur.fetchall()


async def events_between(emp_id, day_from, day_to):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT day, event_type, ts FROM events WHERE employee_id=? AND day>=? AND day<=? ORDER BY ts",
            (emp_id, day_from, day_to),
        )
        return await cur.fetchall()


# ---------------- Sozlamalar (FaceID va h.k.) ----------------

async def get_setting(key, default=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        r = await cur.fetchone()
        return r[0] if r else default


async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)))
        await db.commit()


async def get_settings_dict():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT key, value FROM settings")
        return {k: v for k, v in await cur.fetchall()}


async def count_employees():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM employees")
        r = await cur.fetchone()
        return r[0] if r else 0


# ---------------- Bo'limlar (departments) ----------------
async def add_department(name):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute("INSERT INTO departments(name) VALUES(?)", (name.strip(),))
            await db.commit()
            return cur.lastrowid
        except aiosqlite.IntegrityError:
            return None


async def list_departments():
    """Har bir bo'lim va undagi xodimlar sonini qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT d.id, d.name, COUNT(e.id)
               FROM departments d
               LEFT JOIN employees e ON e.department_id=d.id AND e.active=1
               GROUP BY d.id ORDER BY d.name""")
        return [{"id": r[0], "name": r[1], "count": r[2]} for r in await cur.fetchall()]


async def get_department(dep_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id,name FROM departments WHERE id=?", (dep_id,))
        r = await cur.fetchone()
        return {"id": r[0], "name": r[1]} if r else None


async def delete_department(dep_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE employees SET department_id=NULL WHERE department_id=?", (dep_id,))
        await db.execute("DELETE FROM departments WHERE id=?", (dep_id,))
        await db.commit()


async def department_members(dep_id, active_only=True):
    async with aiosqlite.connect(DB_PATH) as db:
        q = "SELECT * FROM employees WHERE department_id=?"
        if active_only:
            q += " AND active=1"
        q += " ORDER BY LOWER(first_name), LOWER(last_name)"
        cur = await db.execute(q, (dep_id,))
        return [await _row_to_emp(r) for r in await cur.fetchall()]


async def set_employee_department(emp_id, dep_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE employees SET department_id=? WHERE id=?", (dep_id, emp_id))
        await db.commit()


# ---------------- Ro'yxatdan o'tmaganlar ----------------
async def unlinked_employees(dep_id=None):
    """Bazada bor, lekin botga /start bosmagan (telegram_id yo'q) xodimlar."""
    async with aiosqlite.connect(DB_PATH) as db:
        q = "SELECT * FROM employees WHERE active=1 AND (telegram_id IS NULL)"
        args = ()
        if dep_id:
            q += " AND department_id=?"
            args = (dep_id,)
        q += " ORDER BY LOWER(first_name), LOWER(last_name)"
        cur = await db.execute(q, args)
        return [await _row_to_emp(r) for r in await cur.fetchall()]


async def linked_employees(dep_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        q = "SELECT * FROM employees WHERE active=1 AND telegram_id IS NOT NULL"
        args = ()
        if dep_id:
            q += " AND department_id=?"
            args = (dep_id,)
        cur = await db.execute(q, args)
        return [await _row_to_emp(r) for r in await cur.fetchall()]


async def record_unknown(name):
    now = now_local().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO unknown_names(name,last_seen,cnt) VALUES(?,?,1) "
            "ON CONFLICT(name) DO UPDATE SET last_seen=excluded.last_seen, cnt=cnt+1",
            (name, now))
        await db.commit()


async def list_unknown():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT name, cnt, last_seen FROM unknown_names ORDER BY cnt DESC")
        return [{"name": r[0], "cnt": r[1], "last_seen": r[2]} for r in await cur.fetchall()]


async def clear_unknown():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM unknown_names")
        await db.commit()


# ---------------- Xabar shablonlari (templates) ----------------
DEFAULT_TPL_IN = "🟢 Kirish qayd etildi\n🕐 Vaqt: {time}{late}\n\nXush kelibsiz! 😊"
DEFAULT_TPL_OUT = "🔴 Chiqish qayd etildi\n🕐 Vaqt: {time}\n⏱ Ishlangan vaqt: {worked}\n\nYaxshi boring! 👋"
DEFAULT_TPL_WARN = "⚠️ Eslatma\nIltimos, kerakli ma'lumotlarni to'ldiring."
DEFAULT_TPL_SURVEY = "📊 So'rovnoma\nIltimos, quyidagi savollarga javob bering."


async def get_template(key, default=""):
    v = await get_setting(key)
    return v if v else default


# ---------------- Adminlar (bot orqali qo'shiladigan) ----------------
async def add_admin(telegram_id, note=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO admins(telegram_id,note,added_at) VALUES(?,?,?)",
            (int(telegram_id), note, now_local().isoformat()))
        await db.commit()


async def remove_admin(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE telegram_id=?", (int(telegram_id),))
        await db.commit()


async def list_admins():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT telegram_id, note FROM admins ORDER BY added_at")
        return [{"telegram_id": r[0], "note": r[1]} for r in await cur.fetchall()]


async def list_admin_ids():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT telegram_id FROM admins")
        return [r[0] for r in await cur.fetchall()]


# ==================== A: MA'LUMOT TALABLARI ====================
def _emp_matches_dep(emp, dep_id):
    return dep_id is None or emp.get("department_id") == dep_id


async def add_data_request(title, dtype, dep_id, deadline, mandatory):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO data_requests(title,dtype,dep_id,deadline,mandatory,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (title, dtype, dep_id, deadline, 1 if mandatory else 0, now_local().isoformat()))
        await db.commit()
        return cur.lastrowid


async def get_data_request(req_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id,title,dtype,dep_id,deadline,mandatory FROM data_requests WHERE id=?", (req_id,))
        r = await cur.fetchone()
        if not r:
            return None
        return {"id": r[0], "title": r[1], "dtype": r[2], "dep_id": r[3],
                "deadline": r[4], "mandatory": r[5]}


async def list_data_requests():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT r.id,r.title,r.dtype,r.dep_id,r.deadline,r.mandatory,
                      (SELECT COUNT(*) FROM data_submissions s WHERE s.request_id=r.id)
               FROM data_requests r ORDER BY r.id DESC""")
        out = []
        for r in await cur.fetchall():
            out.append({"id": r[0], "title": r[1], "dtype": r[2], "dep_id": r[3],
                        "deadline": r[4], "mandatory": r[5], "subs": r[6]})
        return out


async def delete_data_request(req_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM data_submissions WHERE request_id=?", (req_id,))
        await db.execute("DELETE FROM data_requests WHERE id=?", (req_id,))
        await db.commit()


async def add_submission(request_id, employee_id, content, kind):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO data_submissions(request_id,employee_id,content,kind,submitted_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(request_id,employee_id) "
            "DO UPDATE SET content=excluded.content, kind=excluded.kind, submitted_at=excluded.submitted_at",
            (request_id, employee_id, content, kind, now_local().isoformat()))
        await db.commit()


async def request_submissions(request_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT e.first_name,e.last_name,e.phone,s.content,s.kind,s.submitted_at,s.employee_id
               FROM data_submissions s JOIN employees e ON e.id=s.employee_id
               WHERE s.request_id=? ORDER BY s.submitted_at""", (request_id,))
        return [{"first_name": r[0], "last_name": r[1], "phone": r[2], "content": r[3],
                 "kind": r[4], "at": r[5], "emp_id": r[6]} for r in await cur.fetchall()]


async def pending_requests_for(emp):
    """Xodimga tegishli (dep mos), hali topshirilmagan talablar."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id,title,dtype,dep_id,deadline,mandatory FROM data_requests")
        reqs = await cur.fetchall()
        cur2 = await db.execute("SELECT request_id FROM data_submissions WHERE employee_id=?", (emp["id"],))
        done = {r[0] for r in await cur2.fetchall()}
    out = []
    for r in reqs:
        req = {"id": r[0], "title": r[1], "dtype": r[2], "dep_id": r[3],
               "deadline": r[4], "mandatory": r[5]}
        if req["id"] in done:
            continue
        if _emp_matches_dep(emp, req["dep_id"]):
            out.append(req)
    return out


async def eligible_linked_for_request(req):
    emps = await linked_employees()
    return [e for e in emps if _emp_matches_dep(e, req["dep_id"])]


# ==================== B: SO'ROVNOMALAR ====================
async def create_survey(title, dep_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO surveys(title,dep_id,active,created_at) VALUES(?,?,1,?)",
            (title, dep_id, now_local().isoformat()))
        await db.commit()
        return cur.lastrowid


async def add_question(survey_id, qtext, image_file_id, ord):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO survey_questions(survey_id,qtext,image_file_id,ord) VALUES(?,?,?,?)",
            (survey_id, qtext, image_file_id, ord))
        await db.commit()
        return cur.lastrowid


async def add_option(question_id, otext, ord):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO survey_options(question_id,otext,ord) VALUES(?,?,?)",
            (question_id, otext, ord))
        await db.commit()


async def get_survey(survey_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id,title,dep_id,active FROM surveys WHERE id=?", (survey_id,))
        r = await cur.fetchone()
        return {"id": r[0], "title": r[1], "dep_id": r[2], "active": r[3]} if r else None


async def list_surveys():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT s.id,s.title,s.dep_id,s.active,
                      (SELECT COUNT(DISTINCT employee_id) FROM survey_answers a WHERE a.survey_id=s.id)
               FROM surveys s ORDER BY s.id DESC""")
        return [{"id": r[0], "title": r[1], "dep_id": r[2], "active": r[3], "responders": r[4]}
                for r in await cur.fetchall()]


async def survey_questions(survey_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id,qtext,image_file_id,ord FROM survey_questions WHERE survey_id=? ORDER BY ord,id",
            (survey_id,))
        return [{"id": r[0], "qtext": r[1], "image_file_id": r[2], "ord": r[3]}
                for r in await cur.fetchall()]


async def question_options(question_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id,otext,ord FROM survey_options WHERE question_id=? ORDER BY ord,id",
            (question_id,))
        return [{"id": r[0], "otext": r[1], "ord": r[2]} for r in await cur.fetchall()]


async def record_answer(survey_id, question_id, option_id, employee_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO survey_answers(survey_id,question_id,option_id,employee_id,answered_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(question_id,employee_id) "
            "DO UPDATE SET option_id=excluded.option_id, answered_at=excluded.answered_at",
            (survey_id, question_id, option_id, employee_id, now_local().isoformat()))
        await db.commit()


async def survey_stats(survey_id):
    """Har bir savol -> variantlar va nechta kishi tanlagani."""
    qs = await survey_questions(survey_id)
    async with aiosqlite.connect(DB_PATH) as db:
        result = []
        for q in qs:
            opts = await question_options(q["id"])
            data = []
            total = 0
            for o in opts:
                cur = await db.execute(
                    "SELECT COUNT(*) FROM survey_answers WHERE question_id=? AND option_id=?",
                    (q["id"], o["id"]))
                c = (await cur.fetchone())[0]
                total += c
                data.append({"otext": o["otext"], "count": c})
            result.append({"qtext": q["qtext"], "options": data, "total": total})
        return result


async def survey_detailed(survey_id):
    """Har bir xodim -> savolларга bergan javoblari."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT e.first_name,e.last_name,q.qtext,o.otext,a.answered_at
               FROM survey_answers a
               JOIN employees e ON e.id=a.employee_id
               JOIN survey_questions q ON q.id=a.question_id
               JOIN survey_options o ON o.id=a.option_id
               WHERE a.survey_id=? ORDER BY e.last_name,e.first_name,q.ord,q.id""",
            (survey_id,))
        rows = await cur.fetchall()
    by_emp = {}
    for fn, ln, qt, ot, at in rows:
        key = (str(fn or "")+" "+str(ln or "")).strip()
        by_emp.setdefault(key, []).append((qt, ot))
    return by_emp


async def delete_survey(survey_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM survey_answers WHERE survey_id=?", (survey_id,))
        qs = await db.execute("SELECT id FROM survey_questions WHERE survey_id=?", (survey_id,))
        qids = [r[0] for r in await qs.fetchall()]
        for qid in qids:
            await db.execute("DELETE FROM survey_options WHERE question_id=?", (qid,))
        await db.execute("DELETE FROM survey_questions WHERE survey_id=?", (survey_id,))
        await db.execute("DELETE FROM surveys WHERE id=?", (survey_id,))
        await db.commit()


async def has_completed_survey(emp_id, survey_id):
    qs = await survey_questions(survey_id)
    if not qs:
        return True
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(DISTINCT question_id) FROM survey_answers WHERE survey_id=? AND employee_id=?",
            (survey_id, emp_id))
        answered = (await cur.fetchone())[0]
    return answered >= len(qs)


async def pending_surveys_for(emp):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id,title,dep_id FROM surveys WHERE active=1")
        rows = await cur.fetchall()
    out = []
    for r in rows:
        s = {"id": r[0], "title": r[1], "dep_id": r[2]}
        if not _emp_matches_dep(emp, s["dep_id"]):
            continue
        if not await has_completed_survey(emp["id"], s["id"]):
            out.append(s)
    return out


async def eligible_linked_for_survey(survey):
    emps = await linked_employees()
    return [e for e in emps if _emp_matches_dep(e, survey["dep_id"])]


async def search_employees(query, linked_only=True):
    """Ism (username) yoki telefon bo'yicha xodim qidiradi."""
    q = f"%{query.strip().lower()}%"
    async with aiosqlite.connect(DB_PATH) as db:
        sql = ("SELECT * FROM employees WHERE active=1 AND "
               "(LOWER(first_name) LIKE ? OR LOWER(last_name) LIKE ? OR phone LIKE ?)")
        if linked_only:
            sql += " AND telegram_id IS NOT NULL"
        sql += " ORDER BY LOWER(first_name) LIMIT 30"
        cur = await db.execute(sql, (q, q, q))
        return [await _row_to_emp(r) for r in await cur.fetchall()]


# ==================== Kechikishni hisoblamaslik (kechirim) ====================
async def add_exemptions(emp_ids, day):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS late_exemptions (
                   employee_id INTEGER NOT NULL, day TEXT NOT NULL,
                   created_at TEXT, UNIQUE(employee_id, day))""")
        for eid in emp_ids:
            await db.execute(
                "INSERT OR IGNORE INTO late_exemptions(employee_id,day,created_at) VALUES(?,?,?)",
                (int(eid), day, now_local().isoformat()))
        await db.commit()


async def is_exempt(emp_id, day):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT 1 FROM late_exemptions WHERE employee_id=? AND day=?", (emp_id, day))
            return (await cur.fetchone()) is not None
    except Exception:
        return False


async def exempt_days_for(emp_id):
    """Xodimning barcha kechirilgan kunlari (bitta so'rovda)."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT day FROM late_exemptions WHERE employee_id=?", (emp_id,))
            return {r[0] for r in await cur.fetchall()}
    except Exception:
        return set()


async def list_exemptions():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT x.employee_id, x.day, e.first_name, e.last_name
               FROM late_exemptions x JOIN employees e ON e.id=x.employee_id
               ORDER BY x.day DESC, e.first_name""")
        return [{"emp_id": r[0], "day": r[1], "first_name": r[2], "last_name": r[3]}
                for r in await cur.fetchall()]


async def remove_exemption(emp_id, day):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM late_exemptions WHERE employee_id=? AND day=?", (emp_id, day))
        await db.commit()


async def set_manual_attendance(emp_id, day, kirish_hm, chiqish_hm):
    """Berilgan kun uchun kirish/chiqishni qo'lda o'rnatadi (eski qaydlarni almashtiradi)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM events WHERE employee_id=? AND day=?", (emp_id, day))
        if kirish_hm:
            ts = f"{day}T{kirish_hm}:00"
            await db.execute(
                "INSERT OR REPLACE INTO events(employee_id,event_type,ts,day,external_id) VALUES(?,?,?,?,?)",
                (emp_id, "in", ts, day, f"manual-{emp_id}-{day}-in"))
        if chiqish_hm:
            ts = f"{day}T{chiqish_hm}:00"
            await db.execute(
                "INSERT OR REPLACE INTO events(employee_id,event_type,ts,day,external_id) VALUES(?,?,?,?,?)",
                (emp_id, "out", ts, day, f"manual-{emp_id}-{day}-out"))
        await db.commit()
