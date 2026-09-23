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
            [KeyboardButton(text="✉️ HR bo'limiga xabar")],
        ],
        resize_keyboard=True,
    )


def user_faceid_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Bugun", callback_data="u:today"),
         InlineKeyboardButton(text="🗓 Bu oy", callback_data="u:month")],
        [InlineKeyboardButton(text="📆 Boshqa oy", callback_data="u:months"),
         InlineKeyboardButton(text="🔎 Sana bo'yicha", callback_data="u:date")],
    ])


def months_kb(prefix, months):
    """months: [(label, 'YYYY-MM'), ...]"""
    rows = []
    row = []
    for label, ym in months:
        row.append(InlineKeyboardButton(text=label, callback_data=f"{prefix}:{ym}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fine_deps_kb(deps, enabled, mode, prefix="finedep"):
    """mode: 'all' | 'none' | 'some'. enabled: set of dep ids."""
    rows = []
    all_mark = "✅" if mode == "all" else "⬜️"
    none_mark = "✅" if mode == "none" else "⬜️"
    rows.append([InlineKeyboardButton(text=f"{all_mark} Hammaga ko'rsatish", callback_data=f"{prefix}:all")])
    rows.append([InlineKeyboardButton(text=f"{none_mark} Hech kimga", callback_data=f"{prefix}:none")])
    for d in deps:
        mark = "✅" if (mode == "some" and d["id"] in enabled) else "⬜️"
        rows.append([InlineKeyboardButton(text=f"{mark} 🏢 {d['name']}",
                                          callback_data=f"{prefix}:{d['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_myinfo_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁 Ma'lumotlarni ko'rish", callback_data="u:info:view")],
        [InlineKeyboardButton(text="✏️ O'zgartirish", callback_data="u:info:edit")],
    ])


def user_edit_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Telefon", callback_data="u:edit:phone")],
    ])


def user_data_edit_kb(reqs):
    """Xodim to'ldiradigan/o'zgartiradigan ma'lumotlar + telefon."""
    rows = [[InlineKeyboardButton(text="📞 Telefon", callback_data="u:edit:phone")]]
    for r in reqs:
        mark = "✅" if r.get("submitted") else ("🔴" if r["mandatory"] else "🟢")
        rows.append([InlineKeyboardButton(text=f"{mark} {r['title']}",
                                          callback_data=f"fillreq:{r['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==================== ADMIN ====================
def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📷 FaceID boshqarish")],
            [KeyboardButton(text="👥 Ma'lumotlar"), KeyboardButton(text="🏢 Bo'limlar")],
            [KeyboardButton(text="✉️ Xabar"), KeyboardButton(text="🔔 Eslatma")],
            [KeyboardButton(text="📋 Ma'lumot talablari"), KeyboardButton(text="📊 So'rovnoma")],
            [KeyboardButton(text="🔙 Oddiy menyu")],
        ],
        resize_keyboard=True,
    )


def admin_faceid_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Qurilma sozlamalari", callback_data="a:fset")],
        [InlineKeyboardButton(text="📝 Bildirishnoma matnlari", callback_data="a:tpl")],
        [InlineKeyboardButton(text="💰 Jarima ko'rinishi (xodimga)", callback_data="a:finetoggle")],
        [InlineKeyboardButton(text="🕐 Ortiqcha ko'rinishi (xodimga)", callback_data="a:overtoggle")],
        [InlineKeyboardButton(text="📅 Dars jadvali yuklash/yangilash", callback_data="a:schedupload")],
        [InlineKeyboardButton(text="🔗 Ismlarni biriktirish", callback_data="a:schedbind")],
        [InlineKeyboardButton(text="🚫 Kechikishni hisoblamaslik", callback_data="a:exempt")],
        [InlineKeyboardButton(text="🕒 Vaqtni o'zgartirish", callback_data="a:settime")],
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


def add_countlate_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Kechikish hisoblanadi", callback_data="addcl:1")],
        [InlineKeyboardButton(text="❌ Kechikish hisoblanmaydi", callback_data="addcl:0")],
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


def hr_user_reply_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Javob berish", callback_data="hruser")],
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
        [InlineKeyboardButton(text="📨 To'ldirmaganlarga eslatma (shaxsan)", callback_data="rem:data")],
        [InlineKeyboardButton(text="📋 To'ldirmaganlar ro'yxati", callback_data="rem:list")],
        [InlineKeyboardButton(text="📢 Guruhga eslatma (ro'yxatdan o'tmagan)", callback_data="rem:send")],
    ])


