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
            """
        )
        await db.commit()


# ---------------- Xodimlar ----------------

async def add_employee(first_name, last_name, phone, faceid_user_id,
                       work_start=None, work_end=None, grace_minutes=None):
    phone = normalize_phone(phone)
    work_start = work_start or DEFAULT_WORK_START
    work_end = work_end or DEFAULT_WORK_END
    grace = GRACE_MINUTES if grace_minutes is None else grace_minutes
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO employees
               (first_name,last_name,phone,faceid_user_id,work_start,work_end,
                grace_minutes,count_late,active,created_at)
               VALUES (?,?,?,?,?,?,?,1,1,?)""",
            (first_name, last_name, phone, str(faceid_user_id), work_start,
             work_end, grace, now_local().isoformat()),
        )
        await db.commit()
        return cur.lastrowid


async def _row_to_emp(row):
    if not row:
        return None
    keys = ["id", "first_name", "last_name", "phone", "faceid_user_id",
            "telegram_id", "work_start", "work_end", "grace_minutes",
            "count_late", "active", "created_at"]
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
