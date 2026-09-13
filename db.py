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
            """
        )
        # Migratsiya: employees jadvaliga department_id ustunini qo'shamiz (bo'lmasa)
        cur = await db.execute("PRAGMA table_info(employees)")
        cols = [r[1] for r in await cur.fetchall()]
        if "department_id" not in cols:
            await db.execute("ALTER TABLE employees ADD COLUMN department_id INTEGER")
        await db.commit()


# ---------------- Xodimlar ----------------

async def add_employee(first_name, last_name, phone, faceid_user_id,
                       work_start=None, work_end=None, grace_minutes=None):
    phone = normalize_phone(phone)
    work_start = work_start or DEFAULT_WORK_START
    work_end = work_end or DEFAULT_WORK_END
    grace = GRACE_MINUTES if grace_minutes is None else grace_minutes
    # FaceID ID ixtiyoriy (guruh o'qishda ism bo'yicha topiladi)
    fid = None if faceid_user_id in (None, "", "-") else str(faceid_user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO employees
               (first_name,last_name,phone,faceid_user_id,work_start,work_end,
                grace_minutes,count_late,active,created_at)
               VALUES (?,?,?,?,?,?,?,1,1,?)""",
            (first_name, last_name, phone, fid, work_start,
             work_end, grace, now_local().isoformat()),
        )
        await db.commit()
        return cur.lastrowid


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
        q += " ORDER BY last_name, first_name"
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
        q += " ORDER BY last_name, first_name"
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
        q += " ORDER BY last_name, first_name"
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
