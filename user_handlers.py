"""Xodimlar uchun handlerlar: ro'yxatdan o'tish va hisobotlarni ko'rish."""
import datetime as dt
import calendar
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
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
    wait_period = State()


def today_str():
    return dt.datetime.now(TZ).strftime("%Y-%m-%d")


@router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    await state.clear()
    emp = await db.get_employee_by_telegram(msg.from_user.id)
    if emp:
        extra = "\n\n🔐 Admin: /admin" if msg.from_user.id in ADMIN_IDS else ""
        await msg.answer(
            f"Assalomu alaykum, {emp['first_name']}! 👋\n"
            f"Quyidagi menyudan foydalaning." + extra,
            reply_markup=kb.user_menu())
        return
    await msg.answer(
        "Assalomu alaykum! 👋\n\n"
        "Botdan foydalanish uchun telefon raqamingizni yuboring "
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
        await msg.answer(
            "❌ Bu raqam bazada topilmadi.\n"
            "Iltimos, administrator sizni tizimga qo'shganiga ishonch hosil qiling "
            "va to'g'ri raqam yuboring.")
        return
    await db.bind_telegram(emp["id"], msg.from_user.id)
    await state.clear()
    extra = "\n\n🔐 Admin: /admin" if msg.from_user.id in ADMIN_IDS else ""
    await msg.answer(
        f"✅ Muvaffaqiyatli! Xush kelibsiz, {emp['first_name']} {emp['last_name']}." + extra,
        reply_markup=kb.user_menu())


# ---------------- Hisobotlar ----------------

async def _need_emp(msg):
    emp = await db.get_employee_by_telegram(msg.from_user.id)
    if not emp:
        await msg.answer("Avval /start bosib ro'yxatdan o'ting.")
    return emp


@router.message(F.text == "📅 Bugun")
async def r_today(msg: Message):
    emp = await _need_emp(msg)
    if emp:
        await msg.answer(await reports.daily_text(emp, today_str()))


@router.message(F.text == "🗓 Bu oy")
async def r_month(msg: Message):
    emp = await _need_emp(msg)
    if not emp:
        return
    now = dt.datetime.now(TZ)
    first = now.replace(day=1).strftime("%Y-%m-%d")
    last_day = calendar.monthrange(now.year, now.month)[1]
    last = now.replace(day=last_day).strftime("%Y-%m-%d")
    await msg.answer(await reports.period_text(emp, first, last, "Oylik hisobot"))


@router.message(F.text == "📆 Sana bo'yicha")
async def ask_date(msg: Message, state: FSMContext):
    if not await _need_emp(msg):
        return
    await state.set_state(UserState.wait_date)
    await msg.answer("Sanani yuboring (format: YYYY-MM-DD, masalan 2026-08-15):")


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


@router.message(F.text == "⏳ Davr bo'yicha")
async def ask_period(msg: Message, state: FSMContext):
    if not await _need_emp(msg):
        return
    await state.set_state(UserState.wait_period)
    await msg.answer("Davrni yuboring (format: YYYY-MM-DD YYYY-MM-DD):\n"
                     "Masalan: 2026-08-01 2026-08-15")


@router.message(UserState.wait_period, F.text)
async def got_period(msg: Message, state: FSMContext):
    emp = await db.get_employee_by_telegram(msg.from_user.id)
    parts = msg.text.strip().split()
    try:
        d1 = dt.datetime.strptime(parts[0], "%Y-%m-%d").strftime("%Y-%m-%d")
        d2 = dt.datetime.strptime(parts[1], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        await msg.answer("❌ Noto'g'ri format. Masalan: 2026-08-01 2026-08-15")
        return
    await state.clear()
    if d1 > d2:
        d1, d2 = d2, d1
    await msg.answer(await reports.period_text(emp, d1, d2, "Davr hisoboti"))
