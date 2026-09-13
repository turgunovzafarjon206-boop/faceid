"""Admin panel: FaceID boshqarish (sozlama+Excel hisobot), Ma'lumotlar, Xabar."""
import datetime as dt
import calendar
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import db
import reports
import faceid
import keyboards as kb
from config import ADMIN_IDS, TZ

router = Router()

# Bot orqali qo'shilgan adminlar (xotirada, startda yuklanadi)
EXTRA_ADMINS = set()


def is_super(uid) -> bool:
    """Asosiy admin (env ADMIN_IDS) — faqat ular admin qo'sha/o'chira oladi."""
    return uid in ADMIN_IDS


def is_admin(uid) -> bool:
    return uid in ADMIN_IDS or uid in EXTRA_ADMINS


async def load_admins():
    global EXTRA_ADMINS
    try:
        EXTRA_ADMINS = set(await db.list_admin_ids())
    except Exception:
        EXTRA_ADMINS = set()


class AddEmp(StatesGroup):
    first = State()
    last = State()
    phone = State()
    faceid = State()
    schedule = State()
    department = State()


class HRReply(StatesGroup):
    wait = State()


class EditEmp(StatesGroup):
    value = State()


class FaceIDSet(StatesGroup):
    value = State()


class AdminReport(StatesGroup):
    period = State()


class Broadcast(StatesGroup):
    content = State()


class DeptState(StatesGroup):
    name = State()


class TplState(StatesGroup):
    value = State()


class ReminderState(StatesGroup):
    text = State()


class AdminAdd(StatesGroup):
    value = State()


class RestoreState(StatesGroup):
    wait_file = State()


def _month_range():
    now = dt.datetime.now(TZ)
    first = now.replace(day=1).strftime("%Y-%m-%d")
    last = now.replace(day=calendar.monthrange(now.year, now.month)[1]).strftime("%Y-%m-%d")
    return first, last