def recipients_kb(deps, prefix):
    kb = [[InlineKeyboardButton(text="📢 Hammaga", callback_data=f"{prefix}:all")],
          [InlineKeyboardButton(text="🔎 Xodimlarni tanlash", callback_data=f"{prefix}:search")]]
    for d in deps:
        kb.append([InlineKeyboardButton(text=f"🏢 {d['name']} ({d['count']})",
                                        callback_data=f"{prefix}:d:{d['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def bc_select_kb(employees, selected):
    rows = []
    for e in employees:
        mark = "✅" if e["id"] in selected else "⬜️"
        nm = (str(e['first_name'] or '') + ' ' + str(e['last_name'] or '')).strip()
        rows.append([InlineKeyboardButton(text=f"{mark} {nm} ({e['phone']})",
                                          callback_data=f"bcsel:{e['id']}")])
    rows.append([InlineKeyboardButton(text="🔎 Yana qidirish", callback_data="bcto:search")])
    rows.append([InlineKeyboardButton(text=f"✅ Yuborish ({len(selected)} ta)", callback_data="bcsend")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
        [InlineKeyboardButton(text="🗂 Xodim ma'lumoti", callback_data="a:empdata")],
        [InlineKeyboardButton(text="📋 To'liq to'ldirmaganlar", callback_data="ed:incomplete")],
        [InlineKeyboardButton(text="👑 Adminlar", callback_data="a:admins")],
        [InlineKeyboardButton(text="💾 Zaxira nusxa", callback_data="a:backup"),
         InlineKeyboardButton(text="♻️ Tiklash", callback_data="a:restore")],
    ])


def empdata_select_kb(employees):
    rows = []
    for e in employees:
        nm = (str(e['first_name'] or '') + ' ' + str(e['last_name'] or '')).strip()
        rows.append([InlineKeyboardButton(text=f"👤 {nm} ({e['phone']})",
                                          callback_data=f"edshow:{e['id']}")])
    rows.append([InlineKeyboardButton(text="🔎 Yana qidirish", callback_data="ed:search")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def empdata_actions_kb(emp_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬇️ Yuklab olish (ZIP)", callback_data=f"eddl:{emp_id}")],
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
        [InlineKeyboardButton(text="📆 Boshqa oy", callback_data="arep:months")],
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
        mark = "🟢" if e["telegram_id"] else "🔴"
        _nm = (str(e['first_name'] or '')+' '+str(e['last_name'] or '')).strip()
        kb.append([InlineKeyboardButton(
            text=f"{mark} {_nm} ({e['phone']})",
            callback_data=f"emp:{e['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def employee_manage_kb(emp):
    late = "✅ Kechikish hisoblanadi" if emp["count_late"] else "❌ Kechikish hisoblanmaydi"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Username", callback_data=f"edit:name:{emp['id']}")],
        [InlineKeyboardButton(text="📞 Telefon", callback_data=f"edit:phone:{emp['id']}")],
        [InlineKeyboardButton(text="🕐 Ish grafigi", callback_data=f"edit:schedule:{emp['id']}")],
        [InlineKeyboardButton(text=late, callback_data=f"togglelate:{emp['id']}")],
        [InlineKeyboardButton(text="🏢 Bo'lim tayinlash", callback_data=f"empdep:{emp['id']}")],
        [InlineKeyboardButton(text="👑 Admin qilish", callback_data=f"empadm:{emp['id']}")],
        [InlineKeyboardButton(text="📊 Hisobot (bu oy)", callback_data=f"report:{emp['id']}")],
        [InlineKeyboardButton(text="🗑 O'chirish (nofaol)", callback_data=f"deactivate:{emp['id']}")],
    ])


# ==================== A: Ma'lumot talablari ====================
def datareq_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Talab qo'shish", callback_data="dr:add")],
        [InlineKeyboardButton(text="📋 Talablar ro'yxati", callback_data="dr:list")],
    ])


def dtype_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Matn", callback_data="drtype:text")],
        [InlineKeyboardButton(text="🖼 Rasm", callback_data="drtype:photo")],
        [InlineKeyboardButton(text="📎 Fayl", callback_data="drtype:file")],
    ])


def dr_target_kb(deps):
    kb = [[InlineKeyboardButton(text="📢 Hammaga (umumiy)", callback_data="drtar:all")]]
    for d in deps:
        kb.append([InlineKeyboardButton(text=f"🏢 {d['name']}", callback_data=f"drtar:d:{d['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def dr_mandatory_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Majburiy", callback_data="drman:1"),
         InlineKeyboardButton(text="🟢 Ixtiyoriy", callback_data="drman:0")],
    ])


def dr_list_kb(reqs):
    kb = []
    for r in reqs:
        kb.append([InlineKeyboardButton(text=f"{r['title']} ({r['subs']} ta)",
                                        callback_data=f"drshow:{r['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def dr_actions_kb(req_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁 Topshirganlar", callback_data=f"drsubs:{req_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"drdel:{req_id}")],
    ])


def pending_reqs_kb(reqs):
    kb = []
    for r in reqs:
        mark = "🔴" if r["mandatory"] else "🟢"
        kb.append([InlineKeyboardButton(text=f"{mark} {r['title']}", callback_data=f"fillreq:{r['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ==================== B: So'rovnoma ====================
def survey_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ So'rovnoma yaratish", callback_data="sv:add")],
        [InlineKeyboardButton(text="📋 So'rovnomalar", callback_data="sv:list")],
    ])


def sv_target_kb(deps):
    kb = [[InlineKeyboardButton(text="📢 Hammaga", callback_data="svtar:all")]]
    for d in deps:
        kb.append([InlineKeyboardButton(text=f"🏢 {d['name']}", callback_data=f"svtar:d:{d['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def sv_addq_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yana savol", callback_data="svq:more")],
        [InlineKeyboardButton(text="✅ Tugatish va yuborish", callback_data="svq:done")],
    ])


def sv_list_kb(surveys):
    kb = []
    for s in surveys:
        act = "🟢" if s["active"] else "⚪️"
        kb.append([InlineKeyboardButton(text=f"{act} {s['title']} ({s['responders']} javob)",
                                        callback_data=f"svshow:{s['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def sv_actions_kb(sid, active):
    rows = [
        [InlineKeyboardButton(text="📊 Statistika (raqamli)", callback_data=f"svstat:{sid}")],
        [InlineKeyboardButton(text="👥 Kim nima javob berdi", callback_data=f"svdet:{sid}")],
    ]
    if active:
        rows.append([InlineKeyboardButton(text="⏹ To'xtatish", callback_data=f"svstop:{sid}")])
    rows.append([InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"svdel:{sid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pending_surveys_kb(surveys):
    kb = []
    for s in surveys:
        kb.append([InlineKeyboardButton(text=f"📊 {s['title']}", callback_data=f"svstart:{s['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def survey_options_kb(survey_id, q):
    rows = []
    for o in q["_options"]:
        rows.append([InlineKeyboardButton(
            text=o["otext"], callback_data=f"svans:{survey_id}:{q['id']}:{o['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==================== Kechikishni hisoblamaslik ====================
def exempt_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Qo'shish (sana + xodimlar)", callback_data="ex:add")],
        [InlineKeyboardButton(text="📋 Ro'yxat", callback_data="ex:list")],
    ])


def ex_select_kb(employees, selected):
    rows = []
    for e in employees:
        mark = "✅" if e["id"] in selected else "⬜️"
        nm = (str(e['first_name'] or '') + ' ' + str(e['last_name'] or '')).strip()
        rows.append([InlineKeyboardButton(text=f"{mark} {nm} ({e['phone']})",
                                          callback_data=f"exsel:{e['id']}")])
    rows.append([InlineKeyboardButton(text="🔎 Yana qidirish", callback_data="ex:search")])
    rows.append([InlineKeyboardButton(text=f"✅ Saqlash ({len(selected)} ta)", callback_data="exsave")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def exemptions_list_kb(items):
    rows = []
    for it in items[:40]:
        nm = (str(it['first_name'] or '') + ' ' + str(it['last_name'] or '')).strip()
        rows.append([InlineKeyboardButton(
            text=f"🗑 {it['day']} — {nm}", callback_data=f"exdel:{it['emp_id']}:{it['day']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settime_select_kb(employees):
    """Bitta xodim tanlash (vaqtni o'zgartirish uchun)."""
    rows = []
    for e in employees:
        nm = (str(e['first_name'] or '') + ' ' + str(e['last_name'] or '')).strip()
        rows.append([InlineKeyboardButton(text=f"👤 {nm} ({e['phone']})",
                                          callback_data=f"stemp:{e['id']}")])
    rows.append([InlineKeyboardButton(text="🔎 Yana qidirish", callback_data="st:search")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sched_unmatched_kb(names):
    """Biriktirilmagan jadval nomlari — bosilsa username so'raladi."""
    import hashlib
    rows = []
    for nm in names[:40]:
        h = hashlib.md5(nm.encode()).hexdigest()[:10]
        rows.append([InlineKeyboardButton(text=f"🔗 {nm}", callback_data=f"bind:{h}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bind_pick_kb(employees):
    rows = []
    for e in employees:
        nm = (str(e['first_name'] or '') + ' ' + str(e['last_name'] or '')).strip()
        rows.append([InlineKeyboardButton(text=f"👤 {nm} ({e['phone']})",
                                          callback_data=f"bindemp:{e['id']}")])
    rows.append([InlineKeyboardButton(text="🔎 Yana qidirish", callback_data="bind:search")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
