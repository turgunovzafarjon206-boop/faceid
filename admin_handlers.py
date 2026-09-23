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
    username = State()
    phone = State()
    schedule = State()
    countlate = State()
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
    search = State()


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


class Exempt(StatesGroup):
    date = State()
    search = State()


class SetTime(StatesGroup):
    search = State()
    date = State()
    times = State()


class SchedUpload(StatesGroup):
    wait_file = State()


class SchedBind(StatesGroup):
    search = State()


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
    await state.set_state(AddEmp.username)
    await cb.message.answer(
        "Username kiriting (guruhda ko'rinadigan nom — masalan: Zafarjon Turg'unov "
        "yoki Ismoil aka). Aynan guruhdagidek yozing:")
    await cb.answer()


@router.message(AddEmp.username, F.text)
async def add_username(msg: Message, state: FSMContext):
    await state.update_data(username=msg.text.strip())
    await state.set_state(AddEmp.phone)
    await msg.answer("Telefon raqam (masalan 901234567):")


@router.message(AddEmp.phone, F.text)
async def add_phone(msg: Message, state: FSMContext):
    await state.update_data(phone=msg.text.strip())
    await state.set_state(AddEmp.schedule)
    await msg.answer("Ish grafigi (format: 08:00-18:00).\n"
                     "Grafik kerak bo'lmasa - (chiziqcha) yuboring:")


@router.message(AddEmp.schedule, F.text)
async def add_schedule(msg: Message, state: FSMContext):
    val = msg.text.strip()
    if val == "-":
        # grafiksiz — standart qiymatlar ishlatiladi
        from config import DEFAULT_WORK_START, DEFAULT_WORK_END
        await state.update_data(ws=DEFAULT_WORK_START, we=DEFAULT_WORK_END)
    else:
        try:
            ws, we = val.split("-")
            dt.datetime.strptime(ws.strip(), "%H:%M")
            dt.datetime.strptime(we.strip(), "%H:%M")
        except ValueError:
            await msg.answer("❌ Format noto'g'ri. Masalan: 08:00-18:00 yoki - (chiziqcha)")
            return
        await state.update_data(ws=ws.strip(), we=we.strip())
    await state.set_state(None)
    await msg.answer("Kechikish hisoblansinmi?", reply_markup=kb.add_countlate_kb())


