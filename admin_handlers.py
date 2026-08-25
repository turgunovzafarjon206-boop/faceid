"""Admin panel: xodim qo'shish, boshqarish, hisobot."""
import datetime as dt
import calendar
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
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


# ---------------- Xodim qo'shish ----------------
@router.message(F.text == "➕ Xodim qo'shish")
async def add_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(AddEmp.first)
    await msg.answer("Ism kiriting:")


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
        emp_id = await db.add_employee(
            data["first"], data["last"], data["phone"], data["faceid"],
            work_start=ws.strip(), work_end=we.strip())
    except Exception as e:
        await msg.answer(f"❌ Xatolik (telefon yoki FaceID ID takrorlangan bo'lishi mumkin):\n{e}")
        await state.clear()
        return
    await state.clear()
    await msg.answer(
        f"✅ Xodim qo'shildi!\n\n"
        f"👤 {data['first']} {data['last']}\n"
        f"📞 {data['phone']}\n"
        f"🆔 FaceID: {data['faceid']}\n"
        f"🕐 {ws.strip()}-{we.strip()}\n\n"
        f"Endi xodim botga /start bosib, shu raqam bilan kirsin.",
        reply_markup=kb.admin_menu())


# ---------------- Xodimlarni boshqarish ----------------
@router.message(F.text == "👥 Xodimlar")
async def list_emps(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    emps = await db.list_employees()
    if not emps:
        await msg.answer("Hozircha xodim yo'q.")
        return
    await msg.answer("Xodimni tanlang:", reply_markup=kb.employees_kb(emps))


@router.callback_query(F.data.startswith("emp:"))
async def show_emp(cb: CallbackQuery):
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    if not emp:
        await cb.answer("Topilmadi", show_alert=True)
        return
    bound = "✅ ulangan" if emp["telegram_id"] else "❌ ulanmagan"
    txt = (f"👤 {emp['first_name']} {emp['last_name']}\n"
           f"📞 {emp['phone']}\n"
           f"🆔 FaceID: {emp['faceid_user_id']}\n"
           f"🕐 {emp['work_start']}-{emp['work_end']}\n"
           f"⏰ Kechikish: {'hisoblanadi' if emp['count_late'] else 'hisoblanmaydi'}\n"
           f"📲 Telegram: {bound}")
    await cb.message.answer(txt, reply_markup=kb.employee_manage_kb(emp))
    await cb.answer()


@router.callback_query(F.data.startswith("togglelate:"))
async def toggle_late(cb: CallbackQuery):
    emp_id = int(cb.data.split(":")[1])
    emp = await db.get_employee_by_id(emp_id)
    new = 0 if emp["count_late"] else 1
    await db.update_employee(emp_id, count_late=new)
    await cb.answer("Yangilandi ✅")
    emp = await db.get_employee_by_id(emp_id)
    try:
        await cb.message.edit_reply_markup(reply_markup=kb.employee_manage_kb(emp))
    except Exception:
        await cb.message.answer(
            f"Kechikish endi {'hisoblanadi' if new else 'hisoblanmaydi'}.",
            reply_markup=kb.employee_manage_kb(emp))


@router.callback_query(F.data.startswith("deactivate:"))
async def deactivate(cb: CallbackQuery):
    emp_id = int(cb.data.split(":")[1])
    await db.update_employee(emp_id, active=0)
    await cb.answer("Xodim nofaol qilindi")
    await cb.message.answer("🗑 Xodim nofaol holatga o'tkazildi.")


@router.callback_query(F.data.startswith("report:"))
async def emp_report(cb: CallbackQuery):
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    now = dt.datetime.now(TZ)
    first = now.replace(day=1).strftime("%Y-%m-%d")
    last_day = calendar.monthrange(now.year, now.month)[1]
    last = now.replace(day=last_day).strftime("%Y-%m-%d")
    await cb.message.answer(await reports.period_text(emp, first, last, "Oylik hisobot"))
    await cb.answer()


# ---- Tahrirlash ----
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


# ---------------- Umumiy hisobot ----------------
@router.message(F.text == "📊 Hisobot")
async def all_report(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    emps = await db.list_employees()
    if not emps:
        await msg.answer("Xodim yo'q.")
        return
    now = dt.datetime.now(TZ)
    day = now.strftime("%Y-%m-%d")
    lines = [f"📊 Bugungi hisobot ({day}):\n"]
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
    await msg.answer("\n".join(lines))


# ---------------- FaceID sozlamalari ----------------
def _mask(v):
    if not v:
        return "—"
    return v[:3] + "***" if len(v) > 4 else "***"


async def _faceid_status_text():
    s = await faceid.effective_settings()
    return (
        "⚙️ FaceID qurilma sozlamalari\n\n"
        f"🔧 Rejim: {s['mode']}\n"
        f"🌐 URL: {s['url'] or '—'}\n"
        f"🔑 Token: {_mask(s['token'])}\n"
        f"👤 Login: {s['user'] or '—'}\n"
        f"🔒 Parol: {_mask(s['pass'])}\n"
        f"⏱ Interval: {s['interval']} soniya\n\n"
        "O'zgartirish uchun tugmani bosing:"
    )


@router.message(F.text == "⚙️ FaceID sozlamalari")
async def faceid_settings(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    s = await faceid.effective_settings()
    await msg.answer(await _faceid_status_text(),
                     reply_markup=kb.faceid_settings_kb(s["mode"]))


@router.callback_query(F.data == "fset:mode")
async def fset_mode(cb: CallbackQuery):
    await cb.message.answer("Rejimni tanlang:", reply_markup=kb.faceid_mode_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("fmode:"))
async def fset_mode_pick(cb: CallbackQuery):
    mode = cb.data.split(":")[1]
    await db.set_setting("faceid_mode", mode)
    await cb.answer("Rejim saqlandi ✅")
    await cb.message.answer(await _faceid_status_text(),
                            reply_markup=kb.faceid_settings_kb(mode))


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
        await _test_connection(cb)
        return
    if field == "mode":
        return  # yuqorida ishlanadi
    key, prompt = _FIELD_PROMPTS[field]
    await state.set_state(FaceIDSet.value)
    await state.update_data(key=key)
    await cb.message.answer(prompt)
    await cb.answer()


@router.message(FaceIDSet.value, F.text)
async def fset_save(msg: Message, state: FSMContext):
    data = await state.get_data()
    key = data["key"]
    val = msg.text.strip()
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
    await msg.answer(await _faceid_status_text(),
                     reply_markup=kb.faceid_settings_kb(s["mode"]))


async def _test_connection(cb: CallbackQuery):
    await cb.answer("Tekshirilyapti...")
    try:
        client, _ = await faceid.build_client()
        since = dt.datetime.now(TZ) - dt.timedelta(days=1)
        events = await client.fetch_events(since)
        if not events:
            await cb.message.answer(
                "🔌 Ulanish ishladi, lekin oxirgi 1 kunda hodisa topilmadi.\n"
                "(Rejim 'mock' bo'lsa bu normal. 'generic' bo'lsa API to'g'ri URL "
                "berayotganini tekshiring.)")
            return
        sample = events[-5:]
        lines = ["✅ Ulanish muvaffaqiyatli! Oxirgi hodisalar:\n"]
        for e in sample:
            lines.append(f"• FaceID ID: {e['faceid_user_id']} | "
                         f"{e['ts'].strftime('%Y-%m-%d %H:%M')} | "
                         f"{e.get('event_type') or 'avto'}")
        lines.append("\n💡 Yuqoridagi 'FaceID ID' larni xodim qo'shishda ishlating.")
        await cb.message.answer("\n".join(lines))
    except Exception as e:
        await cb.message.answer(f"❌ Ulanishda xatolik:\n{e}\n\n"
                                "URL, token yoki rejimni tekshiring.")
