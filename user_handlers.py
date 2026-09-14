"""Xodimlar uchun handlerlar: ro'yxatdan o'tish, FaceID hisobotlari, Mening ma'lumotlarim."""
import datetime as dt
import calendar
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import db
import reports
import keyboards as kb
from config import ADMIN_IDS, TZ

router = Router()


class UserState(StatesGroup):
    wait_phone = State()
    wait_date = State()
    edit_value = State()
    hr_wait = State()


def today_str():
    return dt.datetime.now(TZ).strftime("%Y-%m-%d")


async def _need_emp(obj):
    uid = obj.from_user.id
    emp = await db.get_employee_by_telegram(uid)
    if not emp:
        target = obj.message if isinstance(obj, CallbackQuery) else obj
        await target.answer("Avval /start bosib ro'yxatdan o'ting.")
    return emp


# ==================== Ro'yxatdan o'tish ====================
@router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    await state.clear()
    emp = await db.get_employee_by_telegram(msg.from_user.id)
    if emp:
        extra = "\n\n🔐 Admin: /admin" if msg.from_user.id in ADMIN_IDS else ""
        await msg.answer(
            f"Assalomu alaykum, {emp['first_name']}! 👋\nQuyidagi menyudan foydalaning." + extra,
            reply_markup=kb.user_menu())
        return
    await msg.answer(
        "Assalomu alaykum! 👋\n\nBotdan foydalanish uchun telefon raqamingizni yuboring "
        "(tugma orqali yoki qo'lda, masalan: 901234567).",
        reply_markup=kb.contact_kb())
    await state.set_state(UserState.wait_phone)


@router.message(UserState.wait_phone, F.contact)
async def got_contact(msg: Message, state: FSMContext):
    await _register(msg, state, msg.contact.phone_number)


@router.message(UserState.wait_phone, F.text)
async def got_phone_text(msg: Message, state: FSMContext):
    await _register(msg, state, msg.text)


async def _register(msg, state, phone):
    emp = await db.get_employee_by_phone(phone)
    if not emp:
        await msg.answer("❌ Bu raqam bazada topilmadi.\n"
                         "Administrator sizni tizimga qo'shganiga ishonch hosil qiling.")
        return
    await db.bind_telegram(emp["id"], msg.from_user.id)
    await state.clear()
    extra = "\n\n🔐 Admin: /admin" if msg.from_user.id in ADMIN_IDS else ""
    await msg.answer(
        f"✅ Muvaffaqiyatli! Xush kelibsiz, {emp['first_name']} {emp['last_name']}." + extra,
        reply_markup=kb.user_menu())


# ==================== 📷 FaceID bo'limi ====================
@router.message(F.text == "📷 FaceID")
async def m_faceid(msg: Message):
    if await _need_emp(msg):
        await msg.answer("📷 FaceID — hisobot turini tanlang:", reply_markup=kb.user_faceid_kb())


@router.callback_query(F.data == "u:today")
async def cb_today(cb: CallbackQuery):
    emp = await _need_emp(cb)
    if emp:
        await cb.message.answer(await reports.daily_text(emp, today_str()))
    await cb.answer()


@router.callback_query(F.data == "u:month")
async def cb_month(cb: CallbackQuery):
    emp = await _need_emp(cb)
    if emp:
        now = dt.datetime.now(TZ)
        first = now.replace(day=1).strftime("%Y-%m-%d")
        last = now.replace(day=calendar.monthrange(now.year, now.month)[1]).strftime("%Y-%m-%d")
        await cb.message.answer(await reports.period_text(emp, first, last, "Oylik hisobot"))
    await cb.answer()


@router.callback_query(F.data == "u:months")
async def cb_months(cb: CallbackQuery):
    if await _need_emp(cb):
        await cb.message.answer("Qaysi oy?", reply_markup=kb.months_kb("umon", reports.months_list(12)))
    await cb.answer()


@router.callback_query(F.data.startswith("umon:"))
async def cb_month_pick(cb: CallbackQuery):
    emp = await _need_emp(cb)
    if emp:
        ym = cb.data.split(":")[1]
        first, last = reports.month_bounds(ym)
        await cb.message.answer(await reports.period_text(emp, first, last, "Oylik hisobot"))
    await cb.answer()


@router.callback_query(F.data == "u:date")
async def cb_date(cb: CallbackQuery, state: FSMContext):
    if await _need_emp(cb):
        await state.set_state(UserState.wait_date)
        await cb.message.answer("Sanani yuboring (format: YYYY-MM-DD, masalan 2026-08-15):")
    await cb.answer()


