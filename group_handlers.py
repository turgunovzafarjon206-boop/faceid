"""Guruh buyruqlari: bot guruhga qo'shilib ADMIN qilinsa, javobni o'sha guruhga yuboradi.

  /jarima <filial> [oy]   — filial xodimlarining shu oydagi jarimalari
  /jamoa  <filial>        — filial xodimlari ro'yxati

Oy ko'rinishlari: sentyabr | sentyabr 2026 | 09.2026 | 2026-09 | (yozilmasa — joriy oy)

Kim ishlata oladi: bot adminlari va guruh adminlari.
Hamma a'zolarga ochish uchun Railway Variables: GROUP_CMD_ALL = 1
"""
import os
import re
import datetime as dt

from aiogram import Router, F
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import db
import reports
from config import TZ

router = Router()

ALLOW_ALL = os.getenv("GROUP_CMD_ALL", "").strip() == "1"
_ADMIN_STATUSES = (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)

UZ_MONTH_KEYS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6,
    "iyul": 7, "avgust": 8, "sentyabr": 9, "oktyabr": 10, "noyabr": 11, "dekabr": 12,
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}


def _norm(s):
    s = str(s).lower()
    for ch in "'`ʻʼ’‘":
        s = s.replace(ch, "")
    return " ".join(s.split())


def _month_from_word(w):
    w = _norm(w)
    if len(w) < 3:
        return None
    hits = {m for k, m in UZ_MONTH_KEYS.items() if k.startswith(w) or w.startswith(k)}
    return hits.pop() if len(hits) == 1 else None


def parse_branch_and_month(args):
    """'Uchtepa filiali sentyabr 2026' -> ('Uchtepa filiali', '2026-09')."""
    toks = (args or "").split()
    now = dt.datetime.now(TZ)
    year, month = None, None
    if toks:
        t = toks[-1]
        m1 = re.fullmatch(r"(\d{1,2})[./-](20\d{2})", t)          # 09.2026
        m2 = re.fullmatch(r"(20\d{2})[./-](\d{1,2})", t)          # 2026-09
        if m1 and 1 <= int(m1.group(1)) <= 12:
            month, year = int(m1.group(1)), int(m1.group(2)); toks.pop()
        elif m2 and 1 <= int(m2.group(2)) <= 12:
            year, month = int(m2.group(1)), int(m2.group(2)); toks.pop()
        else:
            if re.fullmatch(r"20\d{2}", t) and len(toks) >= 2:  # ... sentyabr 2026
                year = int(t); toks.pop()
            if toks:
                mw = _month_from_word(toks[-1])
                if mw:
                    month = mw; toks.pop()
                elif year is not None:                          # yil bor, oy yo'q — qaytaramiz
                    toks.append(str(year)); year = None
    if month is None:
        month, year = now.month, now.year
    elif year is None:
        year = now.year
    return " ".join(toks).strip(), f"{year}-{month:02d}"


async def find_branch(query):
    """Qaytaradi: (branch | None, variantlar_ro'yxati)."""
    branches = await db.list_branches()
    q = _norm(query)
    if not q:
        return None, branches
    strip_w = lambda s: _norm(s).replace("filiali", "").replace("filial", "").strip()
    exact = [b for b in branches if _norm(b["name"]) == q or strip_w(b["name"]) == strip_w(q)]
    if len(exact) == 1:
        return exact[0], []
    part = [b for b in branches
            if q in _norm(b["name"]) or (strip_w(q) and strip_w(q) in _norm(b["name"]))]
    if len(part) == 1:
        return part[0], []
    return None, (part or branches)


async def _allowed(msg: Message):
    """Bot guruhda admin bo'lishi va chaqiruvchi ruxsatga ega bo'lishi kerak."""
    import admin_handlers
    if msg.chat.type == ChatType.PRIVATE:
        if admin_handlers.is_admin(msg.from_user.id):
            return True
        await msg.answer("⛔ Bu buyruq faqat adminlar uchun.")
        return False
    try:
        me = await msg.bot.get_chat_member(msg.chat.id, msg.bot.id)
        if me.status not in _ADMIN_STATUSES:
            await msg.answer("⚠️ Buyruqlar ishlashi uchun meni bu guruhda ADMIN qiling.")
            return False
    except Exception:
        return False
    if ALLOW_ALL or admin_handlers.is_admin(msg.from_user.id):
        return True
    try:
        who = await msg.bot.get_chat_member(msg.chat.id, msg.from_user.id)
        if who.status in _ADMIN_STATUSES:
            return True
    except Exception:
        pass
    await msg.answer("⛔ Bu buyruq faqat guruh adminlari uchun.")
    return False