# ==================== Asosiy menyu ====================
@router.message(Command("admin"))
async def admin_entry(msg: Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("⛔ Sizda ruxsat yo'q.")
        return
    await msg.answer("🔐 Admin panel", reply_markup=kb.admin_menu())


@router.message(F.text == "🔙 Oddiy menyu")
async def back_normal(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer("Oddiy menyu", reply_markup=kb.user_menu())


@router.message(F.text == "📷 FaceID boshqarish")
async def m_faceid_manage(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer("📷 FaceID boshqarish:", reply_markup=kb.admin_faceid_kb())


@router.message(F.text == "👥 Ma'lumotlar")
async def m_data(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer("👥 Ma'lumotlar:", reply_markup=kb.admin_data_kb())


@router.message(F.text == "✉️ Xabar")
async def m_message(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(Broadcast.content)
    await msg.answer("✉️ Yubormoqchi bo'lgan xabaringizni yuboring — "
                     "matn, rasm (izoh bilan) yoki video bo'lishi mumkin.")


@router.message(F.text == "🏢 Bo'limlar")
async def m_departments(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer("🏢 Bo'limlar boshqaruvi:", reply_markup=kb.dep_manage_kb())


@router.message(F.text == "🔔 Eslatma")
async def m_reminder(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer(
            "🔔 Ma'lumot to'ldirmaganlar (botga /start bosmagan xodimlar) uchun eslatma.",
            reply_markup=kb.reminder_kb())


# ==================== Ma'lumotlar: Xodim qo'shish ====================
@router.callback_query(F.data == "a:addemp")
async def add_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(AddEmp.first)
    await cb.message.answer("Ism kiriting:")
    await cb.answer()


@router.message(AddEmp.first, F.text)
async def add_first(msg: Message, state: FSMContext):
    await state.update_data(first=msg.text.strip())
    await state.set_state(AddEmp.last)
    await msg.answer("Familiya kiriting:")


@router.message(AddEmp.last, F.text)
async def add_last(msg: Message, state: FSMContext):
    await state.update_data(last=msg.text.strip())
    await state.set_state(AddEmp.phone)
    await msg.answer("Telefon raqam (masalan 901234567):")


@router.message(AddEmp.phone, F.text)
async def add_phone(msg: Message, state: FSMContext):
    await state.update_data(phone=msg.text.strip())
    await state.set_state(AddEmp.faceid)
    await msg.answer("FaceID ID (ixtiyoriy).\nGuruhdan ism bo'yicha topiladi, "
                     "shuning uchun kerak bo'lmasa - (chiziqcha) yuboring:")


@router.message(AddEmp.faceid, F.text)
async def add_faceid(msg: Message, state: FSMContext):
    await state.update_data(faceid=msg.text.strip())
    await state.set_state(AddEmp.schedule)
    await msg.answer("Ish grafigi (format: 08:00-18:00):")


@router.message(AddEmp.schedule, F.text)
async def add_schedule(msg: Message, state: FSMContext):
    try:
        ws, we = msg.text.strip().split("-")
        dt.datetime.strptime(ws.strip(), "%H:%M")
        dt.datetime.strptime(we.strip(), "%H:%M")
    except ValueError:
        await msg.answer("❌ Format noto'g'ri. Masalan: 08:00-18:00")
        return
    await state.update_data(ws=ws.strip(), we=we.strip())
    deps = await db.list_departments()
    if not deps:
        await _create_employee(msg, state, dep_id=None)
    else:
        await state.set_state(AddEmp.department)
        await msg.answer("Bo'limni tanlang:", reply_markup=kb.add_dep_pick_kb(deps))


@router.callback_query(AddEmp.department, F.data.startswith("adddep:"))
async def add_pick_dep(cb: CallbackQuery, state: FSMContext):
    dep_id = int(cb.data.split(":")[1]) or None
    await _create_employee(cb.message, state, dep_id=dep_id)
    await cb.answer()


async def _create_employee(target, state: FSMContext, dep_id):
    data = await state.get_data()
    try:
        emp_id = await db.add_employee(
            data["first"], data["last"], data["phone"], data["faceid"],
            work_start=data["ws"], work_end=data["we"])
    except Exception as e:
        await target.answer(f"❌ Xatolik (telefon yoki FaceID ID takrorlangan bo'lishi mumkin):\n{e}")
        await state.clear()
        return
    if dep_id:
        await db.set_employee_department(emp_id, dep_id)
    dep_name = ""
    if dep_id:
        d = await db.get_department(dep_id)
        dep_name = f"\n🏢 Bo'lim: {d['name']}" if d else ""
    await state.clear()
    await target.answer(
        f"✅ Xodim qo'shildi!\n\n👤 {data['first']} {data['last']}\n"
        f"📞 {data['phone']}\n🆔 FaceID: {data['faceid']}\n"
        f"🕐 {data['ws']}-{data['we']}{dep_name}\n\n"
        f"Endi xodim botga /start bosib, shu raqam bilan kirsin.",
        reply_markup=kb.admin_menu())


# ==================== Ma'lumotlar: Xodimlarni boshqarish ====================
@router.callback_query(F.data == "a:listemp")
async def list_emps(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    emps = await db.list_employees()
    if not emps:
        await cb.message.answer("Hozircha xodim yo'q.")
    else:
        await cb.message.answer("Xodimni tanlang:", reply_markup=kb.employees_kb(emps))
    await cb.answer()


@router.callback_query(F.data.startswith("emp:"))
async def show_emp(cb: CallbackQuery):
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    if not emp:
        return await cb.answer("Topilmadi", show_alert=True)
    bound = "✅ ulangan" if emp["telegram_id"] else "❌ ulanmagan"
    await cb.message.answer(
        f"👤 {emp['first_name']} {emp['last_name']}\n📞 {emp['phone']}\n"
        f"🆔 FaceID: {emp['faceid_user_id']}\n🕐 {emp['work_start']}-{emp['work_end']}\n"
        f"⏰ Kechikish: {'hisoblanadi' if emp['count_late'] else 'hisoblanmaydi'}\n"
        f"📲 Telegram: {bound}",
        reply_markup=kb.employee_manage_kb(emp))
    await cb.answer()


@router.callback_query(F.data.startswith("togglelate:"))
async def toggle_late(cb: CallbackQuery):
    emp_id = int(cb.data.split(":")[1])
    emp = await db.get_employee_by_id(emp_id)
    new = 0 if emp["count_late"] else 1
    await db.update_employee(emp_id, count_late=new)
    emp = await db.get_employee_by_id(emp_id)
    await cb.answer("Yangilandi ✅")
    try:
        await cb.message.edit_reply_markup(reply_markup=kb.employee_manage_kb(emp))
    except Exception:
        await cb.message.answer(f"Kechikish endi {'hisoblanadi' if new else 'hisoblanmaydi'}.",
                                reply_markup=kb.employee_manage_kb(emp))


@router.callback_query(F.data.startswith("deactivate:"))
async def deactivate(cb: CallbackQuery):
    await db.update_employee(int(cb.data.split(":")[1]), active=0)
    await cb.answer("Nofaol qilindi")
    await cb.message.answer("🗑 Xodim nofaol holatga o'tkazildi.")


@router.callback_query(F.data.startswith("report:"))
async def emp_report(cb: CallbackQuery):
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    first, last = _month_range()
    await cb.message.answer(await reports.period_text(emp, first, last, "Oylik hisobot"))
    await cb.answer()


@router.callback_query(F.data.startswith("edit:"))
async def edit_field(cb: CallbackQuery, state: FSMContext):
    _, field, emp_id = cb.data.split(":")
    await state.set_state(EditEmp.value)
    await state.update_data(field=field, emp_id=int(emp_id))
    prompts = {
        "name": "Yangi Ism va Familiya (masalan: Ali Valiyev):",
        "phone": "Yangi telefon raqam (901234567):",
        "faceid": "Yangi FaceID ID:",
        "schedule": "Yangi ish grafigi (08:00-18:00):",
    }
    await cb.message.answer(prompts.get(field, "Yangi qiymat:"))
    await cb.answer()


@router.message(EditEmp.value, F.text)
async def save_edit(msg: Message, state: FSMContext):
    data = await state.get_data()
    field, emp_id, val = data["field"], data["emp_id"], msg.text.strip()
    try:
        if field == "name":
            parts = val.split()
            await db.update_employee(emp_id, first_name=parts[0],
                                     last_name=" ".join(parts[1:]) or parts[0])
        elif field == "phone":
            await db.update_employee(emp_id, phone=val)
        elif field == "faceid":
            await db.update_employee(emp_id, faceid_user_id=val)
        elif field == "schedule":
            ws, we = val.split("-")
            dt.datetime.strptime(ws.strip(), "%H:%M")
            dt.datetime.strptime(we.strip(), "%H:%M")
            await db.update_employee(emp_id, work_start=ws.strip(), work_end=we.strip())
    except Exception as e:
        await msg.answer(f"❌ Xatolik: {e}")
        return
    await state.clear()
    emp = await db.get_employee_by_id(emp_id)
    await msg.answer("✅ Saqlandi.", reply_markup=kb.admin_menu())
    await msg.answer(f"👤 {emp['first_name']} {emp['last_name']} yangilandi.",
                     reply_markup=kb.employee_manage_kb(emp))


# ==================== FaceID boshqarish: Hisobot (Excel) ====================
@router.callback_query(F.data == "a:report")
async def report_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await cb.message.answer("Qaysi davr uchun Excel hisobot?", reply_markup=kb.admin_report_kb())
    await cb.answer()


async def _send_excel(target, day_from, day_to, title):
    emps = await db.list_employees()
    if not emps:
        await target.answer("Xodim yo'q.")
        return
    path = await reports.build_period_excel(emps, day_from, day_to, title)
    await target.answer_document(
        FSInputFile(path, filename=f"{title.replace(' ', '_')}_{day_from}_{day_to}.xlsx"),
        caption=f"📊 {title}\n{day_from} … {day_to}")


@router.callback_query(F.data == "arep:today")
async def rep_today(cb: CallbackQuery):
    day = dt.datetime.now(TZ).strftime("%Y-%m-%d")
    await cb.answer("Tayyorlanmoqda...")
    await _send_excel(cb.message, day, day, "Kunlik hisobot")


@router.callback_query(F.data == "arep:month")
async def rep_month(cb: CallbackQuery):
    first, last = _month_range()
    await cb.answer("Tayyorlanmoqda...")
    await _send_excel(cb.message, first, last, "Oylik hisobot")


@router.callback_query(F.data == "arep:period")
async def rep_period(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminReport.period)
    await cb.message.answer("Davrni yuboring (YYYY-MM-DD YYYY-MM-DD):\n"
                            "Masalan: 2026-08-01 2026-08-31")
    await cb.answer()


@router.message(AdminReport.period, F.text)
async def rep_period_got(msg: Message, state: FSMContext):
    parts = msg.text.strip().split()
    try:
        d1 = dt.datetime.strptime(parts[0], "%Y-%m-%d").strftime("%Y-%m-%d")
        d2 = dt.datetime.strptime(parts[1], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        await msg.answer("❌ Noto'g'ri format. Masalan: 2026-08-01 2026-08-31")
        return
    await state.clear()
    if d1 > d2:
        d1, d2 = d2, d1
    await msg.answer("⏳ Excel tayyorlanmoqda...")
    await _send_excel(msg, d1, d2, "Davr hisoboti")


@router.callback_query(F.data == "a:today")
async def today_status(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    emps = await db.list_employees()
    day = dt.datetime.now(TZ).strftime("%Y-%m-%d")
    lines = [f"📋 Bugungi holat ({day}):\n"]
    for emp in emps:
        events = await db.events_for_day(emp["id"], day)
        r = reports.compute_day(emp, events)
        if not r:
            lines.append(f"• {emp['first_name']} {emp['last_name']}: qayd yo'q")
            continue
        kirish = r["kirish"].strftime("%H:%M") if r["kirish"] else "—"
        chiqish = r["chiqish"].strftime("%H:%M") if r["chiqish"] else "—"
        late = f" ⏰+{r['kechikish_min']}daq" if r["kech_qoldi"] else ""
        lines.append(f"• {emp['first_name']} {emp['last_name']}: "
                     f"{kirish}–{chiqish} | {reports.fmt_duration(r['ishlangan_min'])}{late}")
    await cb.message.answer("\n".join(lines) if len(lines) > 1 else "Xodim yo'q.")
    await cb.answer()


# ==================== FaceID boshqarish: Qurilma sozlamalari ====================
def _mask(v):
    if not v:
        return "—"
    return v[:3] + "***" if len(v) > 4 else "***"


async def _faceid_status_text():
    s = await faceid.effective_settings()
    return ("⚙️ FaceID qurilma sozlamalari\n\n"
            f"🔧 Rejim: {s['mode']}\n🌐 URL: {s['url'] or '—'}\n"
            f"🔑 Token: {_mask(s['token'])}\n👤 Login: {s['user'] or '—'}\n"
            f"🔒 Parol: {_mask(s['pass'])}\n⏱ Interval: {s['interval']} soniya\n\n"
            "O'zgartirish uchun tugmani bosing:")


@router.callback_query(F.data == "a:fset")
async def faceid_settings(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    s = await faceid.effective_settings()
    await cb.message.answer(await _faceid_status_text(), reply_markup=kb.faceid_settings_kb(s["mode"]))
    await cb.answer()


@router.callback_query(F.data == "fset:mode")
async def fset_mode(cb: CallbackQuery):
    await cb.message.answer("Rejimni tanlang:", reply_markup=kb.faceid_mode_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("fmode:"))
async def fset_mode_pick(cb: CallbackQuery):
    mode = cb.data.split(":")[1]
    await db.set_setting("faceid_mode", mode)
    await cb.answer("Rejim saqlandi ✅")
    await cb.message.answer(await _faceid_status_text(), reply_markup=kb.faceid_settings_kb(mode))


_FIELD_PROMPTS = {
    "url": ("faceid_url", "API manzilini yuboring (masalan https://api.qurilma.uz/events):"),
    "token": ("faceid_token", "Token yuboring (yo'q bo'lsa - deb yozing):"),
    "user": ("faceid_user", "Login yuboring:"),
    "pass": ("faceid_pass", "Parol yuboring:"),
    "interval": ("faceid_interval", "Necha soniyada bir tekshirilsin? (masalan 15):"),
}


@router.callback_query(F.data.startswith("fset:"))
async def fset_field(cb: CallbackQuery, state: FSMContext):
    field = cb.data.split(":")[1]
    if field == "test":
        return await _test_connection(cb)
    if field == "mode":
        return
    key, prompt = _FIELD_PROMPTS[field]
    await state.set_state(FaceIDSet.value)
    await state.update_data(key=key)
    await cb.message.answer(prompt)
    await cb.answer()


@router.message(FaceIDSet.value, F.text)
async def fset_save(msg: Message, state: FSMContext):
    data = await state.get_data()
    key, val = data["key"], msg.text.strip()
    if key == "faceid_token" and val == "-":
        val = ""
    if key == "faceid_interval":
        try:
            val = str(max(5, int(val)))
        except ValueError:
            await msg.answer("❌ Raqam kiriting, masalan 15.")
            return
    await db.set_setting(key, val)
    await state.clear()
    await msg.answer("✅ Saqlandi.")
    s = await faceid.effective_settings()
    await msg.answer(await _faceid_status_text(), reply_markup=kb.faceid_settings_kb(s["mode"]))


async def _test_connection(cb: CallbackQuery):
    await cb.answer("Tekshirilyapti...")
    try:
        client, _ = await faceid.build_client()
        since = dt.datetime.now(TZ) - dt.timedelta(days=1)
        events = await client.fetch_events(since)
        if not events:
            await cb.message.answer(
                "🔌 Ulanish ishladi, lekin oxirgi 1 kunda hodisa topilmadi.\n"
                "(Rejim 'mock' bo'lsa bu normal.)")
            return
        lines = ["✅ Ulanish muvaffaqiyatli! Oxirgi hodisalar:\n"]
        for e in events[-5:]:
            lines.append(f"• FaceID ID: {e['faceid_user_id']} | "
                         f"{e['ts'].strftime('%Y-%m-%d %H:%M')} | {e.get('event_type') or 'avto'}")
        lines.append("\n💡 Bu ID'larni xodim qo'shishda ishlating.")
        await cb.message.answer("\n".join(lines))
    except Exception as e:
        await cb.message.answer(f"❌ Ulanishda xatolik:\n{e}\n\nURL, token yoki rejimni tekshiring.")


# ==================== Xabar (broadcast: matn/rasm/video + qabul qiluvchi) ====================
@router.message(Broadcast.content)
async def bcast_got_content(msg: Message, state: FSMContext):
    kind = None
    payload = {}
    if msg.photo:
        kind = "photo"
        payload = {"file_id": msg.photo[-1].file_id, "caption": msg.caption or ""}
    elif msg.video:
        kind = "video"
        payload = {"file_id": msg.video.file_id, "caption": msg.caption or ""}
    elif msg.text:
        kind = "text"
        payload = {"text": msg.text}
    else:
        await msg.answer("Faqat matn, rasm yoki video yuboring.")
        return
    await state.update_data(kind=kind, payload=payload)
    deps = await db.list_departments()
    await msg.answer("Kimga yuborilsin?", reply_markup=kb.recipients_kb(deps, "bcto"))


async def _recipients(target):
    """target: 'all' yoki ('dep', id)"""
    if target == "all":
        return await db.linked_employees()
    return await db.linked_employees(dep_id=target[1])


@router.callback_query(F.data.startswith("bcto:"))
async def bcast_send(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kind = data.get("kind")
    payload = data.get("payload", {})
    if not kind:
        await cb.answer("Avval xabar yuboring", show_alert=True)
        return

    parts = cb.data.split(":")
    if parts[1] == "all":
        recips = await _recipients("all")
        target_name = "hammaga"
    else:  # bcto:d:<id>
        dep_id = int(parts[2])
        recips = await _recipients(("dep", dep_id))
        dep = await db.get_department(dep_id)
        target_name = dep["name"] if dep else "bo'lim"

    await state.clear()
    await cb.answer("Yuborilmoqda...")
    ok = fail = 0
    for emp in recips:
        try:
            cid = emp["telegram_id"]
            if kind == "text":
                await cb.bot.send_message(cid, payload["text"])
            elif kind == "photo":
                await cb.bot.send_photo(cid, payload["file_id"], caption=payload["caption"] or None)
            elif kind == "video":
                await cb.bot.send_video(cid, payload["file_id"], caption=payload["caption"] or None)
            ok += 1
        except Exception:
            fail += 1
    await cb.message.answer(f"✅ Yuborildi ({target_name}): {ok} ta\n❌ Yuborilmadi: {fail} ta",
                            reply_markup=kb.admin_menu())


# ==================== Bo'limlar (departments) ====================
@router.callback_query(F.data == "dep:add")
async def dep_add(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(DeptState.name)
    await cb.message.answer("Yangi bo'lim nomini yozing (masalan: Sotuv bo'limi):")
    await cb.answer()


@router.message(DeptState.name, F.text)
async def dep_add_save(msg: Message, state: FSMContext):
    dep_id = await db.add_department(msg.text.strip())
    await state.clear()
    if dep_id:
        await msg.answer(f"✅ Bo'lim qo'shildi: {msg.text.strip()}", reply_markup=kb.dep_manage_kb())
    else:
        await msg.answer("❌ Bunday bo'lim allaqachon bor.", reply_markup=kb.dep_manage_kb())


@router.callback_query(F.data == "dep:list")
async def dep_list(cb: CallbackQuery):
    deps = await db.list_departments()
    if not deps:
        await cb.message.answer("Hozircha bo'lim yo'q.")
    else:
        total = sum(d["count"] for d in deps)
        await cb.message.answer(f"🏢 Bo'limlar (jami xodim: {total}). Tanlang:",
                                reply_markup=kb.departments_kb(deps, "depshow"))
    await cb.answer()


@router.callback_query(F.data.startswith("depshow:"))
async def dep_show(cb: CallbackQuery):
    dep_id = int(cb.data.split(":")[1])
    dep = await db.get_department(dep_id)
    members = await db.department_members(dep_id)
    lines = [f"🏢 {dep['name']} — {len(members)} ta xodim\n"]
    for m in members:
        link = "✅" if m["telegram_id"] else "⛔"
        lines.append(f"{link} {m['first_name']} {m['last_name']} ({m['phone']})")
    await cb.message.answer("\n".join(lines), reply_markup=kb.dep_actions_kb(dep_id))
    await cb.answer()


@router.callback_query(F.data.startswith("depmem:"))
async def dep_members(cb: CallbackQuery):
    await dep_show(cb)


@router.callback_query(F.data.startswith("depdel:"))
async def dep_delete(cb: CallbackQuery):
    dep_id = int(cb.data.split(":")[1])
    await db.delete_department(dep_id)
    await cb.answer("O'chirildi")
    await cb.message.answer("🗑 Bo'lim o'chirildi (xodimlar bo'limsiz qoldi).",
                            reply_markup=kb.dep_manage_kb())


# Xodimga bo'lim tayinlash (xodim boshqarish oynasidan)
@router.callback_query(F.data.startswith("empdep:"))
async def emp_dep_choose(cb: CallbackQuery):
    emp_id = int(cb.data.split(":")[1])
    deps = await db.list_departments()
    if not deps:
        await cb.answer("Avval bo'lim qo'shing", show_alert=True)
        return
    await cb.message.answer("Bo'limni tanlang:", reply_markup=kb.emp_department_kb(deps, emp_id))
    await cb.answer()


@router.callback_query(F.data.startswith("setdep:"))
async def emp_dep_set(cb: CallbackQuery):
    _, emp_id, dep_id = cb.data.split(":")
    dep_id = int(dep_id)
    await db.set_employee_department(int(emp_id), dep_id if dep_id else None)
    await cb.answer("Saqlandi ✅")
    await cb.message.answer("🏢 Bo'lim yangilandi.")


# ==================== Bildirishnoma matnlari (templates) ====================
@router.callback_query(F.data == "a:tpl")
async def tpl_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    tin = await db.get_template("tpl_in", db.DEFAULT_TPL_IN)
    tout = await db.get_template("tpl_out", db.DEFAULT_TPL_OUT)
    twarn = await db.get_template("tpl_warn", db.DEFAULT_TPL_WARN)
    tsurv = await db.get_template("tpl_survey", db.DEFAULT_TPL_SURVEY)
    await cb.message.answer(
        "📝 Bildirishnoma matnlari.\n\n"
        "Belgilar: {name} {time} {date} {worked} {late} {late_min}\n\n"
        f"🟢 KIRISH:\n{tin}\n\n🔴 CHIQISH:\n{tout}\n\n"
        f"⚠️ OGOHLANTIRISH:\n{twarn}\n\n📊 SO'ROVNOMA:\n{tsurv}",
        reply_markup=kb.templates_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("tpl:"))
async def tpl_action(cb: CallbackQuery, state: FSMContext):
    what = cb.data.split(":")[1]
    if what == "reset":
        await db.set_setting("tpl_in", db.DEFAULT_TPL_IN)
        await db.set_setting("tpl_out", db.DEFAULT_TPL_OUT)
        await db.set_setting("tpl_warn", db.DEFAULT_TPL_WARN)
        await db.set_setting("tpl_survey", db.DEFAULT_TPL_SURVEY)
        await cb.answer("Standartga qaytarildi ✅")
        await cb.message.answer("↩️ Barcha matnlar standart holatga qaytarildi.")
        return
    keymap = {"in": "tpl_in", "out": "tpl_out", "warn": "tpl_warn", "survey": "tpl_survey"}
    await state.set_state(TplState.value)
    await state.update_data(which=keymap.get(what, "tpl_in"))
    await cb.message.answer("Yangi matnni yuboring (belgilar: {name} {time} {date} {worked} {late}):")
    await cb.answer()


@router.message(TplState.value, F.text)
async def tpl_save(msg: Message, state: FSMContext):
    data = await state.get_data()
    await db.set_setting(data["which"], msg.text)
    await state.clear()
    await msg.answer("✅ Matn saqlandi.", reply_markup=kb.admin_menu())


# ==================== Eslatma (to'ldirmaganlar) ====================
@router.callback_query(F.data == "rem:list")
async def rem_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    unlinked = await db.unlinked_employees()
    unknown = await db.list_unknown()
    lines = ["📋 Ma'lumot to'ldirmaganlar:\n"]
    lines.append(f"⛔ Botga ulanmagan xodimlar ({len(unlinked)}):")
    for e in unlinked[:50]:
        lines.append(f"  • {e['first_name']} {e['last_name']} ({e['phone']})")
    if not unlinked:
        lines.append("  — yo'q —")
    lines.append(f"\n❓ Guruhda ko'rilgan, lekin bazada yo'q ({len(unknown)}):")
    for u in unknown[:50]:
        lines.append(f"  • {u['name']} ({u['cnt']} marta)")
    if not unknown:
        lines.append("  — yo'q —")
    await cb.message.answer("\n".join(lines))
    await cb.answer()


@router.callback_query(F.data == "rem:send")
async def rem_send_choose(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    deps = await db.list_departments()
    await cb.message.answer("Eslatma kimlar uchun? (ular guruhga eslatib e'lon qilinadi)",
                            reply_markup=kb.recipients_kb(deps, "remto"))
    await cb.answer()


@router.callback_query(F.data.startswith("remto:"))
async def rem_send_text(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    if parts[1] == "all":
        await state.update_data(dep_id=None)
    else:
        await state.update_data(dep_id=int(parts[2]))
    await state.set_state(ReminderState.text)
    await cb.message.answer(
        "Eslatma matnini yozing (muddat ham qo'shishingiz mumkin, masalan:\n"
        "«Iltimos, botdan ro'yxatdan o'ting. Muddat: 20.09.2026 gacha»):")
    await cb.answer()


@router.message(ReminderState.text, F.text)
async def rem_send_do(msg: Message, state: FSMContext):
    data = await state.get_data()
    dep_id = data.get("dep_id")
    await state.clear()

    unlinked = await db.unlinked_employees(dep_id=dep_id)
    if not unlinked:
        await msg.answer("Bu guruhda ro'yxatdan o'tmaganlar yo'q. ✅", reply_markup=kb.admin_menu())
        return

    names = "\n".join(f"• {e['first_name']} {e['last_name']}" for e in unlinked)
    text = f"🔔 ESLATMA\n\n{msg.text}\n\nQuyidagilar botdan ro'yxatdan o'tishi kerak:\n{names}"

    import userbot
    ok = await userbot.post_to_group(text)
    if ok:
        await msg.answer(f"✅ Eslatma guruhga yuborildi ({len(unlinked)} kishi).",
                         reply_markup=kb.admin_menu())
    else:
        await msg.answer(
            "❌ Guruhga yuborib bo'lmadi (userbot ishlamayapti yoki guruh hali aniqlanmagan).\n"
            "Guruhga kamida bitta qurilma xabari kelgach, guruh avtomatik aniqlanadi.\n\n"
            f"Ro'yxat:\n{names}", reply_markup=kb.admin_menu())


# ==================== Adminlar boshqaruvi ====================
@router.message(Command("id"))
async def cmd_id(msg: Message):
    await msg.answer(f"🆔 Sizning Telegram ID: `{msg.from_user.id}`", parse_mode="Markdown")


@router.callback_query(F.data == "a:admins")
async def admins_menu(cb: CallbackQuery):
    if not is_super(cb.from_user.id):
        return await cb.answer("Faqat asosiy admin boshqaradi", show_alert=True)
    dbadmins = await db.list_admins()
    lines = ["👑 Adminlar:\n"]
    lines.append("Asosiy (o'zgarmas):")
    for a in ADMIN_IDS:
        lines.append(f"  • {a}")
    lines.append("\nQo'shilganlar:")
    if dbadmins:
        for a in dbadmins:
            lines.append(f"  • {a['note'] or ''} ({a['telegram_id']})")
    else:
        lines.append("  — yo'q —")
    lines.append("\nO'chirish uchun ustiga bosing yoki yangi qo'shing:")
    await cb.message.answer("\n".join(lines), reply_markup=kb.admins_kb(dbadmins))
    await cb.answer()


@router.callback_query(F.data == "adm:add")
async def adm_add(cb: CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    await state.set_state(AdminAdd.value)
    await cb.message.answer(
        "Yangi admin qo'shish. Uning Telegram ID raqamini yuboring.\n\n"
        "💡 ID ni bilish uchun o'sha odam botga /id yozsin.\n"
        "Yoki xodimning ismini yozing (agar u botga ulangan bo'lsa).")
    await cb.answer()


@router.message(AdminAdd.value, F.text)
async def adm_add_save(msg: Message, state: FSMContext):
    val = msg.text.strip()
    await state.clear()
    tg_id = None
    note = ""
    if val.isdigit():
        tg_id = int(val)
        note = f"ID {tg_id}"
        # agar shu ID xodim bo'lsa, ismini yozamiz
        for e in await db.list_employees():
            if e["telegram_id"] == tg_id:
                note = f"{e['first_name']} {e['last_name']}"
                break
    else:
        emp = await db.get_employee_by_name(val)
        if emp and emp["telegram_id"]:
            tg_id = emp["telegram_id"]
            note = f"{emp['first_name']} {emp['last_name']}"
        elif emp and not emp["telegram_id"]:
            await msg.answer("❌ Bu xodim hali botga /start bosmagan. Avval u ulanishi kerak.",
                             reply_markup=kb.admin_menu())
            return
        else:
            await msg.answer("❌ Topilmadi. Telegram ID raqam yuboring yoki to'g'ri ism yozing.",
                             reply_markup=kb.admin_menu())
            return
    await db.add_admin(tg_id, note)
    await load_admins()
    await msg.answer(f"✅ Admin qo'shildi: {note}", reply_markup=kb.admin_menu())
    try:
        await msg.bot.send_message(tg_id, "👑 Sizga admin huquqi berildi. /admin bosing.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("admdel:"))
async def adm_del(cb: CallbackQuery):
    if not is_super(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    tg_id = int(cb.data.split(":")[1])
    await db.remove_admin(tg_id)
    await load_admins()
    await cb.answer("O'chirildi")
    await cb.message.answer("🗑 Admin o'chirildi.")


@router.callback_query(F.data.startswith("empadm:"))
async def emp_make_admin(cb: CallbackQuery):
    if not is_super(cb.from_user.id):
        return await cb.answer("Faqat asosiy admin", show_alert=True)
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    if not emp["telegram_id"]:
        return await cb.answer("Xodim botga ulanmagan", show_alert=True)
    note = f"{emp['first_name']} {emp['last_name']}"
    await db.add_admin(emp["telegram_id"], note)
    await load_admins()
    await cb.answer("Admin qilindi ✅")
    await cb.message.answer(f"👑 {note} endi admin.")
    try:
        await cb.bot.send_message(emp["telegram_id"], "👑 Sizga admin huquqi berildi. /admin bosing.")
    except Exception:
        pass


# ==================== Zaxira (backup) va tiklash ====================
@router.callback_query(F.data == "a:backup")
async def backup_db(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    from config import DB_PATH
    import os
    if not os.path.exists(DB_PATH):
        return await cb.answer("Baza fayli topilmadi", show_alert=True)
    ts = dt.datetime.now(TZ).strftime("%Y%m%d_%H%M")
    await cb.message.answer_document(
        FSInputFile(DB_PATH, filename=f"backup_{ts}.db"),
        caption="💾 Bazaning zaxira nusxasi.\nUni saqlab qo'ying — kerak bo'lsa 'Tiklash' orqali qaytarasiz.")
    await cb.answer()


@router.callback_query(F.data == "a:restore")
async def restore_start(cb: CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id):
        return await cb.answer("Faqat asosiy admin", show_alert=True)
    await state.set_state(RestoreState.wait_file)
    await cb.message.answer(
        "♻️ Tiklash. Avval olingan zaxira (.db) faylini yuboring.\n"
        "⚠️ Hozirgi ma'lumotlar ustiga yoziladi!")
    await cb.answer()


@router.message(RestoreState.wait_file, F.document)
async def restore_got_file(msg: Message, state: FSMContext):
    doc = msg.document
    if not doc.file_name.endswith(".db"):
        await msg.answer("❌ Faqat .db fayl yuboring.")
        return
    path = f"/tmp/restore_{doc.file_unique_id}.db"
    await msg.bot.download(doc, destination=path)
    await state.update_data(path=path)
    await msg.answer("Shu fayl bilan hozirgi bazani almashtiraymi? Bu qaytarib bo'lmaydi.",
                     reply_markup=kb.restore_confirm_kb())


@router.callback_query(F.data == "restore:no")
async def restore_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("❌ Bekor qilindi.", reply_markup=kb.admin_menu())
    await cb.answer()


@router.callback_query(F.data == "restore:yes")
async def restore_do(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    path = data.get("path")
    from config import DB_PATH
    import os, shutil
    try:
        # tekshiruv: haqiqiy sqlite bazami
        import sqlite3
        conn = sqlite3.connect(path)
        conn.execute("SELECT count(*) FROM employees")
        conn.close()
    except Exception:
        await cb.message.answer("❌ Bu to'g'ri baza fayli emas. Bekor qilindi.",
                                reply_markup=kb.admin_menu())
        return
    try:
        shutil.copyfile(path, DB_PATH)
        await load_admins()
        n = await db.count_employees()
        await cb.message.answer(f"✅ Baza tiklandi. Endi {n} ta xodim bor.",
                                reply_markup=kb.admin_menu())
    except Exception as e:
        await cb.message.answer(f"❌ Tiklashda xatolik: {e}", reply_markup=kb.admin_menu())
    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    await cb.answer()


# ==================== HR / Adminga xabar (javob) ====================
def all_admin_ids():
    return set(ADMIN_IDS) | set(EXTRA_ADMINS)


@router.callback_query(F.data.startswith("hrreply:"))
async def hr_reply_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    emp_tg = int(cb.data.split(":")[1])
    await state.set_state(HRReply.wait)
    await state.update_data(emp_tg=emp_tg)
    await cb.message.answer("✍️ Javobingizni yozing:")
    await cb.answer()


@router.message(HRReply.wait, F.text)
async def hr_reply_send(msg: Message, state: FSMContext):
    data = await state.get_data()
    emp_tg = data.get("emp_tg")
    await state.clear()
    try:
        await msg.bot.send_message(emp_tg, f"👤 Admin javobi:\n\n{msg.text}")
        await msg.answer("✅ Javob yuborildi.", reply_markup=kb.admin_menu())
    except Exception as e:
        await msg.answer(f"❌ Yuborilmadi: {e}", reply_markup=kb.admin_menu())


# ==================== Guruh tarixini o'qish (backfill) ====================
@router.callback_query(F.data == "a:backfill")
async def backfill_trigger(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await cb.answer("O'qilmoqda... (biroz kuting)")
    await cb.message.answer("🔄 Guruhning eski xabarlari o'qilmoqda. Bu bir-ikki daqiqa olishi mumkin...")
    import userbot
    count, info = await userbot.backfill(limit=5000)
    if info == "ok":
        await cb.message.answer(
            f"✅ Tayyor! Eski xabarlardan {count} ta yangi qayd qo'shildi.\n"
            "Endi o'tgan davr statistikasi ham to'liq.", reply_markup=kb.admin_menu())
    else:
        await cb.message.answer(f"⚠️ O'qib bo'lmadi: {info}\n"
                                "(Guruhga kamida bitta qurilma xabari kelgach qayta urinib ko'ring.)",
                                reply_markup=kb.admin_menu())
