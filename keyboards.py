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
            [KeyboardButton(text="✉️ Adminga xabar")],
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
            [KeyboardButton(text="👥 Ma'lumotlar"), KeyboardButton(text="🏢 Bo'limlar")],
            [KeyboardButton(text="✉️ Xabar"), KeyboardButton(text="🔔 Eslatma")],
            [KeyboardButton(text="🔙 Oddiy menyu")],
        ],
        resize_keyboard=True,
    )


def admin_faceid_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Qurilma sozlamalari", callback_data="a:fset")],
        [InlineKeyboardButton(text="📝 Bildirishnoma matnlari", callback_data="a:tpl")],
        [InlineKeyboardButton(text="🔄 Guruh tarixini o'qish", callback_data="a:backfill")],
        [InlineKeyboardButton(text="📊 Hisobot (Excel)", callback_data="a:report")],
        [InlineKeyboardButton(text="📋 Bugungi holat", callback_data="a:today")],
    ])


def templates_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Kirish matni", callback_data="tpl:in"),
         InlineKeyboardButton(text="🔴 Chiqish matni", callback_data="tpl:out")],
        [InlineKeyboardButton(text="⚠️ Ogohlantirish matni", callback_data="tpl:warn"),
         InlineKeyboardButton(text="📊 So'rovnoma matni", callback_data="tpl:survey")],
        [InlineKeyboardButton(text="↩️ Standartga qaytarish", callback_data="tpl:reset")],
    ])


def add_dep_pick_kb(deps):
    kb = [[InlineKeyboardButton(text="— Bo'limsiz —", callback_data="adddep:0")]]
    for d in deps:
        kb.append([InlineKeyboardButton(text=f"🏢 {d['name']}", callback_data=f"adddep:{d['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def hr_reply_kb(emp_tg_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"hrreply:{emp_tg_id}")],
    ])


def dep_manage_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Bo'lim qo'shish", callback_data="dep:add")],
        [InlineKeyboardButton(text="📋 Bo'limlar ro'yxati", callback_data="dep:list")],
    ])


def departments_kb(deps, prefix="dep"):
    kb = [[InlineKeyboardButton(text=f"🏢 {d['name']} ({d['count']})",
                                callback_data=f"{prefix}:{d['id']}")] for d in deps]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def dep_actions_kb(dep_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Xodimlari", callback_data=f"depmem:{dep_id}")],
        [InlineKeyboardButton(text="🗑 Bo'limni o'chirish", callback_data=f"depdel:{dep_id}")],
    ])


def reminder_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 To'ldirmaganlar ro'yxati", callback_data="rem:list")],
        [InlineKeyboardButton(text="📢 Guruhga eslatma yuborish", callback_data="rem:send")],
    ])


def recipients_kb(deps, prefix):
    kb = [[InlineKeyboardButton(text="📢 Hammaga", callback_data=f"{prefix}:all")]]
    for d in deps:
        kb.append([InlineKeyboardButton(text=f"🏢 {d['name']} ({d['count']})",
                                        callback_data=f"{prefix}:d:{d['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def emp_department_kb(deps, emp_id):
    kb = [[InlineKeyboardButton(text="— Bo'limsiz —", callback_data=f"setdep:{emp_id}:0")]]
    for d in deps:
        kb.append([InlineKeyboardButton(text=f"🏢 {d['name']}",
                                        callback_data=f"setdep:{emp_id}:{d['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_data_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Xodim qo'shish", callback_data="a:addemp")],
        [InlineKeyboardButton(text="👥 Xodimlar ro'yxati", callback_data="a:listemp")],
        [InlineKeyboardButton(text="👑 Adminlar", callback_data="a:admins")],
        [InlineKeyboardButton(text="💾 Zaxira nusxa", callback_data="a:backup"),
         InlineKeyboardButton(text="♻️ Tiklash", callback_data="a:restore")],
    ])


def admins_kb(admin_list):
    kb = []
    for a in admin_list:
        label = f"🗑 {a['note'] or a['telegram_id']}"
        kb.append([InlineKeyboardButton(text=label, callback_data=f"admdel:{a['telegram_id']}")])
    kb.append([InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="adm:add")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def restore_confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ha, tiklash", callback_data="restore:yes"),
         InlineKeyboardButton(text="❌ Bekor", callback_data="restore:no")],
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
        [InlineKeyboardButton(text="🏢 Bo'lim tayinlash", callback_data=f"empdep:{emp['id']}")],
        [InlineKeyboardButton(text="👑 Admin qilish", callback_data=f"empadm:{emp['id']}")],
        [InlineKeyboardButton(text="📊 Hisobot (bu oy)", callback_data=f"report:{emp['id']}")],
        [InlineKeyboardButton(text="🗑 O'chirish (nofaol)", callback_data=f"deactivate:{emp['id']}")],
    ])