@router.callback_query(F.data.startswith("addcl:"))
async def add_countlate(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    data = await state.get_data()
    if "username" not in data:
        await cb.answer("Sessiya tugagan, qaytadan boshlang", show_alert=True)
        await state.clear()
        return
    await state.update_data(count_late=int(cb.data.split(":")[1]))
    deps = await db.list_departments()
    if not deps:
        await _create_employee(cb.message, state, dep_id=None)
    else:
        await state.set_state(AddEmp.department)
        await cb.message.answer("Bo'limni tanlang:", reply_markup=kb.add_dep_pick_kb(deps))
    await cb.answer()


@router.callback_query(F.data.startswith("adddep:"))
async def add_pick_dep(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    dep_id = int(cb.data.split(":")[1]) or None
    await _create_employee(cb.message, state, dep_id=dep_id)
    await cb.answer()


async def _create_employee(target, state: FSMContext, dep_id):
    data = await state.get_data()
    try:
        emp_id = await db.add_employee(
            data["username"], "", data["phone"], "-",
            work_start=data["ws"], work_end=data["we"],
            count_late=data.get("count_late", 1))
    except Exception as e:
        await target.answer(f"❌ Xatolik (telefon takrorlangan bo'lishi mumkin):\n{e}")
        await state.clear()
        return
    if dep_id:
        await db.set_employee_department(emp_id, dep_id)
    dep_name = ""
    if dep_id:
        d = await db.get_department(dep_id)
        dep_name = f"\n🏢 Bo'lim: {d['name']}" if d else ""
    cl = "hisoblanadi" if data.get("count_late", 1) else "hisoblanmaydi"
    await state.clear()
    await target.answer(
        f"✅ Xodim qo'shildi!\n\n👤 Username: {data['username']}\n"
        f"📞 {data['phone']}\n🕐 {data['ws']}-{data['we']}\n"
        f"⏰ Kechikish: {cl}{dep_name}\n\n"
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
        linked = sum(1 for e in emps if e["telegram_id"])
        unlinked = len(emps) - linked
        await cb.message.answer(
            f"👥 Jami {len(emps)} ta xodim\n🟢 Ulangan: {linked} | 🔴 Ulanmagan: {unlinked}\n\n"
            "Xodimni tanlang:", reply_markup=kb.employees_kb(emps))
    await cb.answer()


@router.callback_query(F.data.startswith("emp:"))
async def show_emp(cb: CallbackQuery):
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    if not emp:
        return await cb.answer("Topilmadi", show_alert=True)
    bound = "✅ ulangan" if emp["telegram_id"] else "❌ ulanmagan"
    dep = "yo'q"
    if emp.get("department_id"):
        d = await db.get_department(emp["department_id"])
        dep = d["name"] if d else "yo'q"
    await cb.message.answer(
        f"👤 Username: {db.full_name(emp)}\n📞 {emp['phone']}\n"
        f"🕐 {emp['work_start']}-{emp['work_end']}\n🏢 Bo'lim: {dep}\n"
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
    await cb.message.answer(await reports.period_text(emp, first, last, "Oylik hisobot", for_admin=True))
    await cb.answer()


@router.callback_query(F.data.startswith("edit:"))
async def edit_field(cb: CallbackQuery, state: FSMContext):
    _, field, emp_id = cb.data.split(":")
    await state.set_state(EditEmp.value)
    await state.update_data(field=field, emp_id=int(emp_id))
    prompts = {
        "name": "Yangi username:",
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
            await db.update_employee(emp_id, first_name=val, last_name="")
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
    await msg.answer(f"👤 {db.full_name(emp)} yangilandi.",
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


@router.callback_query(F.data == "arep:months")
async def rep_months(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await cb.message.answer("Qaysi oy uchun Excel?",
                            reply_markup=kb.months_kb("arepmon", reports.months_list(12)))
    await cb.answer()


@router.callback_query(F.data.startswith("arepmon:"))
async def rep_month_pick(cb: CallbackQuery):
    ym = cb.data.split(":")[1]
    first, last = reports.month_bounds(ym)
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


async def _fine_mode():
    v = await db.get_setting("fine_deps")
    if v == "all":
        return "all", set()
    if not v:
        return "none", set()
    ids = set(int(x) for x in v.split(",") if x.strip().isdigit())
    return "some", ids


@router.callback_query(F.data == "a:finetoggle")
async def fine_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    deps = await db.list_departments()
    mode, ids = await _fine_mode()
    await cb.message.answer(
        "💰 Jarima qaysi bo'limlarga ko'rinsin?\n"
        "(Admin har doim ko'radi. Bo'lim tanlansa — o'sha bo'lim xodimlari ko'radi.)",
        reply_markup=kb.fine_deps_kb(deps, ids, mode))
    await cb.answer()


@router.callback_query(F.data.startswith("finedep:"))
async def fine_set(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    what = cb.data.split(":")[1]
    if what == "all":
        await db.set_setting("fine_deps", "all")
    elif what == "none":
        await db.set_setting("fine_deps", "")
    else:
        mode, ids = await _fine_mode()
        did = int(what)
        if mode != "some":
            ids = set()
        if did in ids:
            ids.discard(did)
        else:
            ids.add(did)
        await db.set_setting("fine_deps", ",".join(str(i) for i in sorted(ids)))
    deps = await db.list_departments()
    mode, ids = await _fine_mode()
    try:
        await cb.message.edit_reply_markup(reply_markup=kb.fine_deps_kb(deps, ids, mode))
    except Exception:
        pass
    await cb.answer("Saqlandi ✅")


async def _over_mode():
    v = await db.get_setting("over_deps")
    if v == "all":
        return "all", set()
    if not v:
        return "none", set()
    ids = set(int(x) for x in v.split(",") if x.strip().isdigit())
    return "some", ids


@router.callback_query(F.data == "a:overtoggle")
async def over_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    deps = await db.list_departments()
    mode, ids = await _over_mode()
    await cb.message.answer(
        "🕐 Ortiqcha ish vaqti qaysi bo'limlarga ko'rinsin?\n"
        "(Admin har doim ko'radi.)",
        reply_markup=kb.fine_deps_kb(deps, ids, mode, prefix="overdep"))
    await cb.answer()


@router.callback_query(F.data.startswith("overdep:"))
async def over_set(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    what = cb.data.split(":")[1]
    if what == "all":
        await db.set_setting("over_deps", "all")
    elif what == "none":
        await db.set_setting("over_deps", "")
    else:
        mode, ids = await _over_mode()
        did = int(what)
        if mode != "some":
            ids = set()
        if did in ids:
            ids.discard(did)
        else:
            ids.add(did)
        await db.set_setting("over_deps", ",".join(str(i) for i in sorted(ids)))
    deps = await db.list_departments()
    mode, ids = await _over_mode()
    try:
        await cb.message.edit_reply_markup(reply_markup=kb.fine_deps_kb(deps, ids, mode, prefix="overdep"))
    except Exception:
        pass
    await cb.answer("Saqlandi ✅")


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
            lines.append(f"• {db.full_name(emp)}: qayd yo'q")
            continue
        kirish = r["kirish"].strftime("%H:%M") if r["kirish"] else "—"
        chiqish = r["chiqish"].strftime("%H:%M") if r["chiqish"] else "—"
        late = f" ⏰+{r['kechikish_min']}daq" if r["kech_qoldi"] else ""
        lines.append(f"• {db.full_name(emp)}: "
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


@router.callback_query(F.data == "bcto:search")
async def bcast_search_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(Broadcast.search)
    await cb.message.answer("Xodim ismi (username) yoki telefon qidiruv so'zini yozing:")
    await cb.answer()


@router.message(Broadcast.search, F.text)
async def bcast_search_results(msg: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("kind"):
        await msg.answer("Avval xabar yuboring (matn/rasm/video).")
        return
    found = await db.search_employees(msg.text.strip(), linked_only=True)
    await state.set_state(None)
    selected = set(data.get("selected", []))
    found_min = [{"id": e["id"], "first_name": e["first_name"],
                  "last_name": e["last_name"], "phone": e["phone"]} for e in found]
    prev = {f["id"]: f for f in data.get("bc_found", [])}
    for f in found_min:
        prev[f["id"]] = f
    await state.update_data(bc_found=list(prev.values()))
    if not found:
        await msg.answer("Hech kim topilmadi. «🔎 Yana qidirish» orqali qayta urinib ko'ring.",
                         reply_markup=kb.bc_select_kb(list(prev.values()), selected))
        return
    await msg.answer("Belgilang va «✅ Yuborish» bosing:",
                     reply_markup=kb.bc_select_kb(found_min, selected))


@router.callback_query(F.data.startswith("bcsel:"))
async def bcast_select_toggle(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = set(data.get("selected", []))
    eid = int(cb.data.split(":")[1])
    if eid in selected:
        selected.discard(eid)
    else:
        selected.add(eid)
    await state.update_data(selected=list(selected))
    await cb.answer("✅ belgilandi" if eid in selected else "olib tashlandi")
    found = data.get("bc_found", [])
    shown_ids = []
    try:
        for r in cb.message.reply_markup.inline_keyboard:
            cd = r[0].callback_data
            if cd and cd.startswith("bcsel:"):
                shown_ids.append(int(cd.split(":")[1]))
    except Exception:
        pass
    shown = [f for f in found if f["id"] in shown_ids] or found
    try:
        await cb.message.edit_reply_markup(reply_markup=kb.bc_select_kb(shown, selected))
    except Exception:
        pass


@router.callback_query(F.data == "bcsend")
async def bcast_send_selected(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kind = data.get("kind")
    payload = data.get("payload", {})
    selected = list(data.get("selected", []))
    if not kind or not selected:
        await cb.answer("Hech kim tanlanmagan", show_alert=True)
        return
    await state.clear()
    await cb.answer("Yuborilmoqda...")
    ok = fail = 0
    for eid in selected:
        emp = await db.get_employee_by_id(eid)
        if not emp or not emp["telegram_id"]:
            continue
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
    await cb.message.answer(f"✅ Tanlangan xodimlarga yuborildi: {ok} ta\n❌ Yuborilmadi: {fail} ta",
                            reply_markup=kb.admin_menu())


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
        link = "🟢" if m["telegram_id"] else "🔴"
        lines.append(f"{link} {db.full_name(m)} ({m['phone']})")
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
@router.callback_query(F.data == "rem:data")
async def rem_data(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await cb.answer("Yuborilmoqda...")
    tpl = await db.get_template("tpl_warn", db.DEFAULT_TPL_WARN)
    emps = await db.linked_employees()
    sent = 0
    for emp in emps:
        pending = await db.pending_requests_for(emp)
        if not pending:
            continue
        lines = [tpl, "", "Quyidagi ma'lumotlar to'ldirilmagan:"]
        for p in pending:
            dl = f" — {p['deadline']} gacha" if p["deadline"] else ""
            mark = "🔴" if p["mandatory"] else "🟢"
            lines.append(f"{mark} {p['title']}{dl}")
        lines.append("\nTo'ldirish uchun pastdagi tugmani bosing:")
        try:
            await cb.bot.send_message(emp["telegram_id"], "\n".join(lines),
                                      reply_markup=kb.pending_reqs_kb(pending))
            sent += 1
        except Exception:
            pass
    await cb.message.answer(
        f"✅ Eslatma {sent} ta xodimga yuborildi (to'ldirilmagan ma'lumoti borlarga).",
        reply_markup=kb.admin_menu())


@router.callback_query(F.data == "rem:list")
async def rem_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    unlinked = await db.unlinked_employees()
    unknown = await db.list_unknown()
    lines = ["📋 Ma'lumot to'ldirmaganlar:\n"]
    lines.append(f"⛔ Botga ulanmagan xodimlar ({len(unlinked)}):")
    for e in unlinked[:50]:
        lines.append(f"  • {db.full_name(e)} ({e['phone']})")
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

    names = "\n".join(f"• {db.full_name(e)}" for e in unlinked)
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
                note = db.full_name(e)
                break
    else:
        emp = await db.get_employee_by_name(val)
        if emp and emp["telegram_id"]:
            tg_id = emp["telegram_id"]
            note = db.full_name(emp)
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
    note = db.full_name(emp)
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
        await msg.bot.send_message(emp_tg, f"👤 HR javobi:\n\n{msg.text}",
                                   reply_markup=kb.hr_user_reply_kb())
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


# ==================== Kechikishni hisoblamaslik (kechirim) ====================
@router.callback_query(F.data == "a:exempt")
async def exempt_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await cb.message.answer(
        "🚫 Kechikishni hisoblamaslik.\n"
        "Tanlangan xodimlar uchun tanlangan kunda kech qolish (va jarima) hisoblanmaydi.",
        reply_markup=kb.exempt_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "ex:add")
async def exempt_add(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(Exempt.date)
    await state.update_data(ex_selected=[])
    await cb.message.answer("Sana kiriting (YYYY-MM-DD, masalan 2026-09-06):")
    await cb.answer()


@router.message(Exempt.date, F.text)
async def exempt_date(msg: Message, state: FSMContext):
    try:
        day = dt.datetime.strptime(msg.text.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        await msg.answer("❌ Noto'g'ri format. Masalan: 2026-09-06")
        return
    await state.update_data(ex_day=day)
    await state.set_state(Exempt.search)
    await msg.answer(f"📅 Sana: {day}\nEndi xodim ismini (username) qidiring:")


@router.callback_query(F.data == "ex:search")
async def exempt_search_again(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Exempt.search)
    await cb.message.answer("Xodim ismini yozing:")
    await cb.answer()


@router.message(Exempt.search, F.text)
async def exempt_search(msg: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("ex_day"):
        await msg.answer("Avval sanani kiriting.")
        return
    found = await db.search_employees(msg.text.strip(), linked_only=False)
    await state.set_state(None)
    selected = set(data.get("ex_selected", []))
    # topilganlarni holatda saqlaymiz (tugmalarni qayta chizish uchun)
    found_min = [{"id": e["id"], "first_name": e["first_name"],
                  "last_name": e["last_name"], "phone": e["phone"]} for e in found]
    # avvalgi topilganlarni ham saqlab qolamiz (ko'p qidiruvda tanlov yo'qolmasin)
    prev = {f["id"]: f for f in data.get("ex_found", [])}
    for f in found_min:
        prev[f["id"]] = f
    await state.update_data(ex_found=list(prev.values()))
    if not found:
        await msg.answer("Topilmadi. «🔎 Yana qidirish» bilan urinib ko'ring.",
                         reply_markup=kb.ex_select_kb(list(prev.values()), selected))
        return
    await msg.answer(f"📅 {data['ex_day']} — belgilang va «✅ Saqlash»:",
                     reply_markup=kb.ex_select_kb(found_min, selected))


@router.callback_query(F.data.startswith("exsel:"))
async def exempt_toggle(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = set(data.get("ex_selected", []))
    eid = int(cb.data.split(":")[1])
    if eid in selected:
        selected.discard(eid)
    else:
        selected.add(eid)
    await state.update_data(ex_selected=list(selected))
    await cb.answer("✅ belgilandi" if eid in selected else "olib tashlandi")
    found = data.get("ex_found", [])
    # joriy xabardagi ro'yxatni ko'rsatamiz
    shown_ids = []
    try:
        for r in cb.message.reply_markup.inline_keyboard:
            cd = r[0].callback_data
            if cd and cd.startswith("exsel:"):
                shown_ids.append(int(cd.split(":")[1]))
    except Exception:
        pass
    shown = [f for f in found if f["id"] in shown_ids] or found
    try:
        await cb.message.edit_reply_markup(reply_markup=kb.ex_select_kb(shown, selected))
    except Exception:
        pass


@router.callback_query(F.data == "exsave")
async def exempt_save(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    day = data.get("ex_day")
    selected = data.get("ex_selected", [])
    if not day or not selected:
        return await cb.answer("Hech kim belgilanmagan", show_alert=True)
    try:
        await db.add_exemptions(selected, day)
    except Exception as e:
        await cb.answer()
        await cb.message.answer(f"❌ Xatolik: {e}", reply_markup=kb.admin_menu())
        return
    await state.clear()
    await cb.answer("Saqlandi ✅")
    await cb.message.answer(
        f"✅ {len(selected)} ta xodim uchun {day} kuni kechikish hisoblanmaydi.",
        reply_markup=kb.admin_menu())


@router.callback_query(F.data == "ex:list")
async def exempt_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    items = await db.list_exemptions()
    if not items:
        await cb.message.answer("Hozircha kechirim yo'q.")
    else:
        await cb.message.answer("📋 Kechirimlar (o'chirish uchun bosing):",
                                reply_markup=kb.exemptions_list_kb(items))
    await cb.answer()


@router.callback_query(F.data.startswith("exdel:"))
async def exempt_delete(cb: CallbackQuery):
    _, eid, day = cb.data.split(":")
    await db.remove_exemption(int(eid), day)
    await cb.answer("O'chirildi")
    await cb.message.answer("🗑 Kechirim o'chirildi.")


# ==================== Vaqtni o'zgartirish (manual) ====================
import re as _re


def _parse_times(text):
    """'Kirish: 8:50 Chiqish: 19:00' -> ('08:50','19:00'). Faqat bittasi ham bo'lishi mumkin."""
    t = text.lower().replace(".", ":")
    kir = _re.search(r"kir\w*\D*(\d{1,2}:\d{2})", t)
    chiq = _re.search(r"chiq\w*\D*(\d{1,2}:\d{2})", t)
    kh = kir.group(1) if kir else None
    ch = chiq.group(1) if chiq else None
    if not kh and not ch:
        times = _re.findall(r"(\d{1,2}:\d{2})", t)
        if len(times) >= 2:
            kh, ch = times[0], times[1]
        elif len(times) == 1:
            kh = times[0]

    def norm(x):
        if not x:
            return None
        hh, mm = x.split(":")
        return f"{int(hh):02d}:{int(mm):02d}"
    return norm(kh), norm(ch)


@router.callback_query(F.data == "a:settime")
async def settime_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(SetTime.search)
    await cb.message.answer("🕒 Vaqtni o'zgartirish.\nXodim ismini (username) qidiring:")
    await cb.answer()


@router.callback_query(F.data == "st:search")
async def settime_search_again(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SetTime.search)
    await cb.message.answer("Xodim ismini yozing:")
    await cb.answer()


@router.message(SetTime.search, F.text)
async def settime_search(msg: Message, state: FSMContext):
    found = await db.search_employees(msg.text.strip(), linked_only=False)
    if not found:
        await msg.answer("Topilmadi. Qaytadan qidiring:")
        return
    await state.set_state(None)
    await msg.answer("Xodimni tanlang:", reply_markup=kb.settime_select_kb(found))


@router.callback_query(F.data.startswith("stemp:"))
async def settime_pick(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    await state.update_data(st_emp=emp["id"], st_name=db.full_name(emp))
    await state.set_state(SetTime.date)
    await cb.message.answer(f"👤 {db.full_name(emp)}\nSana kiriting (YYYY-MM-DD):")
    await cb.answer()


@router.message(SetTime.date, F.text)
async def settime_date(msg: Message, state: FSMContext):
    try:
        day = dt.datetime.strptime(msg.text.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        await msg.answer("❌ Noto'g'ri format. Masalan: 2026-09-06")
        return
    await state.update_data(st_day=day)
    await state.set_state(SetTime.times)
    await msg.answer("Vaqtni kiriting. Masalan:\n"
                     "«Kirish: 8:50 Chiqish: 19:00»\n"
                     "yoki faqat «Kirish: 8:50» yoki faqat «Chiqish: 19:00»")


@router.message(SetTime.times, F.text)
async def settime_apply(msg: Message, state: FSMContext):
    data = await state.get_data()
    kh, ch = _parse_times(msg.text)
    if not kh and not ch:
        await msg.answer("❌ Vaqt topilmadi. Masalan: Kirish: 8:50 Chiqish: 19:00")
        return
    await db.set_manual_attendance(data["st_emp"], data["st_day"], kh, ch)
    await state.clear()
    parts = []
    parts.append(f"Kirish: {kh}" if kh else "Kirish: -")
    parts.append(f"Chiqish: {ch}" if ch else "Chiqish: -")
    await msg.answer(
        f"✅ {data['st_name']} — {data['st_day']}\n" + "  ".join(parts) +
        "\nVaqt yangilandi.", reply_markup=kb.admin_menu())


# ==================== Dars jadvali (HolliHop) ====================
import hashlib as _hashlib


@router.callback_query(F.data == "a:schedupload")
async def sched_upload_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(SchedUpload.wait_file)
    await cb.message.answer(
        "📅 Dars jadvali (Excel) faylini yuboring.\n"
        "HolliHop'dagi «Расписание преподавателей» eksportini yuklang. "
        "Eski jadval yangisi bilan almashtiriladi (biriktirishlar saqlanadi).")
    await cb.answer()


@router.message(SchedUpload.wait_file, F.document)
async def sched_upload_file(msg: Message, state: FSMContext):
    doc = msg.document
    if not (doc.file_name or "").lower().endswith((".xlsx", ".xls")):
        await msg.answer("❌ Faqat Excel (.xlsx) fayl yuboring.")
        return
    await state.clear()
    await msg.answer("⏳ O'qilmoqda...")
    path = f"/tmp/sched_{doc.file_unique_id}.xlsx"
    await msg.bot.download(doc, destination=path)
    try:
        import schedule_import
        entries, teachers = schedule_import.parse_schedule_file(path)
        await db.import_schedule(entries)
    except Exception as e:
        await msg.answer(f"❌ Faylni o'qishda xatolik: {e}", reply_markup=kb.admin_menu())
        return
    unmatched = await db.unmatched_schedule_names()
    txt = (f"✅ Jadval yuklandi.\n"
           f"👨‍🏫 Ustozlar: {len(teachers)}, yozuvlar: {len(entries)}\n")
    if unmatched:
        txt += (f"\n⚠️ {len(unmatched)} ta ism botdagi username bilan mos kelmadi.\n"
                "«🔗 Ismlarni biriktirish» orqali ularni qo'lda bog'lang.")
    else:
        txt += "\nBarcha ismlar mos keldi ✅"
    await msg.answer(txt, reply_markup=kb.admin_menu())


@router.callback_query(F.data == "a:schedbind")
async def sched_bind_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    unmatched = await db.unmatched_schedule_names()
    if not unmatched:
        await cb.message.answer("✅ Barcha jadval ismlari botdagi xodimlarga bog'langan.")
        return await cb.answer()
    # hash -> name xaritasini settingsga saqlaymiz (callback qisqa bo'lishi uchun)
    import json
    hmap = {_hashlib.md5(n.encode()).hexdigest()[:10]: n for n in unmatched}
    await db.set_setting("_bindmap", json.dumps(hmap, ensure_ascii=False))
    await cb.message.answer(
        "🔗 Quyidagi ismlar botda topilmadi. Har birini bosib, botdagi xodimni tanlang:",
        reply_markup=kb.sched_unmatched_kb(unmatched))
    await cb.answer()


@router.callback_query(F.data.startswith("bind:"))
async def sched_bind_pick(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    part = cb.data.split(":", 1)[1]
    if part == "search":
        await cb.message.answer("Xodim ismini (username) qidiring:")
        await state.set_state(SchedBind.search)
        return await cb.answer()
    import json
    hmap = json.loads(await db.get_setting("_bindmap") or "{}")
    sched_name = hmap.get(part)
    if not sched_name:
        return await cb.answer("Eskirgan, qaytadan oching", show_alert=True)
    await state.update_data(bind_name=sched_name)
    # familiya bo'yicha avto-qidiruv — admin yozmasdan o'xshashlardan tanlaydi
    surname = sched_name.split()[0] if sched_name.split() else sched_name
    found = await db.search_employees(surname.strip("."), linked_only=False)
    if found:
        await state.set_state(None)
        await cb.message.answer(
            f"«{sched_name}» kimga tegishli? O'xshashlardan tanlang "
            "(yoki «🔎 Yana qidirish»):", reply_markup=kb.bind_pick_kb(found))
    else:
        await state.set_state(SchedBind.search)
        await cb.message.answer(f"«{sched_name}» kimga tegishli? Botdagi ismni qidiring:")
    await cb.answer()


@router.message(SchedBind.search, F.text)
async def sched_bind_search(msg: Message, state: FSMContext):
    found = await db.search_employees(msg.text.strip(), linked_only=False)
    if not found:
        await msg.answer("Topilmadi. Qaytadan qidiring:")
        return
    await state.set_state(None)
    await msg.answer("Tanlang:", reply_markup=kb.bind_pick_kb(found))


@router.callback_query(F.data.startswith("bindemp:"))
async def sched_bind_save(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    data = await state.get_data()
    sched_name = data.get("bind_name")
    if not sched_name:
        return await cb.answer("Avval jadval ismini tanlang", show_alert=True)
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    await db.add_alias(sched_name, emp["id"])
    await state.clear()
    await cb.answer("Biriktirildi ✅")
    await cb.message.answer(
        f"🔗 «{sched_name}» → {db.full_name(emp)} ga biriktirildi.\n"
        "Qolganlarini biriktirish uchun «🔗 Ismlarni biriktirish» ni qayta bosing.",
        reply_markup=kb.admin_menu())
