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


def is_admin(uid) -> bool:
    return uid in ADMIN_IDS


class AddEmp(StatesGroup):
    first = State()
    last = State()
    phone = State()
    faceid = State()
    schedule = State()


class EditEmp(StatesGroup):
    value = State()


class FaceIDSet(StatesGroup):
    value = State()


class AdminReport(StatesGroup):
    period = State()


class Broadcast(StatesGroup):
    text = State()


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
async def m_message(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer("✉️ Xabar bo'limi:", reply_markup=kb.admin_msg_kb())


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
    await msg.answer("FaceID qurilmasidagi foydalanuvchi ID (masalan 5):")


@router.message(AddEmp.faceid, F.text)
async def add_faceid(msg: Message, state: FSMContext):
    await state.update_data(faceid=msg.text.strip())
    await state.set_state(AddEmp.schedule)
    await msg.answer("Ish grafigi (format: 08:00-18:00):")


@router.message(AddEmp.schedule, F.text)
async def add_schedule(msg: Message, state: FSMContext):
    data = await state.get_data()
    try:
        ws, we = msg.text.strip().split("-")
        dt.datetime.strptime(ws.strip(), "%H:%M")
        dt.datetime.strptime(we.strip(), "%H:%M")
    except ValueError:
        await msg.answer("❌ Format noto'g'ri. Masalan: 08:00-18:00")
        return
    try:
        await db.add_employee(data["first"], data["last"], data["phone"],
                              data["faceid"], work_start=ws.strip(), work_end=we.strip())
    except Exception as e:
        await msg.answer(f"❌ Xatolik (telefon yoki FaceID ID takrorlangan bo'lishi mumkin):\n{e}")
        await state.clear()
        return
    await state.clear()
    await msg.answer(
        f"✅ Xodim qo'shildi!\n\n👤 {data['first']} {data['last']}\n"
        f"📞 {data['phone']}\n🆔 FaceID: {data['faceid']}\n🕐 {ws.strip()}-{we.strip()}\n\n"
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


# ==================== Xabar (broadcast) ====================
@router.callback_query(F.data == "a:bcast")
async def bcast_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(Broadcast.text)
    await cb.message.answer("📢 Barcha xodimlarga yuboriladigan xabar matnini yuboring:")
    await cb.answer()


@router.message(Broadcast.text, F.text)
async def bcast_preview(msg: Message, state: FSMContext):
    await state.update_data(text=msg.text)
    emps = [e for e in await db.list_employees() if e["telegram_id"]]
    await msg.answer(
        f"Xabar {len(emps)} ta xodimga yuboriladi:\n\n———\n{msg.text}\n———\n\nTasdiqlaysizmi?",
        reply_markup=kb.bcast_confirm_kb())


@router.callback_query(F.data == "bcast:no")
async def bcast_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("❌ Bekor qilindi.", reply_markup=kb.admin_menu())
    await cb.answer()


@router.callback_query(F.data == "bcast:yes")
async def bcast_send(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("text", "")
    await state.clear()
    await cb.answer("Yuborilmoqda...")
    emps = [e for e in await db.list_employees() if e["telegram_id"]]
    ok = fail = 0
    for emp in emps:
        try:
            await cb.bot.send_message(emp["telegram_id"], f"📢 E'lon:\n\n{text}")
            ok += 1
        except Exception:
            fail += 1
    await cb.message.answer(f"✅ Yuborildi: {ok} ta\n❌ Yuborilmadi: {fail} ta",
                            reply_markup=kb.admin_menu())