@router.message(UserState.wait_date, F.text)
async def got_date(msg: Message, state: FSMContext):
    emp = await db.get_employee_by_telegram(msg.from_user.id)
    try:
        d = dt.datetime.strptime(msg.text.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        await msg.answer("❌ Noto'g'ri format. Masalan: 2026-08-15")
        return
    await state.clear()
    await msg.answer(await reports.daily_text(emp, d))


# ==================== 👤 Mening ma'lumotlarim ====================
@router.message(F.text == "👤 Mening ma'lumotlarim")
async def m_myinfo(msg: Message):
    if await _need_emp(msg):
        await msg.answer("👤 Mening ma'lumotlarim:", reply_markup=kb.user_myinfo_kb())


@router.callback_query(F.data == "u:info:view")
async def cb_info_view(cb: CallbackQuery):
    emp = await _need_emp(cb)
    if emp:
        late = "hisoblanadi" if emp["count_late"] else "hisoblanmaydi"
        await cb.message.answer(
            f"👤 Username: {db.full_name(emp)}\n"
            f"📞 Telefon: {emp['phone']}\n"
            f"🕐 Ish grafigi: {emp['work_start']}-{emp['work_end']}\n"
            f"⏰ Kechikish: {late}")
    await cb.answer()


@router.callback_query(F.data == "u:info:edit")
async def cb_info_edit(cb: CallbackQuery):
    if await _need_emp(cb):
        await cb.message.answer(
            "Nimani o'zgartirmoqchisiz?\n"
            "(FaceID ID va ish grafigini faqat administrator o'zgartiradi.)",
            reply_markup=kb.user_edit_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("u:edit:"))
async def cb_edit_field(cb: CallbackQuery, state: FSMContext):
    field = cb.data.split(":")[2]
    await state.set_state(UserState.edit_value)
    await state.update_data(field=field)
    prompt = ("Yangi username:" if field == "name"
              else "Yangi telefon raqam (901234567):")
    await cb.message.answer(prompt)
    await cb.answer()


@router.message(UserState.edit_value, F.text)
async def save_user_edit(msg: Message, state: FSMContext):
    emp = await db.get_employee_by_telegram(msg.from_user.id)
    data = await state.get_data()
    field, val = data["field"], msg.text.strip()
    try:
        if field == "name":
            await db.update_employee(emp["id"], first_name=val, last_name="")
        elif field == "phone":
            await db.update_employee(emp["id"], phone=val)
    except Exception as e:
        await msg.answer(f"❌ Xatolik: {e}")
        return
    await state.clear()
    await msg.answer("✅ Saqlandi.", reply_markup=kb.user_menu())


# ==================== ✉️ HR bo'limiga xabar ====================
@router.message(F.text == "✉️ HR bo'limiga xabar")
async def hr_start(msg: Message, state: FSMContext):
    if not await _need_emp(msg):
        return
    await state.set_state(UserState.hr_wait)
    await msg.answer("HR bo'limiga yubormoqchi bo'lgan xabaringizni yozing "
                     "(matn, rasm yoki fayl bo'lishi mumkin):")


@router.message(UserState.hr_wait)
async def hr_send(msg: Message, state: FSMContext):
    emp = await db.get_employee_by_telegram(msg.from_user.id)
    await state.clear()
    import admin_handlers
    ids = admin_handlers.all_admin_ids()
    who = f"{db.full_name(emp)} ({emp['phone']})"
    header = f"📩 HR bo'limiga xabar\n{who}:"
    btn = kb.hr_reply_kb(msg.from_user.id)
    sent = 0
    for aid in ids:
        try:
            if msg.photo:
                await msg.bot.send_photo(aid, msg.photo[-1].file_id,
                                         caption=f"{header}\n{msg.caption or ''}", reply_markup=btn)
            elif msg.document:
                await msg.bot.send_document(aid, msg.document.file_id,
                                            caption=f"{header}\n{msg.caption or ''}", reply_markup=btn)
            elif msg.text:
                await msg.bot.send_message(aid, f"{header}\n{msg.text}", reply_markup=btn)
            else:
                continue
            sent += 1
        except Exception:
            pass
    if sent:
        await msg.answer("✅ Xabaringiz HR bo'limiga yuborildi. Tez orada javob beriladi.",
                         reply_markup=kb.user_menu())
    else:
        await msg.answer("❌ Hozircha admin mavjud emas.", reply_markup=kb.user_menu())