def _branch_hint(variants, cmd):
    if not variants:
        return "❌ Hali birorta filial yaratilmagan."
    names = "\n".join(f"• {b['name']}" for b in variants[:30])
    return (f"Filialni aniqlab bo'lmadi. Mavjud filiallar:\n{names}\n\n"
            f"Misol: <code>/{cmd} {variants[0]['name']}</code>")


async def _send_long(msg, text):
    for i in range(0, len(text), 3900):
        await msg.answer(text[i:i + 3900])


@router.message(Command("jarima"))
async def cmd_jarima(msg: Message, command: CommandObject):
    if not await _allowed(msg):
        return
    query, ym = parse_branch_and_month(command.args)
    branch, variants = await find_branch(query)
    if not branch:
        await msg.answer(_branch_hint(variants, "jarima") +
                         " sentyabr\n(oy yozilmasa — joriy oy)")
        return
    first, last = reports.month_bounds(ym)
    y, m = ym.split("-")
    title = f"{reports.UZ_MONTHS[int(m)]} {y}"
    emps = await db.branch_members(branch["id"])
    if not emps:
        await msg.answer(f"🏬 {branch['name']}: xodim yo'q.")
        return
    wait = await msg.answer("⏳ Hisoblanmoqda...")
    rows, clean = [], []
    grand = 0
    for e in emps:
        if not e["count_late"]:
            continue
        series = await reports._late_series(e, first, last)
        _, total = reports._apply_fines(series)
        late_days = sum(1 for _, _, l in series if l > 0)
        late_min = sum(l for _, _, l in series)
        if total > 0:
            rows.append((total, db.full_name(e), late_days, late_min))
            grand += total
        else:
            clean.append(db.full_name(e))
    rows.sort(reverse=True)
    lines = [f"💰 <b>Jarimalar — {branch['name']}</b>", f"🗓 {title}\n"]
    for i, (total, name, ld, lm) in enumerate(rows, 1):
        lines.append(f"{i}. {name} — <b>{reports.fmt_sum(total)} so'm</b> "
                     f"({ld} kun, {lm} daq)")
    if not rows:
        lines.append("Bu oyda jarima yo'q ✅")
    lines.append(f"\n💵 Jami: <b>{reports.fmt_sum(grand)} so'm</b> "
                 f"({len(rows)} ta xodim)")
    if clean:
        lines.append(f"✅ Jarimasiz: {len(clean)} ta — " + ", ".join(clean[:40]))
    try:
        await wait.delete()
    except Exception:
        pass
    await _send_long(msg, "\n".join(lines))


@router.message(Command("jamoa"))
async def cmd_jamoa(msg: Message, command: CommandObject):
    if not await _allowed(msg):
        return
    branch, variants = await find_branch(command.args or "")
    if not branch:
        await msg.answer(_branch_hint(variants, "jamoa"))
        return
    emps = await db.branch_members(branch["id"])
    if not emps:
        await msg.answer(f"🏬 {branch['name']}: xodim yo'q.")
        return
    deps = {}
    lines = [f"👥 <b>{branch['name']}</b> — {len(emps)} ta xodim\n"]
    for i, e in enumerate(emps, 1):
        dep = ""
        if e.get("department_id"):
            if e["department_id"] not in deps:
                d = await db.get_department(e["department_id"])
                deps[e["department_id"]] = d["name"] if d else ""
            dep = deps[e["department_id"]]
        link = "🟢" if e["telegram_id"] else "🔴"
        extra = f" — {dep}" if dep else ""
        lines.append(f"{i}. {link} {db.full_name(e)}{extra} ({e['work_start']}-{e['work_end']})")
    linked = sum(1 for e in emps if e["telegram_id"])
    lines.append(f"\n🟢 Botga ulangan: {linked} | 🔴 Ulanmagan: {len(emps) - linked}")
    await _send_long(msg, "\n".join(lines))
