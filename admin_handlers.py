"""Admin panel: FaceID boshqarish (sozlama+Excel hisobot), Ma'lumotlar, Xabar."""
import datetime as dt
import calendar
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
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
    search = State()
    dates = State()
    time = State()


class SetTime(StatesGroup):
    search = State()
    date = State()
    times = State()


class SchedUpload(StatesGroup):
    wait_file = State()


class SchedBind(StatesGroup):
    search = State()


class BranchState(StatesGroup):
    name = State()
    bulk = State()


class LessonImg(StatesGroup):
    photo = State()


class AttXls(StatesGroup):
    wait_file = State()
    bind_search = State()


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
        await _ask_branch_or_create(cb.message, state, dep_id=None)
    else:
        await state.set_state(AddEmp.department)
        await cb.message.answer("Bo'limni tanlang:", reply_markup=kb.add_dep_pick_kb(deps))
    await cb.answer()


@router.callback_query(F.data.startswith("adddep:"))
async def add_pick_dep(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    dep_id = int(cb.data.split(":")[1]) or None
    await _ask_branch_or_create(cb.message, state, dep_id=dep_id)
    await cb.answer()


async def _ask_branch_or_create(target, state: FSMContext, dep_id):
    await state.update_data(dep_id=dep_id)
    branches = await db.list_branches()
    if not branches:
        await _create_employee(target, state, dep_id=dep_id, branch_id=None)
        return
    await state.set_state(None)
    await target.answer("Filialni tanlang:", reply_markup=kb.add_branch_pick_kb(branches))


@router.callback_query(F.data.startswith("addbr:"))
async def add_pick_branch(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    data = await state.get_data()
    if "username" not in data:
        await cb.answer("Sessiya tugagan, qaytadan boshlang", show_alert=True)
        await state.clear()
        return
    branch_id = int(cb.data.split(":")[1]) or None
    await _create_employee(cb.message, state, dep_id=data.get("dep_id"), branch_id=branch_id)
    await cb.answer()


async def _create_employee(target, state: FSMContext, dep_id, branch_id=None):
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
    if branch_id:
        await db.set_employee_branch(emp_id, branch_id)
    dep_name = ""
    if dep_id:
        d = await db.get_department(dep_id)
        dep_name = f"\n🏢 Bo'lim: {d['name']}" if d else ""
    br_name = ""
    if branch_id:
        b = await db.get_branch(branch_id)
        br_name = f"\n🏬 Filial: {b['name']}" if b else ""
    cl = "hisoblanadi" if data.get("count_late", 1) else "hisoblanmaydi"
    await state.clear()
    await target.answer(
        f"✅ Xodim qo'shildi!\n\n👤 Username: {data['username']}\n"
        f"📞 {data['phone']}\n🕐 {data['ws']}-{data['we']}\n"
        f"⏰ Kechikish: {cl}{dep_name}{br_name}\n\n"
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
    br = "yo'q"
    if emp.get("branch_id"):
        b = await db.get_branch(emp["branch_id"])
        br = b["name"] if b else "yo'q"
    await cb.message.answer(
        f"👤 Username: {db.full_name(emp)}\n📞 {emp['phone']}\n"
        f"🕐 {emp['work_start']}-{emp['work_end']}\n🏢 Bo'lim: {dep}\n🏬 Filial: {br}\n"
        f"👔 Rol: {db.ROLE_NAMES.get(await db.get_role(emp['id']), 'yo‘q')}\n"
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
async def _scope_label(state: FSMContext):
    data = await state.get_data()
    kind, sid = data.get("rep_scope"), data.get("rep_scope_id")
    if kind == "dep":
        d = await db.get_department(sid)
        return f"🏢 {d['name']}" if d else "Hamma xodim"
    if kind == "branch":
        b = await db.get_branch(sid)
        return f"🏬 {b['name']}" if b else "Hamma xodim"
    return "Hamma xodim"


@router.callback_query(F.data == "a:report")
async def report_menu(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await cb.message.answer("Qaysi davr uchun Excel hisobot?",
                            reply_markup=kb.admin_report_kb(await _scope_label(state)))
    await cb.answer()


@router.callback_query(F.data == "arep:scope")
async def report_scope(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    deps = await db.list_departments()
    branches = await db.list_branches()
    await cb.message.answer("Hisobot kim uchun olinsin?",
                            reply_markup=kb.report_scope_kb(deps, branches))
    await cb.answer()


@router.callback_query(F.data.startswith("ascope:"))
async def report_scope_set(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    parts = cb.data.split(":")
    if parts[1] == "all":
        await state.update_data(rep_scope=None, rep_scope_id=None)
    elif parts[1] == "d":
        await state.update_data(rep_scope="dep", rep_scope_id=int(parts[2]))
    else:
        await state.update_data(rep_scope="branch", rep_scope_id=int(parts[2]))
    label = await _scope_label(state)
    await cb.answer("Tanlandi ✅")
    await cb.message.answer(f"👥 Hisobot qamrovi: {label}\nEndi davrni tanlang:",
                            reply_markup=kb.admin_report_kb(label))


async def _scoped_employees(state: FSMContext):
    data = await state.get_data()
    kind, sid = data.get("rep_scope"), data.get("rep_scope_id")
    if kind == "dep":
        return await db.department_members(sid), await _scope_label(state)
    if kind == "branch":
        return await db.branch_members(sid), await _scope_label(state)
    return await db.list_employees(), "Hamma xodim"


async def _send_excel(target, day_from, day_to, title, state=None):
    if state is not None:
        emps, label = await _scoped_employees(state)
    else:
        emps, label = await db.list_employees(), "Hamma xodim"
    if not emps:
        await target.answer("Bu qamrovda xodim yo'q.")
        return
    path = await reports.build_period_excel(emps, day_from, day_to, title)
    await target.answer_document(
        FSInputFile(path, filename=f"{title.replace(' ', '_')}_{day_from}_{day_to}.xlsx"),
        caption=f"📊 {title}\n👥 {label}\n{day_from} … {day_to}")


@router.callback_query(F.data == "arep:today")
async def rep_today(cb: CallbackQuery, state: FSMContext):
    day = dt.datetime.now(TZ).strftime("%Y-%m-%d")
    await cb.answer("Tayyorlanmoqda...")
    await _send_excel(cb.message, day, day, "Kunlik hisobot", state)


@router.callback_query(F.data == "arep:month")
async def rep_month(cb: CallbackQuery, state: FSMContext):
    first, last = _month_range()
    await cb.answer("Tayyorlanmoqda...")
    await _send_excel(cb.message, first, last, "Oylik hisobot", state)


@router.callback_query(F.data == "arep:months")
async def rep_months(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await cb.message.answer("Qaysi oy uchun Excel?",
                            reply_markup=kb.months_kb("arepmon", reports.months_list(12)))
    await cb.answer()


@router.callback_query(F.data.startswith("arepmon:"))
async def rep_month_pick(cb: CallbackQuery, state: FSMContext):
    ym = cb.data.split(":")[1]
    first, last = reports.month_bounds(ym)
    await cb.answer("Tayyorlanmoqda...")
    await _send_excel(cb.message, first, last, "Oylik hisobot", state)


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
    await _send_excel(msg, d1, d2, "Davr hisoboti", state)


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
    unknown = await db.unknown_pending()
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
        "🚫 Kechikishni hisoblamaslik.\n\n"
        "📅 Kun uchun — tanlangan kunlarda butun kun kechikish (va jarima) hisoblanmaydi.\n"
        "🕒 Vaqt uchun — siz kiritgan vaqtdan boshlab kechikish hisoblanadi "
        "(masalan 09:30 kiritsangiz, 09:30 dan keyin kelganlar shundan hisoblab kech qoladi).\n\n"
        "Tartib: avval xodimlarni tanlaysiz, keyin sanalarni (bir nechta bo'lishi mumkin).",
        reply_markup=kb.exempt_menu_kb())
    await cb.answer()


async def _exempt_start(cb, state, mode):
    await state.set_state(Exempt.search)
    await state.update_data(ex_selected=[], ex_found=[], ex_days=[], ex_mode=mode, ex_from=None)
    title = "📅 Kun uchun" if mode == "day" else "🕒 Vaqt uchun"
    await cb.message.answer(f"{title}.\nAvval xodim ismini (username) qidiring:")
    await cb.answer()


@router.callback_query(F.data == "ex:add")
async def exempt_add(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await _exempt_start(cb, state, "day")


@router.callback_query(F.data == "ex:addtime")
async def exempt_add_time(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await _exempt_start(cb, state, "time")


@router.callback_query(F.data == "ex:search")
async def exempt_search_again(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Exempt.search)
    await cb.message.answer("Xodim ismini yozing:")
    await cb.answer()


@router.message(Exempt.search, F.text)
async def exempt_search(msg: Message, state: FSMContext):
    data = await state.get_data()
    found = await db.search_employees(msg.text.strip(), linked_only=False)
    await state.set_state(None)
    selected = set(data.get("ex_selected", []))
    found_min = [{"id": e["id"], "first_name": e["first_name"],
                  "last_name": e["last_name"], "phone": e["phone"]} for e in found]
    prev = {f["id"]: f for f in data.get("ex_found", [])}
    for f in found_min:
        prev[f["id"]] = f
    await state.update_data(ex_found=list(prev.values()))
    if not found:
        await msg.answer("Topilmadi. «🔎 Yana qidirish» bilan urinib ko'ring.",
                         reply_markup=kb.ex_select_kb(list(prev.values()), selected))
        return
    await msg.answer("Xodimlarni belgilang (bir nechta bo'lishi mumkin), "
                     "so'ng «➡️ Davom etish»:",
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


@router.callback_query(F.data == "exnext")
async def exempt_next(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    data = await state.get_data()
    selected = data.get("ex_selected", [])
    if not selected:
        return await cb.answer("Avval xodim belgilang", show_alert=True)
    names = []
    for f in data.get("ex_found", []):
        if f["id"] in selected:
            names.append((str(f['first_name'] or '') + ' ' + str(f['last_name'] or '')).strip())
    if data.get("ex_mode") == "time":
        await state.set_state(Exempt.time)
        await cb.message.answer(
            f"👥 Tanlandi: {len(selected)} ta ({', '.join(names[:10])})\n\n"
            "🕒 Vaqtni kiriting (HH:MM). Shu vaqtdan boshlab kechikish hisoblanadi.\n"
            "Masalan: 09:30")
    else:
        await state.set_state(Exempt.dates)
        await cb.message.answer(
            f"👥 Tanlandi: {len(selected)} ta ({', '.join(names[:10])})\n\n"
            "📅 Endi sanalarni yuboring (YYYY-MM-DD).\n"
            "Bir nechta kun bo'lsa: har birini alohida yuboring yoki bittada vergul/probel bilan.\n"
            "Masalan: <code>2026-09-06, 2026-09-07</code>\n"
            "Oraliq ham mumkin: <code>2026-09-06..2026-09-10</code>")
    await cb.answer()


@router.message(Exempt.time, F.text)
async def exempt_time(msg: Message, state: FSMContext):
    txt = msg.text.strip().replace(".", ":")
    try:
        t = dt.datetime.strptime(txt, "%H:%M")
    except ValueError:
        try:
            t = dt.datetime.strptime(txt, "%H")
        except ValueError:
            await msg.answer("❌ Noto'g'ri format. Masalan: 09:30")
            return
    await state.update_data(ex_from=t.hour * 60 + t.minute)
    await state.set_state(Exempt.dates)
    await msg.answer(
        f"🕒 {t.strftime('%H:%M')} dan boshlab hisoblanadi.\n\n"
        "📅 Endi sanalarni yuboring (YYYY-MM-DD).\n"
        "Bir nechta kun: vergul bilan yoki oraliq <code>2026-09-06..2026-09-10</code>")


_DAY_RE = None


def _parse_days(text):
    """Matndan sanalarni ajratadi. Qabul qilinadi (aralash ham bo'ladi):
       2026-09-06 · 2026-09-06..2026-09-10 · 6.09 · 06.09.2026 ·
       6-sentyabr · 6 sentyabr · 6-10 sentyabr · 6, 7, 8 sentyabr · 6 7 8
       (oy yozilmagan sonlar — keyingi/oldingi yozilgan oyga, bo'lmasa joriy oyga tegishli)."""
    global _DAY_RE
    import group_handlers
    if _DAY_RE is None:
        _DAY_RE = _re.compile(
            r"(?P<iso1>\d{4}-\d{1,2}-\d{1,2})(?:\s*\.\.\s*(?P<iso2>\d{4}-\d{1,2}-\d{1,2}))?"
            r"|(?P<dd>\d{1,2})\.(?P<mm>\d{1,2})(?:\.(?P<yy>\d{2,4}))?(?!\d)"
            r"|(?P<n1>\d{1,2})(?:\s*(?:\.\.|-|–|—)\s*(?P<n2>\d{1,2})(?!\d))?"
            r"(?:\s*-?\s*(?P<mw>[^\W\d_][\w'ʻʼ‘’`]*))?")
    today = dt.datetime.now(TZ).date()
    year = today.year
    items, bad = [], []   # items: (kind, payload) ; kind: 'days' | 'nums' | 'month'
    pos = 0
    t = text or ""
    for m in _DAY_RE.finditer(t):
        gap = t[pos:m.start()]
        if _re.sub(r"[\s,;]+", "", gap):
            bad.append(gap.strip(" ,;"))
        pos = m.end()
        try:
            if m.group("iso1"):
                d1 = dt.datetime.strptime(m.group("iso1"), "%Y-%m-%d").date()
                d2 = dt.datetime.strptime(m.group("iso2"), "%Y-%m-%d").date() if m.group("iso2") else d1
                items.append(("days", (d1, d2)))
            elif m.group("dd"):
                yy = m.group("yy")
                y = int(yy) + (2000 if yy and len(yy) == 2 else 0) if yy else year
                d = dt.date(y, int(m.group("mm")), int(m.group("dd")))
                items.append(("days", (d, d)))
            else:
                a = int(m.group("n1"))
                b = int(m.group("n2")) if m.group("n2") else a
                mw = m.group("mw")
                month = None
                if mw:
                    month = group_handlers._month_from_word(mw)
                    if not month:
                        bad.append(m.group(0).strip())
                        continue
                items.append(("nums", (a, b, month, m.group(0).strip())))
        except ValueError:
            bad.append(m.group(0).strip())
    tail = t[pos:]
    if _re.sub(r"[\s,;]+", "", tail):
        bad.append(tail.strip(" ,;"))

    # Oy yozilmagan sonlarga oy biriktirish: avval keyingi, so'ng oldingi oy
    months = [it[1][2] if it[0] == "nums" else None for it in items]
    resolved = []
    for i, (kind, pl) in enumerate(items):
        if kind == "days":
            resolved.append(pl)
            continue
        a, b, month, raw = pl
        if not month:
            month = next((x for x in months[i + 1:] if x), None) or \
                next((x for x in reversed(months[:i]) if x), None) or today.month
        try:
            d1, d2 = dt.date(year, month, min(a, b)), dt.date(year, month, max(a, b))
        except ValueError:
            bad.append(raw)
            continue
        resolved.append((d1, d2))

    days = []
    for d1, d2 in resolved:
        if d2 < d1:
            d1, d2 = d2, d1
        cur = d1
        while cur <= d2 and len(days) < 120:
            iso = cur.isoformat()
            if iso not in days:
                days.append(iso)
            cur += dt.timedelta(days=1)
    days.sort()
    return days, [b for b in bad if b]


@router.message(Exempt.dates, F.text)
async def exempt_dates(msg: Message, state: FSMContext):
    data = await state.get_data()
    days, bad = _parse_days(msg.text)
    if not days:
        await msg.answer("❌ Sana topilmadi. Masalan: 2026-09-06 yoki 2026-09-06..2026-09-10")
        return
    have = list(data.get("ex_days", []))
    for d in days:
        if d not in have:
            have.append(d)
    have.sort()
    await state.update_data(ex_days=have)
    note = f"\n⚠️ Tushunilmadi: {', '.join(bad)}" if bad else ""
    await msg.answer(
        f"📅 Tanlangan kunlar: {len(have)} ta{note}\n"
        "Yana sana yuborishingiz yoki «✅ Saqlash» bosishingiz mumkin:",
        reply_markup=kb.ex_days_kb(have, data.get("ex_mode", "day")))


@router.callback_query(F.data.startswith("exday:"))
async def exempt_day_remove(cb: CallbackQuery, state: FSMContext):
    day = cb.data.split(":", 1)[1]
    data = await state.get_data()
    have = [d for d in data.get("ex_days", []) if d != day]
    await state.update_data(ex_days=have)
    await cb.answer("O'chirildi")
    try:
        await cb.message.edit_reply_markup(
            reply_markup=kb.ex_days_kb(have, data.get("ex_mode", "day")))
    except Exception:
        pass


@router.callback_query(F.data == "exsave")
async def exempt_save(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("ex_selected", [])
    days = data.get("ex_days", [])
    if not selected:
        return await cb.answer("Xodim belgilanmagan", show_alert=True)
    if not days:
        return await cb.answer("Sana kiritilmagan", show_alert=True)
    mode = data.get("ex_mode", "day")
    from_min = data.get("ex_from") if mode == "time" else None
    try:
        for day in days:
            await db.add_exemptions(selected, day, from_min)
    except Exception as e:
        await cb.answer()
        await cb.message.answer(f"❌ Xatolik: {e}", reply_markup=kb.admin_menu())
        return
    await state.clear()
    await cb.answer("Saqlandi ✅")
    if from_min is None:
        tail = "butun kun kechikish hisoblanmaydi."
    else:
        tail = f"kechikish {from_min // 60:02d}:{from_min % 60:02d} dan boshlab hisoblanadi."
    await cb.message.answer(
        f"✅ {len(selected)} ta xodim × {len(days)} kun uchun {tail}\n"
        f"📅 Kunlar: {', '.join(days[:10])}" + (" …" if len(days) > 10 else ""),
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
    await cb.message.answer(
        f"👤 {db.full_name(emp)}\n"
        "📅 Kun(lar)ni yozing — bittasini yoki bir nechtasini birdaniga:\n"
        "• <code>6-sentyabr</code>\n"
        "• <code>6, 7, 9 sentyabr</code>\n"
        "• <code>6-10 sentyabr</code> (oraliq)\n"
        "• <code>2026-09-06</code> yoki <code>6.09</code>\n\n"
        "Har kunga boshqa vaqt kerak bo'lsa — har qatorga kun va vaqtni yozing:\n"
        "<code>6-sentyabr Kirish: 8:50 Chiqish: 19:00\n"
        "7-sentyabr Kirish: 9:05</code>")
    await cb.answer()


_TIME_WORD_RE = _re.compile(
    r"(kir\w*|chiq\w*|кир\w*|чиқ\w*|чик\w*)\s*:?\s*\d{1,2}[:.]\d{2}", _re.IGNORECASE)


def _days_label(days):
    if len(days) <= 6:
        return ", ".join(reports.uz_date(d) for d in days)
    return f"{reports.uz_date(days[0])} … {reports.uz_date(days[-1])} ({len(days)} kun)"


def _norm_time_words(text):
    t = text
    for a, b in (("кириш", "kirish"), ("Кириш", "Kirish"), ("КИРИШ", "kirish"),
                 ("чиқиш", "chiqish"), ("Чиқиш", "Chiqish"), ("чикиш", "chiqish"),
                 ("Чикиш", "Chiqish"), ("ЧИҚИШ", "chiqish")):
        t = t.replace(a, b)
    return t


@router.message(SetTime.date, F.text)
async def settime_date(msg: Message, state: FSMContext):
    data = await state.get_data()
    text = _norm_time_words(msg.text or "")
    # 1) Qatorma-qator: har qatorda kun + vaqt
    if _TIME_WORD_RE.search(text):
        plan, errors = [], []
        for line in [l for l in text.splitlines() if l.strip()]:
            kh, ch = _parse_times(line)
            day_part = _TIME_WORD_RE.sub(" ", line)
            days, bad = _parse_days(day_part)
            if not days or (not kh and not ch) or bad:
                errors.append(line.strip())
                continue
            for d in days:
                plan.append((d, kh, ch))
        if not plan:
            await msg.answer("❌ Tushunilmadi. Masalan:\n"
                             "<code>6-sentyabr Kirish: 8:50 Chiqish: 19:00</code>")
            return
        for d, kh, ch in plan:
            await db.set_manual_attendance(data["st_emp"], d, kh, ch)
        await state.clear()
        lines = [f"• {reports.uz_date(d)} — Kirish: {kh or '-'}  Chiqish: {ch or '-'}"
                 for d, kh, ch in plan[:40]]
        more = f"\n… va yana {len(plan) - 40} kun" if len(plan) > 40 else ""
        err = ("\n\n⚠️ Tushunilmagan qatorlar (saqlanmadi):\n" + "\n".join(errors)) if errors else ""
        await msg.answer(f"✅ {data['st_name']} — {len(plan)} kun yangilandi:\n"
                         + "\n".join(lines) + more + err, reply_markup=kb.admin_menu())
        return

    # 2) Faqat kunlar — keyin bitta vaqt hammasiga
    days, bad = _parse_days(text)
    if not days:
        await msg.answer("❌ Sana tushunilmadi. Masalan: <code>6, 7, 9 sentyabr</code> "
                         "yoki <code>6-10 sentyabr</code>")
        return
    await state.update_data(st_days=days)
    await state.set_state(SetTime.times)
    note = f"\n⚠️ Tushunilmadi (tashlab ketildi): {', '.join(bad)}" if bad else ""
    await msg.answer(f"📅 Tanlangan kunlar ({len(days)} ta): {_days_label(days)}{note}\n\n"
                     "Vaqtni kiriting (hamma tanlangan kunlarga qo'yiladi). Masalan:\n"
                     "«Kirish: 8:50 Chiqish: 19:00»\n"
                     "yoki faqat «Kirish: 8:50» yoki faqat «Chiqish: 19:00»")


@router.message(SetTime.times, F.text)
async def settime_apply(msg: Message, state: FSMContext):
    data = await state.get_data()
    kh, ch = _parse_times(_norm_time_words(msg.text))
    if not kh and not ch:
        await msg.answer("❌ Vaqt topilmadi. Masalan: Kirish: 8:50 Chiqish: 19:00")
        return
    days = data.get("st_days") or ([data["st_day"]] if data.get("st_day") else [])
    for d in days:
        await db.set_manual_attendance(data["st_emp"], d, kh, ch)
    await state.clear()
    await msg.answer(
        f"✅ {data['st_name']} — {len(days)} kun: {_days_label(days)}\n"
        f"Kirish: {kh or '-'}  Chiqish: {ch or '-'}\nVaqt yangilandi.",
        reply_markup=kb.admin_menu())


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


# ==================== Xodimlar ma'lumotini Excel'da yuklab olish ====================
@router.callback_query(F.data == "a:empexcel")
async def emp_excel(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await cb.answer("Tayyorlanmoqda...")
    try:
        path = await reports.build_employees_excel()
    except Exception as e:
        await cb.message.answer(f"❌ Fayl tayyorlashda xatolik: {e}")
        return
    await cb.message.answer_document(
        FSInputFile(path, filename=path.split("/")[-1]),
        caption="⬇️ Xodimlar ma'lumoti: username, telefon, bo'lim, grafik, ulanish holati "
                "va har bir ma'lumot talabi bo'yicha to'ldirilganlik.\n"
                "2-varaqda to'liq to'ldirmaganlar ro'yxati.")


# ==================== Topish: guruhda bor, bazada yo'q ====================
async def _show_unknown(message):
    items = await db.unknown_pending()
    if not items:
        await message.answer(
            "✅ Guruhda ko'rilgan barcha ismlar bazada bor.\n"
            "Yangi ismlarni topish uchun guruh tarixini qayta o'qing:",
            reply_markup=kb.unknown_kb([]))
        return
    import json
    hmap = {_hashlib.md5(it["name"].encode()).hexdigest()[:10]: it["name"] for it in items}
    await db.set_setting("_unkmap", json.dumps(hmap, ensure_ascii=False))
    await message.answer(
        f"🔍 Guruhda bor, lekin botda yo'q: {len(items)} ta.\n"
        "Xodim sifatida qo'shish uchun ismni bosing (username avtomatik yoziladi):",
        reply_markup=kb.unknown_kb(items))


@router.callback_query(F.data == "a:findunk")
async def find_unknown(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await _show_unknown(cb.message)
    await cb.answer()


@router.callback_query(F.data == "unk:refresh")
async def unknown_refresh(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await cb.answer("O'qilmoqda...")
    await cb.message.answer("🔄 Guruh tarixi o'qilmoqda (bir-ikki daqiqa olishi mumkin)...")
    import userbot
    count, info = await userbot.backfill(limit=5000)
    if info != "ok":
        await cb.message.answer(f"⚠️ O'qib bo'lmadi: {info}\n"
                                "(Guruhga kamida bitta qurilma xabari kelgach qayta urinib ko'ring.)")
    await _show_unknown(cb.message)


@router.callback_query(F.data.startswith("unk:"))
async def unknown_pick(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    h = cb.data.split(":", 1)[1]
    if h == "refresh":
        return  # yuqoridagi handler ishlaydi
    import json
    hmap = json.loads(await db.get_setting("_unkmap") or "{}")
    name = hmap.get(h)
    if not name:
        return await cb.answer("Ro'yxat eskirgan, qaytadan oching", show_alert=True)
    await state.clear()
    await state.update_data(username=name)
    await state.set_state(AddEmp.phone)
    await cb.message.answer(
        f"➕ Yangi xodim: {name}\nUsername avtomatik yozildi.\n\n"
        "Telefon raqamini kiriting (masalan 901234567):")
    await cb.answer()


# ==================== Filiallar ====================
@router.message(F.text == "🏬 Filiallar")
async def m_branches(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer("🏬 Filiallar boshqaruvi:", reply_markup=kb.branch_manage_kb())


@router.callback_query(F.data == "br:add")
async def br_add(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(BranchState.name)
    await cb.message.answer("Yangi filial nomini yozing (masalan: Chilonzor filiali):")
    await cb.answer()


@router.message(BranchState.name, F.text)
async def br_add_save(msg: Message, state: FSMContext):
    bid = await db.add_branch(msg.text.strip())
    await state.clear()
    if bid:
        await msg.answer(f"✅ Filial qo'shildi: {msg.text.strip()}",
                         reply_markup=kb.branch_manage_kb())
    else:
        await msg.answer("❌ Bunday filial allaqachon bor.", reply_markup=kb.branch_manage_kb())


@router.callback_query(F.data == "br:list")
async def br_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    branches = await db.list_branches()
    if not branches:
        await cb.message.answer("Hozircha filial yo'q.")
    else:
        total = sum(b["count"] for b in branches)
        await cb.message.answer(f"🏬 Filiallar (jami xodim: {total}). Tanlang:",
                                reply_markup=kb.branches_kb(branches))
    await cb.answer()


@router.callback_query(F.data.startswith("brshow:"))
async def br_show(cb: CallbackQuery):
    bid = int(cb.data.split(":")[1])
    br = await db.get_branch(bid)
    members = await db.branch_members(bid)
    lines = [f"🏬 {br['name']} — {len(members)} ta xodim\n"]
    for m in members:
        link = "🟢" if m["telegram_id"] else "🔴"
        lines.append(f"{link} {db.full_name(m)} ({m['phone']})")
    await cb.message.answer("\n".join(lines), reply_markup=kb.branch_actions_kb(bid))
    await cb.answer()


@router.callback_query(F.data.startswith("brmem:"))
async def br_members(cb: CallbackQuery):
    await br_show(cb)


@router.callback_query(F.data.startswith("brdel:"))
async def br_delete(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await db.delete_branch(int(cb.data.split(":")[1]))
    await cb.answer("O'chirildi")
    await cb.message.answer("🗑 Filial o'chirildi (xodimlar filialsiz qoldi).",
                            reply_markup=kb.branch_manage_kb())


@router.callback_query(F.data == "br:export")
async def br_export(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    text = await db.employees_export_text()
    if not text:
        await cb.message.answer("Xodim yo'q.")
        return await cb.answer()
    await cb.message.answer(
        "⬇️ Xodimlar ro'yxati.\n"
        "Har qator: <b>Username — Filial</b>\n"
        "Filial nomini yozib (yoki o'zgartirib), matnni nusxalab qaytaring — "
        "«⬆️ Filiallarni matndan yuklash» orqali.")
    for i in range(0, len(text), 3500):
        await cb.message.answer(f"<code>{text[i:i+3500]}</code>")
    await cb.answer()


@router.callback_query(F.data == "br:bulk")
async def br_bulk(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(BranchState.bulk)
    await cb.message.answer(
        "⬆️ Filiallarni matndan yuklash.\n\n"
        "Har qatorga shunday yozing:\n"
        "<code>Username — Filial nomi</code>\n\n"
        "Masalan:\n"
        "<code>Tolipova Nodiraxon — Chilonzor\nAli Valiyev — Yunusobod</code>\n\n"
        "Ajratgich sifatida —, -, : yoki | ishlatsa bo'ladi. "
        "Yangi filial nomi bo'lsa, avtomatik yaratiladi.")
    await cb.answer()


@router.message(BranchState.bulk, F.text)
async def br_bulk_apply(msg: Message, state: FSMContext):
    res = await db.bulk_assign_branches(msg.text)
    await state.clear()
    lines = [f"✅ Filial tayinlandi: {res['ok']} ta xodim"]
    if res["created"]:
        lines.append(f"🆕 Yangi filiallar: {', '.join(sorted(set(res['created'])))}")
    if res["not_found"]:
        lines.append(f"⚠️ Topilmadi ({len(res['not_found'])}): " +
                     ", ".join(res["not_found"][:15]))
    await msg.answer("\n".join(lines), reply_markup=kb.branch_manage_kb())


@router.callback_query(F.data.startswith("empbr:"))
async def emp_branch_choose(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    emp_id = int(cb.data.split(":")[1])
    branches = await db.list_branches()
    if not branches:
        return await cb.answer("Avval filial qo'shing", show_alert=True)
    await cb.message.answer("Filialni tanlang:", reply_markup=kb.emp_branch_kb(branches, emp_id))
    await cb.answer()


@router.callback_query(F.data.startswith("setbr:"))
async def emp_branch_set(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    _, emp_id, bid = cb.data.split(":")
    bid = int(bid)
    await db.set_employee_branch(int(emp_id), bid if bid else None)
    await cb.answer("Saqlandi ✅")
    await cb.message.answer("🏬 Filial yangilandi.")


# ==================== Rasm orqali dars jadval belgilash ====================
import io as _io


def _lesson_months():
    """Keyingi oy, joriy oy va oldingi 3 oy."""
    now = dt.datetime.now(TZ)
    y, m = now.year, now.month + 1
    if m == 13:
        y, m = y + 1, 1
    out = []
    for _ in range(5):
        out.append((f"{reports.UZ_MONTHS[m]} {y}", f"{y}-{m:02d}"))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


@router.callback_query(F.data == "a:fidback")
async def faceid_back(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("📷 FaceID boshqarish:", reply_markup=kb.admin_faceid_kb())
    await cb.answer()


@router.callback_query(F.data == "a:lessonimg")
async def lesson_img_menu(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.clear()
    emps = await db.oquv_employees()
    if not emps:
        await cb.message.answer(
            "❌ O'quv bo'limida xodim topilmadi.\n"
            "Avval «O'quv bo'limi» nomli bo'lim yarating va ustozlarni unga qo'shing.",
            reply_markup=kb.back_kb("a:fidback"))
        return await cb.answer()
    await cb.message.answer(
        f"🗓 Dars jadval belgilash.\nO'quv bo'limi xodimlari ({len(emps)} ta) — ustozni tanlang:",
        reply_markup=kb.lesson_emp_kb(emps))
    await cb.answer()


@router.callback_query(F.data.startswith("limg:"))
async def lesson_img_pick(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    if not emp:
        return await cb.answer("Topilmadi", show_alert=True)
    await state.clear()
    await state.update_data(li_emp=emp["id"])
    await state.set_state(LessonImg.photo)
    await cb.message.answer(
        f"👤 {db.full_name(emp)}\n\n"
        "📷 Shu ustozning oylik dars jadvali rasmini yuboring "
        "(HolliHop → Расписание → «Месяц» ko'rinishi, skrinshot).\n\n"
        "Har kungi birinchi dars vaqti olinadi, kelish vaqti = dars − 5 daqiqa.\n\n"
        "💡 Rasm o'rniga matn ham yuborsa bo'ladi — har qatorda «kun vaqt»:\n"
        "<code>3 17:00\n5 9:30\n7 17:00</code>",
        reply_markup=kb.back_kb("a:lessonimg"))
    await cb.answer()


async def _lesson_ask_month(msg, state, cells, detected):
    await state.update_data(li_cells=cells)
    await state.set_state(None)
    det = ""
    if detected:
        y, m = detected.split("-")
        det = f"\nRasmdan aniqlangan oy: ⭐ {reports.UZ_MONTHS[int(m)]} {y}"
    await msg.answer(
        f"✅ O'qildi: {len(cells)} ta dars bor katak.{det}\n\nQaysi oy uchun saqlansin?",
        reply_markup=kb.lesson_month_kb(_lesson_months(), detected))


@router.message(LessonImg.photo, F.photo | F.document)
async def lesson_img_photo(msg: Message, state: FSMContext):
    if msg.document:
        mt = (msg.document.mime_type or "").lower()
        if not mt.startswith("image/"):
            await msg.answer("❌ Rasm yuboring (jpg/png).")
            return
        file_id, media_type = msg.document.file_id, mt
    else:
        file_id, media_type = msg.photo[-1].file_id, "image/jpeg"
    wait = await msg.answer("⏳ Rasm tahlil qilinmoqda (10–40 soniya)...")
    buf = _io.BytesIO()
    await msg.bot.download(file_id, destination=buf)
    import lesson_vision
    try:
        cells, title = await lesson_vision.parse_image(buf.getvalue(), media_type)
    except Exception as e:
        await msg.answer(
            f"❌ Rasmni o'qib bo'lmadi:\n{str(e)[:300]}\n\n"
            "Qaytadan aniqroq rasm yuboring yoki jadvalni matn bilan yuboring "
            "(har qatorda «kun vaqt», masalan <code>3 17:00</code>).",
            reply_markup=kb.back_kb("a:lessonimg"))
        return
    if not cells:
        await msg.answer("❌ Rasmda dars topilmadi. Aniqroq skrinshot yuboring.",
                         reply_markup=kb.back_kb("a:lessonimg"))
        return
    await _lesson_ask_month(msg, state, cells, lesson_vision.detect_month(title))


@router.message(LessonImg.photo, F.text)
async def lesson_img_text(msg: Message, state: FSMContext):
    import lesson_vision
    cells = lesson_vision.parse_text(msg.text)
    if not cells:
        await msg.answer("❌ Tushunilmadi. Rasm yuboring yoki har qatorda «kun vaqt» yozing, "
                         "masalan <code>3 17:00</code>.")
        return
    await _lesson_ask_month(msg, state, cells, None)


@router.callback_query(F.data.startswith("limgm:"))
async def lesson_img_month(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    data = await state.get_data()
    cells, emp_id = data.get("li_cells"), data.get("li_emp")
    if not cells or not emp_id:
        return await cb.answer("Sessiya tugagan, qaytadan boshlang", show_alert=True)
    ym = cb.data.split(":", 1)[1]
    import lesson_vision
    result = lesson_vision.map_to_month(cells, ym)
    y, m = ym.split("-")
    mlabel = f"{reports.UZ_MONTHS[int(m)]} {y}"
    if not result:
        await cb.message.answer(
            f"❌ {mlabel} uchun mos kun topilmadi. Rasmdagi oy boshqa bo'lishi mumkin — "
            "boshqa oyni tanlang.", reply_markup=kb.lesson_month_kb(_lesson_months()))
        return await cb.answer()
    await db.save_manual_lessons(emp_id, ym, result)
    emp = await db.get_employee_by_id(emp_id)
    await state.clear()
    lines = [f"✅ Saqlandi: {db.full_name(emp)} — {mlabel}",
             f"📚 Dars kunlari: {len(result)} ta | kelish = dars − 5 daqiqa\n"]
    for d, mins in sorted(result.items()):
        need = mins - 5
        lines.append(f"{reports.uz_date(d)} ({reports.uz_weekday(d)[:3]}): "
                     f"dars {mins // 60:02d}:{mins % 60:02d} → kelish {need // 60:02d}:{need % 60:02d}")
    lines.append("\nShu oyda dars yo'q kunlar — dam olish (kechikish yozilmaydi).")
    text = "\n".join(lines)
    for i in range(0, len(text), 3800):
        last = i + 3800 >= len(text)
        await cb.message.answer(text[i:i + 3800],
                                reply_markup=kb.back_kb("a:lessonimg") if last else None)
    await cb.answer("Saqlandi ✅")


# ==================== Xodim so'rovi: jarima hisoblamaslik (rollar bilan) ====================
async def exreq_recipients(emp):
    """So'rov kimlarga boradi: {telegram_id: 'head'|'manager'|'admin'}.
    Oddiy xodim -> o'z bo'limi rahbari; bo'lim rahbari -> menejerlar; adminlar — doim hammasi."""
    role = await db.get_role(emp["id"])
    ids = {}
    if role == "head":
        for m in await db.role_holders("manager"):
            if m["telegram_id"] and m["id"] != emp["id"]:
                ids[m["telegram_id"]] = "manager"
    elif role != "manager" and emp.get("department_id"):
        for h in await db.role_holders("head", emp["department_id"]):
            if h["telegram_id"] and h["id"] != emp["id"]:
                ids[h["telegram_id"]] = "head"
    for aid in all_admin_ids():
        if aid != emp.get("telegram_id"):
            ids.setdefault(aid, "admin")
    return ids


async def can_decide(uid, req_emp):
    if is_admin(uid):
        return True
    if req_emp.get("telegram_id") == uid:
        return False                       # o'z so'rovini o'zi tasdiqlay olmaydi
    me = await db.get_employee_by_telegram(uid)
    if not me:
        return False
    my_role = await db.get_role(me["id"])
    req_role = await db.get_role(req_emp["id"])
    if my_role == "manager" and req_role == "head":
        return True
    if (my_role == "head" and req_role not in ("head", "manager")
            and me.get("department_id") and me["department_id"] == req_emp.get("department_id")):
        return True
    return False


async def person_name(uid):
    e = await db.get_employee_by_telegram(uid) if uid else None
    if e:
        role = await db.get_role(e["id"])
        if role:
            return f"{db.full_name(e)} ({db.ROLE_NAMES[role]})"
        return f"{db.full_name(e)} (Admin)" if is_admin(uid) else db.full_name(e)
    return "Admin"


@router.callback_query(F.data.startswith("exreq:"))
async def exreq_decide(cb: CallbackQuery):
    _, action, rid = cb.data.split(":")
    req = await db.get_exempt_request(int(rid))
    if not req:
        return await cb.answer("So'rov topilmadi", show_alert=True)
    emp = await db.get_employee_by_id(req["employee_id"])
    if not emp:
        return await cb.answer("Xodim topilmadi", show_alert=True)
    if not await can_decide(cb.from_user.id, emp):
        return await cb.answer("⛔ Sizda bu so'rovni belgilash huquqi yo'q", show_alert=True)

    fine = await reports.day_fine(emp, req["day"])   # belgilashdan oldingi jarima
    status = "approved" if action == "ok" else "rejected"
    if not await db.decide_exempt_request(req["id"], status, cb.from_user.id):
        done = await db.get_exempt_request(req["id"])
        who = await person_name(done.get("decided_by")) if done else "boshqa odam"
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await cb.answer(f"Allaqachon belgilangan: {who}", show_alert=True)

    if status == "approved":
        await db.add_exemptions([emp["id"]], req["day"], None)
    who = await person_name(cb.from_user.id)
    day_txt = reports.uz_date(req["day"])
    fine_txt = f"{reports.fmt_sum(fine)} so'm"
    if status == "approved":
        stamp = f"✅ <b>Belgilandi: jarima hisoblanmaydi</b> ({fine_txt})\n👤 Belgiladi: {who}"
        emp_msg = f"✅ {day_txt} kungi {fine_txt} jarima hisobga olinmaydi.\n👤 Belgiladi: {who}"
    else:
        stamp = f"❌ <b>Belgilandi: jarima hisoblanadi</b> ({fine_txt})\n👤 Belgiladi: {who}"
        emp_msg = f"❌ {day_txt} kungi {fine_txt} jarima hisobga olinadi.\n👤 Belgiladi: {who}"

    # So'rov borgan HAMMA odamdagi xabarni yangilaymiz: kim belgilagani ko'rinsin
    edited_here = False
    for m in await db.exreq_messages_for(req["id"]):
        try:
            await cb.bot.edit_message_text(chat_id=m["chat_id"], message_id=m["message_id"],
                                           text=(m["text"] or "") + "\n\n" + stamp, reply_markup=None)
            if m["chat_id"] == cb.message.chat.id and m["message_id"] == cb.message.message_id:
                edited_here = True
        except Exception:
            pass
    if not edited_here:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cb.message.answer(stamp)

    if emp.get("telegram_id"):
        try:
            await cb.bot.send_message(emp["telegram_id"], emp_msg)
        except Exception:
            pass
    await cb.answer("Saqlandi ✅")


# ==================== Rol berish ====================
@router.callback_query(F.data.startswith("emprole:"))
async def emp_role_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    cur = await db.get_role(emp["id"])
    await cb.message.answer(
        f"👔 {db.full_name(emp)} — hozirgi rol: {db.ROLE_NAMES.get(cur, 'yo‘q')}\n\n"
        "🧑‍💼 Bo'lim rahbari — o'z bo'limi xodimlarining jarima so'rovlarini belgilaydi.\n"
        "👔 Menejer — bo'lim rahbarlarining so'rovlarini belgilaydi.\n"
        "(Adminlarga barcha so'rovlar doim boradi.)",
        reply_markup=kb.role_kb(emp["id"]))
    await cb.answer()


@router.callback_query(F.data.startswith("setrole:"))
async def emp_role_set(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    _, eid, role = cb.data.split(":")
    emp = await db.get_employee_by_id(int(eid))
    role = None if role == "none" else role
    if role == "head" and not emp.get("department_id"):
        return await cb.answer("Avval xodimga bo'lim tayinlang", show_alert=True)
    await db.set_role(emp["id"], role)
    label = db.ROLE_NAMES.get(role, "rolsiz")
    extra = ""
    if role == "head":
        d = await db.get_department(emp["department_id"])
        extra = f" ({d['name']})" if d else ""
    await cb.message.answer(f"✅ {db.full_name(emp)}: {label}{extra}")
    if role and emp.get("telegram_id"):
        try:
            await cb.bot.send_message(emp["telegram_id"],
                                      f"👔 Sizga «{label}{extra}» roli berildi. "
                                      "Endi jarima hisoblamaslik so'rovlari sizga ham keladi.")
        except Exception:
            pass
    await cb.answer("Saqlandi ✅")


@router.callback_query(F.data == "a:roles")
async def roles_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    items = await db.all_roles()
    if not items:
        await cb.message.answer("Hozircha rol berilmagan.\nXodimlar ro'yxati → xodim → 👔 Rol berish.")
        return await cb.answer()
    lines = ["👔 <b>Rollar</b>\n"]
    for role, e in items:
        dep = ""
        if role == "head" and e.get("department_id"):
            d = await db.get_department(e["department_id"])
            dep = f" — {d['name']}" if d else ""
        mark = "🟢" if e["telegram_id"] else "🔴"
        lines.append(f"{mark} {db.ROLE_NAMES[role]}: {db.full_name(e)}{dep}")
    await cb.message.answer("\n".join(lines))
    await cb.answer()


# ==================== Kirish-chiqish Excel'dan to'ldirish ====================
@router.callback_query(F.data == "a:attxls")
async def att_xls_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(AttXls.wait_file)
    await cb.message.answer(
        "📥 Kirish-chiqish tabel faylini (.xlsx) yuboring.\n\n"
        "• Har bir varaq — bitta xodim («Xodim:» qatoridagi ism bo'yicha moslanadi).\n"
        "• <b>Bot o'zi yozgan vaqtlar ustun</b> — ular o'zgarmaydi.\n"
        "• Bot yozmagan kirish yoki chiqish bo'lsa — fayldan to'ldiriladi.\n"
        "• Faylni qayta yuklash xavfsiz: takrorlanmaydi, yangilanadi.\n"
        "• Fayldagi ism botdagidan farq qilsa (masalan «Sattarova Nilufar Muxitdin qizi» ↔ "
        "«Nilufar Sattarova») — bot o'zi moslaydi yoki sizdan so'raydi va eslab qoladi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Bog'langan ismlar", callback_data="axl")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="a:fidback")]]))
    await cb.answer()


@router.message(AttXls.wait_file, F.document)
async def att_xls_file(msg: Message, state: FSMContext):
    doc = msg.document
    if not (doc.file_name or "").lower().endswith((".xlsx", ".xlsm")):
        await msg.answer("❌ Faqat Excel (.xlsx) fayl yuboring.")
        return
    await state.clear()
    wait = await msg.answer("⏳ Fayl o'qilmoqda...")
    path = f"/tmp/att_{doc.file_unique_id}.xlsx"
    await msg.bot.download(doc, destination=path)
    import attendance_import
    try:
        sheets = attendance_import.parse_workbook(path)
    except Exception as e:
        await msg.answer(f"❌ Faylni o'qib bo'lmadi: {e}", reply_markup=kb.admin_menu())
        return
    if not sheets:
        await msg.answer("❌ Faylda «Sana / Kelish vaqti / Ketish vaqti» jadvali topilmadi.",
                         reply_markup=kb.admin_menu())
        return

    by_key = await db.employees_by_name_key()
    name_count = {}
    for sh in sheets:
        k = db._name_key(sh["name"])
        name_count[k] = name_count.get(k, 0) + 1

    matched, dup_file, dup_bot, auto = 0, [], [], []
    pending = []                      # [(excel_ism, rows, [o'xshash xodimlar])]
    cnt = {"new": 0, "updated": 0, "same": 0, "bot": 0}
    months = set()
    plan = []                         # [(sheet, emp)]
    rest = []
    for sh in sheets:
        k = db._name_key(sh["name"])
        if name_count[k] > 1:                 # faylda bir xil ismli bir nechta varaq
            dup_file.append(sh["name"]); continue
        emps = by_key.get(k, [])
        if len(emps) > 1:                     # botda bir xil ismli bir nechta xodim
            dup_bot.append(sh["name"]); continue
        if emps:
            plan.append((sh, emps[0]))
        elif sh["rows"]:
            rest.append(sh)
    # Aniq mos kelmaganlar: o'xshash ism bo'yicha (boshqa varaqqa tushmagan xodimlar orasidan)
    used = {e["id"] for _, e in plan}
    for sh in rest:
        cands = await db.similar_employees(sh["name"], exclude_ids=used)
        if len(cands) == 1:
            emp = cands[0]
            used.add(emp["id"])
            await db.add_name_alias(sh["name"], emp["id"])   # keyingi safar darhol topiladi
            auto.append((sh["name"], db.full_name(emp)))
            plan.append((sh, emp))
        else:
            pending.append((sh["name"], sh["rows"], cands))

    for sh, emp in plan:
        matched += 1
        for day, kel, ket in sh["rows"]:
            months.add(day[:7])
            res = await db.fill_day_from_excel(emp["id"], day, kel, ket)
            for v in res.values():
                if v:
                    cnt[v] += 1

    try:
        await wait.delete()
    except Exception:
        pass
    mlabel = ", ".join(f"{reports.UZ_MONTHS[int(m[5:])]} {m[:4]}" for m in sorted(months)) or "—"
    lines = [
        "✅ <b>Tabel yuklandi</b>",
        f"🗓 Davr: {mlabel}",
        f"👥 Varaqlar: {len(sheets)} | moslandi: {matched}",
        f"➕ Fayldan yangi to'ldirildi: {cnt['new']} ta vaqt",
        f"✏️ Avvalgi fayl qiymati yangilandi: {cnt['updated']}",
        f"🤖 Bot yozgani saqlandi (o'zgartirilmadi): {cnt['bot']}",
        f"= O'zgarishsiz (avval yuklangan): {cnt['same']}",
    ]
    if auto:
        lines.append(f"\n🔗 Ism farqli, o'zi moslandi ({len(auto)}):")
        lines += [f"   • {a} → <b>{b}</b>" for a, b in auto[:40]]
        lines.append("   (Xato bo'lsa: 📥 Kirish-chiqish yuklash → 🔗 Bog'langan ismlar)")
    if pending:
        lines.append(f"\n❓ Botdagi xodimga moslanmadi ({len(pending)}) — pastda tanlang 👇")
    if dup_file:
        lines.append(f"\n⚠️ Faylda bir xil ismli varaqlar — o'tkazib yuborildi: " + ", ".join(sorted(set(dup_file))))
    if dup_bot:
        lines.append(f"\n⚠️ Botda bir xil ismli xodimlar — o'tkazib yuborildi: " + ", ".join(dup_bot))
    text = "\n".join(lines)
    for i in range(0, len(text), 3900):
        await msg.answer(text[i:i + 3900],
                         reply_markup=kb.admin_menu() if i + 3900 >= len(text) else None)
    # Moslanmagan ismlar: admin botdagi xodimni tanlaydi
    _XLS_PENDING[msg.from_user.id] = pending
    for idx, (name, rows, cands) in enumerate(pending[:30]):
        await msg.answer(_bind_text(name, rows, cands), reply_markup=_bind_kb(idx, cands))
    if len(pending) > 30:
        await msg.answer(f"… yana {len(pending) - 30} ta ism. Bularni tanlagach, faylni qayta yuklang.")


# --- Excel ismini botdagi xodimga bog'lash ---
_XLS_PENDING = {}     # admin_id -> [(excel_ism, rows, cands)]


def _bind_text(name, rows, cands):
    hint = "O'xshashlari 👇" if cands else "O'xshash ism topilmadi — «🔍 Qidirish» bilan toping."
    return (f"📄 Fayldagi ism: <b>{name}</b> ({len(rows)} kun)\n"
            f"Botdagi qaysi xodim? {hint}")


def _bind_kb(idx, cands):
    rows = [[InlineKeyboardButton(text=f"👤 {db.full_name(e)}"[:60], callback_data=f"axm:{idx}:{e['id']}")]
            for e in cands[:8]]
    rows.append([InlineKeyboardButton(text="🔍 Qidirish", callback_data=f"axs:{idx}"),
                 InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data=f"axk:{idx}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("axs:"))
async def att_bind_search_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    idx = int(cb.data.split(":")[1])
    items = _XLS_PENDING.get(cb.from_user.id) or []
    if idx >= len(items):
        return await cb.answer("Faylni qayta yuklang", show_alert=True)
    await state.set_state(AttXls.bind_search)
    await state.update_data(ax_idx=idx)
    await cb.message.answer(f"🔍 «{items[idx][0]}» uchun botdagi xodim ismini yozing (kirill/lotin):")
    await cb.answer()


@router.message(AttXls.bind_search, F.text)
async def att_bind_search(msg: Message, state: FSMContext):
    idx = (await state.get_data()).get("ax_idx", 0)
    found = await db.search_employees(msg.text, linked_only=False)
    if not found:
        return await msg.answer("Topilmadi. Qaytadan yozing:")
    await state.set_state(None)
    rows = [[InlineKeyboardButton(text=f"👤 {db.full_name(e)}"[:60], callback_data=f"axm:{idx}:{e['id']}")]
            for e in found[:15]]
    await msg.answer("Xodimni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("axm:"))
async def att_bind_pick(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    _, idx, emp_id = cb.data.split(":")
    items = _XLS_PENDING.get(cb.from_user.id) or []
    idx = int(idx)
    if idx >= len(items):
        return await cb.answer("Faylni qayta yuklang", show_alert=True)
    name, rows, _ = items[idx]
    emp = await db.get_employee_by_id(int(emp_id))
    if not emp:
        return await cb.answer("Xodim topilmadi", show_alert=True)
    await db.add_name_alias(name, emp["id"])
    cnt = {"new": 0, "updated": 0, "same": 0, "bot": 0}
    for day, kel, ket in rows:
        res = await db.fill_day_from_excel(emp["id"], day, kel, ket)
        for v in res.values():
            if v:
                cnt[v] += 1
    text = (f"✅ «{name}» → <b>{db.full_name(emp)}</b> bog'landi va eslab qolindi.\n"
            f"➕ Yangi: {cnt['new']}  ✏️ Yangilandi: {cnt['updated']}  "
            f"🤖 Bot yozgani saqlandi: {cnt['bot']}  = O'zgarishsiz: {cnt['same']}")
    try:
        await cb.message.edit_text(text)
    except Exception:
        await cb.message.answer(text)
    await cb.answer("Bog'landi ✅")


@router.callback_query(F.data.startswith("axk:"))
async def att_bind_skip(cb: CallbackQuery):
    try:
        await cb.message.edit_text(cb.message.html_text + "\n\n⏭ <i>O'tkazib yuborildi.</i>")
    except Exception:
        pass
    await cb.answer()


@router.callback_query(F.data == "axl")
async def att_alias_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    items = await db.list_name_aliases()
    if not items:
        await cb.message.answer("🔗 Hali bog'langan Excel ismlari yo'q.")
        return await cb.answer()
    lines = ["🔗 <b>Excel ism → botdagi xodim</b>", "Noto'g'ri bog'langanini ❌ bilan o'chiring "
             "(keyingi yuklashda bot qaytadan so'raydi):", ""]
    rows = []
    for i, (k, alias, emp) in enumerate(items[:60], 1):
        lines.append(f"{i}. {alias} → <b>{db.full_name(emp)}</b>")
        rows.append([InlineKeyboardButton(text=f"❌ {i}. {alias}"[:60], callback_data=f"axd:{_hashlib.md5(k.encode()).hexdigest()[:12]}")])
    await cb.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data.startswith("axd:"))
async def att_alias_delete(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    key = cb.data[4:]
    items = await db.list_name_aliases()
    full = next((k for k, _, _ in items if _hashlib.md5(k.encode()).hexdigest()[:12] == key), None)
    if full:
        await db.remove_name_alias(full)
    await cb.answer("O'chirildi ✅" if full else "Topilmadi")
    items = await db.list_name_aliases()
    rows = [[InlineKeyboardButton(text=f"❌ {i}. {alias}"[:60], callback_data=f"axd:{_hashlib.md5(k.encode()).hexdigest()[:12]}")]
            for i, (k, alias, emp) in enumerate(items[:60], 1)]
    try:
        await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception:
        pass
