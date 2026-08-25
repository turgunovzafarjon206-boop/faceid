"""Tugmalar (klaviaturalar)."""
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardMarkup, InlineKeyboardButton)


def contact_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )


# ==================== XODIM ====================
def user_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📷 FaceID"), KeyboardButton(text="👤 Mening ma'lumotlarim")],
        ],
        resize_keyboard=True,
    )


def user_faceid_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Bugun", callback_data="u:today"),
         InlineKeyboardButton(text="🗓 Bu oy", callback_data="u:month")],
        [InlineKeyboardButton(text="📆 Sana bo'yicha", callback_data="u:date")],
    ])


def user_myinfo_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁 Ma'lumotlarni ko'rish", callback_data="u:info:view")],
        [InlineKeyboardButton(text="✏️ O'zgartirish", callback_data="u:info:edit")],
    ])


def user_edit_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Ism-familiya", callback_data="u:edit:name")],
        [InlineKeyboardButton(text="📞 Telefon", callback_data="u:edit:phone")],
    ])


# ==================== ADMIN ====================
def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📷 FaceID boshqarish")],
            [KeyboardButton(text="👥 Ma'lumotlar"), KeyboardButton(text="✉️ Xabar")],
            [KeyboardButton(text="🔙 Oddiy menyu")],
        ],
        resize_keyboard=True,
    )


def admin_faceid_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Qurilma sozlamalari", callback_data="a:fset")],
        [InlineKeyboardButton(text="📊 Hisobot (Excel)", callback_data="a:report")],
        [InlineKeyboardButton(text="📋 Bugungi holat", callback_data="a:today")],
    ])


def admin_data_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Xodim qo'shish", callback_data="a:addemp")],
        [InlineKeyboardButton(text="👥 Xodimlar ro'yxati", callback_data="a:listemp")],
    ])


def admin_msg_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Hammaga xabar", callback_data="a:bcast")],
    ])


def admin_report_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Bugun", callback_data="arep:today"),
         InlineKeyboardButton(text="🗓 Bu oy", callback_data="arep:month")],
        [InlineKeyboardButton(text="⏳ Davr (sana-sana)", callback_data="arep:period")],
    ])


def bcast_confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ha, yuborish", callback_data="bcast:yes"),
         InlineKeyboardButton(text="❌ Bekor", callback_data="bcast:no")],
    ])


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


def employees_kb(employees):
    kb = []
    for e in employees:
        kb.append([InlineKeyboardButton(
            text=f"{e['first_name']} {e['last_name']} ({e['phone']})",
            callback_data=f"emp:{e['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


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
