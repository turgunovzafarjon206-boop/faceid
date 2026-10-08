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
            CREATE TABLE IF NOT EXISTS unknown_names (
                name TEXT PRIMARY KEY, last_seen TEXT, cnt INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS data_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, dtype TEXT NOT NULL,
                dep_id INTEGER, deadline TEXT, mandatory INTEGER DEFAULT 0, created_at TEXT);
            CREATE TABLE IF NOT EXISTS data_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER NOT NULL,
                employee_id INTEGER NOT NULL, content TEXT, kind TEXT, submitted_at TEXT,
                UNIQUE(request_id, employee_id));
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, dep_id INTEGER,
                active INTEGER DEFAULT 1, created_at TEXT);
            CREATE TABLE IF NOT EXISTS survey_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, survey_id INTEGER NOT NULL, qtext TEXT NOT NULL,
                image_file_id TEXT, ord INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS survey_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT, question_id INTEGER NOT NULL,
                otext TEXT NOT NULL, ord INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS survey_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, survey_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL, option_id INTEGER NOT NULL, employee_id INTEGER NOT NULL,
                answered_at TEXT, UNIQUE(question_id, employee_id));
            CREATE TABLE IF NOT EXISTS lesson_times (
                sched_name TEXT NOT NULL, day TEXT NOT NULL, start_min INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sched_alias (
                sched_name TEXT PRIMARY KEY, employee_id INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS manual_lessons (
                employee_id INTEGER NOT NULL, day TEXT NOT NULL, start_min INTEGER NOT NULL,
                UNIQUE(employee_id, day));
            CREATE TABLE IF NOT EXISTS exempt_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL,
                day TEXT NOT NULL, reason TEXT, status TEXT DEFAULT 'pending',
                created_at TEXT, decided_by INTEGER);
            CREATE TABLE IF NOT EXISTS roles (
                employee_id INTEGER PRIMARY KEY, role TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS exreq_messages (
                req_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL, text TEXT);
            """
        )
        # employees: branch_id ustuni
        cur = await db.execute("PRAGMA table_info(employees)")
        _cols2 = [r[1] for r in await cur.fetchall()]
        if "branch_id" not in _cols2:
            await db.execute("ALTER TABLE employees ADD COLUMN branch_id INTEGER")
        # late_exemptions: from_min ustuni (NULL = butun kun, son = shu vaqtdan boshlab hisoblanadi)
        cur = await db.execute("PRAGMA table_info(late_exemptions)")
        _ecols = [r[1] for r in await cur.fetchall()]
        if "from_min" not in _ecols:
            await db.execute("ALTER TABLE late_exemptions ADD COLUMN from_min INTEGER")
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
            "count_late", "active", "created_at", "department_id", "branch_id"]
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
            # Bot o'zi yozgan qayd ustun: Excel'dan to'ldirilgan shu turdagi qaydni olib tashlaymiz
            if not str(external_id or "").startswith("xls-"):
                await db.execute(
                    "DELETE FROM events WHERE employee_id=? AND day=? AND event_type=? "
                    "AND external_id LIKE 'xls-%'", (emp_id, day, event_type))
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
        await db.executescript(
            """CREATE TABLE IF NOT EXISTS data_requests (
                   id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, dtype TEXT NOT NULL,
                   dep_id INTEGER, deadline TEXT, mandatory INTEGER DEFAULT 0, created_at TEXT);
               CREATE TABLE IF NOT EXISTS data_submissions (
                   id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER NOT NULL,
                   employee_id INTEGER NOT NULL, content TEXT, kind TEXT, submitted_at TEXT,
                   UNIQUE(request_id, employee_id));""")
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
    try:
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
    except Exception:
        return []


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
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT id,title,dtype,dep_id,deadline,mandatory FROM data_requests")
            reqs = await cur.fetchall()
            cur2 = await db.execute("SELECT request_id FROM data_submissions WHERE employee_id=?", (emp["id"],))
            done = {r[0] for r in await cur2.fetchall()}
    except Exception:
        return []
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


_CYR2LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h", "і": "i",
}
_VOWELS = set("аеёиоуыэюяўaeiou")
_APOS = "'`ʻʼ‘’´\""


def translit(text):
    """Kirill -> Lotin (o'zbekcha). Lotin matn o'zgarmaydi."""
    t = (text or "").lower()
    out = []
    prev = ""
    for ch in t:
        if ch == "е" and (not prev or not prev.isalpha() or prev in _VOWELS or prev in "ъь"):
            out.append("ye")          # Евгений -> Yevgeniy, Абдуллаев -> Abdullayev
        elif ch in _CYR2LAT:
            out.append(_CYR2LAT[ch])
        else:
            out.append(ch)
        prev = ch
    return "".join(out)


def search_key(text):
    """Qidiruv uchun yumshoq kalit: kirill/lotin, apostrof, q/k, x/h farqlari e'tiborsiz."""
    t = translit(text)
    for a in _APOS:
        t = t.replace(a, "")
    t = t.replace("dj", "j").replace("kh", "x")
    t = t.replace("sh", "\x01").replace("ch", "\x02")
    t = t.replace("h", "x").replace("q", "k")
    t = t.replace("\x01", "sh").replace("\x02", "ch")
    return " ".join(t.split())


async def search_employees(query, linked_only=True):
    """Ism (username) yoki telefon bo'yicha qidiradi. Kirill yoki lotinda yozilsa ham topadi."""
    key = search_key(query)
    digits = "".join(c for c in (query or "") if c.isdigit())
    if not key:
        return []
    out = []
    for e in await list_employees(active_only=True):
        if linked_only and not e.get("telegram_id"):
            continue
        name_key = search_key(f"{e.get('first_name') or ''} {e.get('last_name') or ''}")
        phone = "".join(c for c in str(e.get("phone") or "") if c.isdigit())
        if key in name_key or (len(digits) >= 3 and digits in phone):
            out.append(e)
        if len(out) >= 30:
            break
    return out


# ==================== Kechikishni hisoblamaslik (kechirim) ====================
async def _ensure_exempt_table(db):
    await db.execute(
        """CREATE TABLE IF NOT EXISTS late_exemptions (
               employee_id INTEGER NOT NULL, day TEXT NOT NULL,
               created_at TEXT, UNIQUE(employee_id, day))""")
    cur = await db.execute("PRAGMA table_info(late_exemptions)")
    cols = [r[1] for r in await cur.fetchall()]
    if "from_min" not in cols:
        await db.execute("ALTER TABLE late_exemptions ADD COLUMN from_min INTEGER")


async def add_exemptions(emp_ids, day, from_min=None):
    """from_min=None -> butun kun uchun kechikish hisoblanmaydi.
    from_min=<daqiqa> -> shu vaqtdan boshlab kechikish hisoblanadi (masalan 9:30 -> 570)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_exempt_table(db)
        for eid in emp_ids:
            await db.execute(
                "INSERT OR REPLACE INTO late_exemptions(employee_id,day,created_at,from_min) "
                "VALUES(?,?,?,?)",
                (int(eid), day, now_local().isoformat(), from_min))
        await db.commit()


async def is_exempt(emp_id, day):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT 1 FROM late_exemptions WHERE employee_id=? AND day=?", (emp_id, day))
            return (await cur.fetchone()) is not None
    except Exception:
        return False


async def exempt_map_for(emp_id):
    """Xodimning kechirimlari: {day: from_min yoki None} (bitta so'rovda)."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT day, from_min FROM late_exemptions WHERE employee_id=?", (emp_id,))
            return {r[0]: r[1] for r in await cur.fetchall()}
    except Exception:
        return {}


async def exempt_days_for(emp_id):
    """Xodimning kechirilgan kunlari (moslik uchun)."""
    return set((await exempt_map_for(emp_id)).keys())


async def list_exemptions():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """SELECT x.employee_id, x.day, e.first_name, e.last_name, x.from_min
                   FROM late_exemptions x JOIN employees e ON e.id=x.employee_id
                   ORDER BY x.day DESC, e.first_name""")
            return [{"emp_id": r[0], "day": r[1], "first_name": r[2],
                     "last_name": r[3], "from_min": r[4]} for r in await cur.fetchall()]
    except Exception:
        return []


async def remove_exemption(emp_id, day):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM late_exemptions WHERE employee_id=? AND day=?", (emp_id, day))
        await db.commit()


async def set_manual_attendance(emp_id, day, kirish_hm, chiqish_hm):
    """Berilgan kun uchun kirish/chiqishni qo'lda o'rnatadi (eski qaydlarni almashtiradi)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Faqat kiritilgan tur almashtiriladi (faqat Kirish berilsa — Chiqish saqlanib qoladi)
        if kirish_hm and chiqish_hm:
            await db.execute("DELETE FROM events WHERE employee_id=? AND day=?", (emp_id, day))
        elif kirish_hm:
            await db.execute("DELETE FROM events WHERE employee_id=? AND day=? AND event_type='in'",
                             (emp_id, day))
        elif chiqish_hm:
            await db.execute("DELETE FROM events WHERE employee_id=? AND day=? AND event_type='out'",
                             (emp_id, day))
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


async def employee_submissions(emp_id):
    """Xodim topshirgan barcha ma'lumotlar (talab nomi bilan)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT r.title, s.kind, s.content, s.submitted_at, r.id
               FROM data_submissions s JOIN data_requests r ON r.id=s.request_id
               WHERE s.employee_id=? ORDER BY r.id""", (emp_id,))
        return [{"title": r[0], "kind": r[1], "content": r[2], "at": r[3], "req_id": r[4]}
                for r in await cur.fetchall()]


async def incomplete_report():
    """To'ldirmagan xodimlar: [{emp, missing:[titles]}]."""
    emps = await list_employees()
    out = []
    for emp in emps:
        pending = await pending_requests_for(emp)
        if pending:
            out.append({"emp": emp, "missing": [p["title"] for p in pending]})
    return out


# ==================== Dars jadvali (HolliHop) ====================
def _sched_parse(name):
    """'Tolipova N.' -> (['tolipova'], 'n'); 'Y.U H.' -> (['y.u'], 'h')."""
    toks = [t for t in str(name).replace("\n", " ").split() if t]
    if not toks:
        return [], None
    last = toks[-1].strip(".")
    if len(last) == 1 and len(toks) > 1:
        return [t.lower().strip(".") for t in toks[:-1]], last.lower()
    return [t.lower().strip(".") for t in toks], None


def _emp_tokens(emp):
    return [t.lower().strip(".") for t in full_name(emp).split() if t]


def _auto_match(sched_name, emps):
    surn, init = _sched_parse(sched_name)
    if not surn:
        return None
    for emp in emps:
        et = _emp_tokens(emp)
        if all(s in et for s in surn):
            if init is None or any(t.startswith(init) for t in et):
                return emp
    return None


async def import_schedule(entries):
    """entries: [(sched_name, day, start_min), ...] — eski jadvalni almashtiradi (aliaslar qoladi)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """CREATE TABLE IF NOT EXISTS lesson_times (sched_name TEXT, day TEXT, start_min INTEGER);
               CREATE TABLE IF NOT EXISTS sched_alias (sched_name TEXT PRIMARY KEY, employee_id INTEGER);""")
        await db.execute("DELETE FROM lesson_times")
        await db.executemany(
            "INSERT INTO lesson_times(sched_name,day,start_min) VALUES(?,?,?)", entries)
        await db.commit()


async def schedule_teacher_names():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT DISTINCT sched_name FROM lesson_times")
            return [r[0] for r in await cur.fetchall()]
    except Exception:
        return []


async def add_alias(sched_name, employee_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS sched_alias (sched_name TEXT PRIMARY KEY, employee_id INTEGER)")
        await db.execute(
            "INSERT OR REPLACE INTO sched_alias(sched_name,employee_id) VALUES(?,?)",
            (sched_name, int(employee_id)))
        await db.commit()


async def _alias_map():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT sched_name, employee_id FROM sched_alias")
            return {r[0]: r[1] for r in await cur.fetchall()}
    except Exception:
        return {}


async def is_lesson_employee(emp):
    """Xodim 'O'quv bo'limi'da bo'lsa True — dars jadvali faqat shularga amal qiladi."""
    dep_id = emp.get("department_id")
    if not dep_id:
        return False
    d = await get_department(dep_id)
    if not d:
        return False
    name = str(d["name"]).lower().replace("'", "").replace("`", "").replace("ʻ", "")
    return "quv" in name  # o'quv / oquv / uquv bo'limi


async def schedule_name_for_employee(emp):
    """Xodimga mos dars-jadval nomini topadi (faqat O'quv bo'limi uchun)."""
    if not await is_lesson_employee(emp):
        return None
    names = await schedule_teacher_names()
    if not names:
        return None
    aliases = await _alias_map()
    for sn, eid in aliases.items():
        if eid == emp["id"] and sn in names:
            return sn
    surn_e = _emp_tokens(emp)
    for sn in names:
        surn, init = _sched_parse(sn)
        if surn and all(s in surn_e for s in surn):
            if init is None or any(t.startswith(init) for t in surn_e):
                return sn
    return None


async def lesson_start_min(sched_name, day):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT MIN(start_min) FROM lesson_times WHERE sched_name=? AND day=?", (sched_name, day))
            r = await cur.fetchone()
            return r[0] if r and r[0] is not None else None
    except Exception:
        return None


async def unmatched_schedule_names():
    """Botdagi xodimga bog'lanmagan (alias ham, avto ham yo'q) jadval nomlari."""
    names = await schedule_teacher_names()
    if not names:
        return []
    emps = await list_employees()
    aliases = await _alias_map()
    aliased = set(aliases.keys())
    out = []
    for sn in names:
        if sn in aliased:
            continue
        if _auto_match(sn, emps) is None:
            out.append(sn)
    return out


async def requests_for_employee(emp):
    """Xodimga tegishli barcha ma'lumot talablari (topshirilган/topshirilmagan belgisi bilan)."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT id,title,dtype,dep_id,deadline,mandatory FROM data_requests ORDER BY id")
            reqs = await cur.fetchall()
            cur2 = await db.execute("SELECT request_id FROM data_submissions WHERE employee_id=?", (emp["id"],))
            done = {r[0] for r in await cur2.fetchall()}
    except Exception:
        return []
    out = []
    for r in reqs:
        req = {"id": r[0], "title": r[1], "dtype": r[2], "dep_id": r[3],
               "deadline": r[4], "mandatory": r[5]}
        if _emp_matches_dep(emp, req["dep_id"]):
            req["submitted"] = req["id"] in done
            out.append(req)
    return out


async def unknown_pending():
    """Guruhda ko'rilgan, lekin bazada hali yo'q ismlar. Endi bazada bor bo'lganlar avtomatik tozalanadi."""
    items = await list_unknown()
    pending = []
    to_delete = []
    for it in items:
        if await get_employee_by_name(it["name"]):
            to_delete.append(it["name"])
        else:
            pending.append(it)
    if to_delete:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.executemany("DELETE FROM unknown_names WHERE name=?",
                                     [(n,) for n in to_delete])
                await db.commit()
        except Exception:
            pass
    return pending


# ==================== Filiallar (branches) ====================
async def _ensure_branch_schema(db):
    await db.execute(
        "CREATE TABLE IF NOT EXISTS branches (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)")
    cur = await db.execute("PRAGMA table_info(employees)")
    cols = [r[1] for r in await cur.fetchall()]
    if "branch_id" not in cols:
        await db.execute("ALTER TABLE employees ADD COLUMN branch_id INTEGER")


async def add_branch(name):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_branch_schema(db)
        try:
            cur = await db.execute("INSERT INTO branches(name) VALUES(?)", (name.strip(),))
            await db.commit()
            return cur.lastrowid
        except aiosqlite.IntegrityError:
            return None


async def list_branches():
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await _ensure_branch_schema(db)
            await db.commit()
        except Exception:
            pass
        try:
            cur = await db.execute(
                """SELECT b.id, b.name, COUNT(e.id)
                   FROM branches b
                   LEFT JOIN employees e ON e.branch_id=b.id AND e.active=1
                   GROUP BY b.id ORDER BY b.name""")
            return [{"id": r[0], "name": r[1], "count": r[2]} for r in await cur.fetchall()]
        except Exception:
            # JOIN ishlamasa ham filiallar ro'yxati ko'rinsin
            try:
                cur = await db.execute("SELECT id, name FROM branches ORDER BY name")
                return [{"id": r[0], "name": r[1], "count": 0} for r in await cur.fetchall()]
            except Exception:
                return []


async def get_branch(branch_id):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT id,name FROM branches WHERE id=?", (branch_id,))
            r = await cur.fetchone()
            return {"id": r[0], "name": r[1]} if r else None
    except Exception:
        return None


async def find_branch_by_name(name):
    key = " ".join(str(name).lower().split())
    for b in await list_branches():
        if " ".join(b["name"].lower().split()) == key:
            return b
    return None


async def delete_branch(branch_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE employees SET branch_id=NULL WHERE branch_id=?", (branch_id,))
        await db.execute("DELETE FROM branches WHERE id=?", (branch_id,))
        await db.commit()


async def set_employee_branch(emp_id, branch_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_branch_schema(db)
        await db.execute("UPDATE employees SET branch_id=? WHERE id=?", (branch_id, emp_id))
        await db.commit()


async def branch_members(branch_id, active_only=True):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_branch_schema(db)
        await db.commit()
        q = "SELECT * FROM employees WHERE branch_id=?"
        if active_only:
            q += " AND active=1"
        q += " ORDER BY LOWER(first_name), LOWER(last_name)"
        cur = await db.execute(q, (branch_id,))
        return [await _row_to_emp(r) for r in await cur.fetchall()]


async def employees_export_text():
    """Ommaviy tayinlash uchun matn: 'Username — Filial nomi' qatorlari."""
    lines = []
    for e in await list_employees():
        br = ""
        if e.get("branch_id"):
            b = await get_branch(e["branch_id"])
            br = b["name"] if b else ""
        lines.append(f"{full_name(e)} — {br}")
    return "\n".join(lines)


async def bulk_assign_branches(text, create_missing=True):
    """Matnni o'qib, har bir xodimga filial tayinlaydi.
    Format: 'Username — Filial' (ajratgich: —, -, :, | yoki tab)."""
    ok = 0
    not_found = []
    created = []
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = None
        for sep in ("—", "–", "\t", " - ", ":", "|"):
            if sep in line:
                parts = line.split(sep, 1)
                break
        if not parts or len(parts) < 2:
            continue
        name, bname = parts[0].strip(), parts[1].strip()
        if not name or not bname:
            continue
        emp = await get_employee_by_name(name)
        if not emp:
            not_found.append(name)
            continue
        br = await find_branch_by_name(bname)
        if not br:
            if not create_missing:
                not_found.append(f"{name} (filial: {bname})")
                continue
            bid = await add_branch(bname)
            if bid is None:
                br = await find_branch_by_name(bname)
                bid = br["id"] if br else None
            else:
                created.append(bname)
            if bid is None:
                continue
        else:
            bid = br["id"]
        await set_employee_branch(emp["id"], bid)
        ok += 1
    return {"ok": ok, "not_found": not_found, "created": created}


# ==================== Rasm orqali dars jadvali (har xodimga) ====================
async def _ensure_manual_lessons(db):
    await db.execute(
        """CREATE TABLE IF NOT EXISTS manual_lessons (
               employee_id INTEGER NOT NULL, day TEXT NOT NULL, start_min INTEGER NOT NULL,
               UNIQUE(employee_id, day))""")


async def save_manual_lessons(emp_id, ym, day_to_min):
    """ym='2026-09'. Shu oy uchun eski yozuvlar o'chiriladi va yangilari yoziladi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_manual_lessons(db)
        await db.execute("DELETE FROM manual_lessons WHERE employee_id=? AND substr(day,1,7)=?",
                         (emp_id, ym))
        await db.executemany(
            "INSERT OR REPLACE INTO manual_lessons(employee_id,day,start_min) VALUES(?,?,?)",
            [(emp_id, d, m) for d, m in sorted(day_to_min.items())])
        await db.commit()


async def manual_lessons_for(emp_id):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT day, start_min FROM manual_lessons WHERE employee_id=?", (emp_id,))
            return {r[0]: r[1] for r in await cur.fetchall()}
    except Exception:
        return {}


async def lesson_context(emp):
    """Dars-jadval konteksti (faqat O'quv bo'limi uchun).
    Rasm orqali belgilangan oylar Excel jadvalidan ustun turadi."""
    if not await is_lesson_employee(emp):
        return {"is_lesson": False}
    manual = await manual_lessons_for(emp["id"])
    return {
        "is_lesson": True,
        "sched_name": None,   # Excel dars jadvali olib tashlandi — faqat rasm orqali belgilangan jadval
        "manual": manual,
        "manual_months": {d[:7] for d in manual},
    }


async def oquv_employees():
    """O'quv bo'limi(lar)idagi faol xodimlar."""
    out = []
    for d in await list_departments():
        nm = str(d["name"]).lower().replace("'", "").replace("`", "").replace("ʻ", "")
        if "quv" in nm:
            out.extend(await department_members(d["id"]))
    seen, res = set(), []
    for e in out:
        if e["id"] not in seen:
            seen.add(e["id"]); res.append(e)
    return res


# ==================== Xodim: jarima hisoblamaslik so'rovi ====================
async def _ensure_exreq(db):
    await db.execute(
        """CREATE TABLE IF NOT EXISTS exempt_requests (
               id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL,
               day TEXT NOT NULL, reason TEXT, status TEXT DEFAULT 'pending',
               created_at TEXT, decided_by INTEGER)""")


async def create_exempt_request(emp_id, day, reason):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_exreq(db)
        cur = await db.execute(
            "INSERT INTO exempt_requests(employee_id,day,reason,status,created_at) VALUES(?,?,?,?,?)",
            (emp_id, day, reason, "pending", now_local().isoformat()))
        await db.commit()
        return cur.lastrowid


async def get_exempt_request(req_id):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT id,employee_id,day,reason,status,decided_by FROM exempt_requests WHERE id=?",
                (req_id,))
            r = await cur.fetchone()
            if not r:
                return None
            return {"id": r[0], "employee_id": r[1], "day": r[2], "reason": r[3],
                    "status": r[4], "decided_by": r[5]}
    except Exception:
        return None


async def decide_exempt_request(req_id, status, admin_id):
    """Faqat 'pending' bo'lsa o'zgartiradi. True — muvaffaqiyatli, False — allaqachon hal qilingan."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_exreq(db)
        cur = await db.execute(
            "UPDATE exempt_requests SET status=?, decided_by=? WHERE id=? AND status='pending'",
            (status, admin_id, req_id))
        await db.commit()
        return cur.rowcount > 0


async def lesson_days_in_range(emp, day_from, day_to):
    """O'quv bo'limi xodimining shu oraliqdagi dars kunlari: {'YYYY-MM-DD': dars_boshlanish_min}.
    Rasm orqali belgilangan oy Excel jadvalidan ustun turadi."""
    ctx = await lesson_context(emp)
    if not ctx.get("is_lesson"):
        return {}
    out = {d: m for d, m in ctx["manual"].items() if day_from <= d <= day_to}
    sn = ctx.get("sched_name")
    if sn:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cur = await db.execute(
                    """SELECT day, MIN(start_min) FROM lesson_times
                       WHERE sched_name=? AND day BETWEEN ? AND ? GROUP BY day""",
                    (sn, day_from, day_to))
                for d, m in await cur.fetchall():
                    if d[:7] not in ctx["manual_months"] and d not in out:
                        out[d] = m
        except Exception:
            pass
    return out


# ==================== Rollar: bo'lim rahbari / menejer ====================
ROLE_NAMES = {"head": "Bo'lim rahbari", "manager": "Menejer"}


async def _ensure_roles(db):
    await db.execute("CREATE TABLE IF NOT EXISTS roles (employee_id INTEGER PRIMARY KEY, role TEXT NOT NULL)")


async def set_role(emp_id, role):
    """role: 'head' | 'manager' | None (olib tashlash)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_roles(db)
        if role:
            await db.execute("INSERT OR REPLACE INTO roles(employee_id, role) VALUES(?,?)", (emp_id, role))
        else:
            await db.execute("DELETE FROM roles WHERE employee_id=?", (emp_id,))
        await db.commit()


async def get_role(emp_id):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT role FROM roles WHERE employee_id=?", (emp_id,))
            r = await cur.fetchone()
            return r[0] if r else None
    except Exception:
        return None


async def role_holders(role, dep_id=None):
    """Shu roldagi faol xodimlar (bo'lim rahbari uchun dep_id bo'yicha)."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            q = ("SELECT e.* FROM employees e JOIN roles r ON r.employee_id=e.id "
                 "WHERE r.role=? AND e.active=1")
            args = [role]
            if dep_id is not None:
                q += " AND e.department_id=?"
                args.append(dep_id)
            cur = await db.execute(q + " ORDER BY LOWER(e.first_name)", args)
            return [await _row_to_emp(r) for r in await cur.fetchall()]
    except Exception:
        return []


async def all_roles():
    out = []
    for role in ("manager", "head"):
        for e in await role_holders(role):
            out.append((role, e))
    return out


# ==================== So'rov xabarlari (kimga yuborilgan) ====================
async def add_exreq_message(req_id, chat_id, message_id, text):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS exreq_messages (req_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
                   message_id INTEGER NOT NULL, text TEXT)""")
        await db.execute("INSERT INTO exreq_messages(req_id,chat_id,message_id,text) VALUES(?,?,?,?)",
                         (req_id, chat_id, message_id, text))
        await db.commit()


async def exreq_messages_for(req_id):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT chat_id, message_id, text FROM exreq_messages WHERE req_id=?",
                                   (req_id,))
            return [{"chat_id": r[0], "message_id": r[1], "text": r[2]} for r in await cur.fetchall()]
    except Exception:
        return []


# ==================== Excel'dan kirish/chiqish to'ldirish ====================
def _name_key(name):
    """Ism kaliti: kichik harf, apostroflarsiz, so'zlar tartibsiz ('Diyora Y.U' == 'Y.U Diyora')."""
    s = str(name or "").lower()
    for ch in "'`ʻʼ’‘":
        s = s.replace(ch, "")
    return " ".join(sorted(s.split()))


async def employees_by_name_key():
    """{ism_kaliti: [xodimlar]} — faqat aniq moslik uchun."""
    out = {}
    for e in await list_employees():
        out.setdefault(_name_key(full_name(e)), []).append(e)
    return out


async def fill_day_from_excel(emp_id, day, kelish, ketish):
    """Bot yozmagan turini Excel'dan to'ldiradi. Bot yozgan (yoki qo'lda kiritilgan) qayd o'zgarmaydi.
    Qaytaradi: {'in': holat, 'out': holat}; holat: 'new' | 'updated' | 'same' | 'bot' | None."""
    res = {"in": None, "out": None}
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT event_type, external_id, ts FROM events WHERE employee_id=? AND day=?", (emp_id, day))
        rows = await cur.fetchall()
        own = {t for t, ext, _ in rows if not str(ext or "").startswith("xls-")}
        xls = {ext: ts for _, ext, ts in rows if str(ext or "").startswith("xls-")}
        for etype, hm in (("in", kelish), ("out", ketish)):
            if not hm:
                continue
            if etype in own:
                res[etype] = "bot"
                continue
            ext = f"xls-{emp_id}-{day}-{etype}"
            ts = f"{day}T{hm}:00"
            if ext in xls:
                if xls[ext] == ts:
                    res[etype] = "same"
                    continue
                await db.execute("UPDATE events SET ts=? WHERE external_id=?", (ts, ext))
                res[etype] = "updated"
            else:
                await db.execute(
                    "INSERT INTO events (employee_id,event_type,ts,day,external_id) VALUES (?,?,?,?,?)",
                    (emp_id, etype, ts, day, ext))
                res[etype] = "new"
        await db.commit()
    return res
