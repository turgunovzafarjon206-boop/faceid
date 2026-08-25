"""Tugmalar (klaviaturalar)."""
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardMarkup, InlineKeyboardButton)


def contact_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )


def user_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Bugun"), KeyboardButton(text="🗓 Bu oy")],
            [KeyboardButton(text="📆 Sana bo'yicha"), KeyboardButton(text="⏳ Davr bo'yicha")],
        ],
        resize_keyboard=True,
    )


def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Xodim qo'shish")],
            [KeyboardButton(text="👥 Xodimlar"), KeyboardButton(text="📊 Hisobot")],
            [KeyboardButton(text="⚙️ FaceID sozlamalari")],
            [KeyboardButton(text="🔙 Oddiy menyu")],
        ],
        resize_keyboard=True,
    )


def employees_kb(employees):
    kb = []
    for e in employees:
        kb.append([InlineKeyboardButton(
            text=f"{e['first_name']} {e['last_name']} ({e['phone']})",
            callback_data=f"emp:{e['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def faceid_settings_kb(mode):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔧 Rejim: {mode}", callback_data="fset:mode")],
        [InlineKeyboardButton(text="🌐 API manzil (URL)", callback_data="fset:url")],
        [InlineKeyboardButton(text="🔑 Token", callback_data="fset:token")],
        [InlineKeyboardButton(text="👤 Login", callback_data="fset:user")],
        [InlineKeyboardButton(text="🔒 Parol", callback_data="fset:pass")],
        [InlineKeyboardButton(text="⏱ Tekshirish interval (soniya)", callback_data="fset:interval")],
        [InlineKeyboardButton(text="🔌 Ulanishni tekshirish", callback_data="fset:test")],
    ])


def faceid_mode_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="mock (test)", callback_data="fmode:mock")],
        [InlineKeyboardButton(text="generic (JSON API)", callback_data="fmode:generic")],
        [InlineKeyboardButton(text="hikvision", callback_data="fmode:hikvision")],
    ])


def employee_manage_kb(emp):
    late = "✅ Kechikish hisoblanadi" if emp["count_late"] else "❌ Kechikish hisoblanmaydi"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Ism/Familiya", callback_data=f"edit:name:{emp['id']}")],
        [InlineKeyboardButton(text="📞 Telefon", callback_data=f"edit:phone:{emp['id']}")],
        [InlineKeyboardButton(text="🆔 FaceID ID", callback_data=f"edit:faceid:{emp['id']}")],
        [InlineKeyboardButton(text="🕐 Ish grafigi", callback_data=f"edit:schedule:{emp['id']}")],
        [InlineKeyboardButton(text=late, callback_data=f"togglelate:{emp['id']}")],
        [InlineKeyboardButton(text="📊 Hisobot (bu oy)", callback_data=f"report:{emp['id']}")],
        [InlineKeyboardButton(text="🗑 O'chirish (nofaol)", callback_data=f"deactivate:{emp['id']}")],
    ])
