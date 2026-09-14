"""A: Ma'lumot to'plash — admin talab qo'shadi/o'chiradi, xodim to'ldiradi."""
import datetime as dt
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import db
import keyboards as kb
from config import TZ

router = Router()


def is_admin(uid):
    import admin_handlers
    return admin_handlers.is_admin(uid)


class NewReq(StatesGroup):
    title = State()
    dtype = State()
    target = State()
    deadline = State()
    mandatory = State()


class FillReq(StatesGroup):
    wait = State()


# ---------- ADMIN: talab qo'shish ----------
@router.message(F.text == "📋 Ma'lumot talablari")
async def dr_menu(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer("📋 Ma'lumot talablari:", reply_markup=kb.datareq_menu_kb())


@router.callback_query(F.data == "dr:add")
async def dr_add(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(NewReq.title)
    await state.update_data(_dr={})
    await cb.message.answer("Talab nomini yozing (masalan: Pasport nusxasi):")
    await cb.answer()


@router.message(NewReq.title, F.text)
async def dr_title(msg: Message, state: FSMContext):
    await state.update_data(title=msg.text.strip())
    await state.set_state(None)  # keyingi qadamlar callback (holatga bog'liq emas)
    await msg.answer("Qanday ma'lumot talab qilinadi?", reply_markup=kb.dtype_kb())


@router.callback_query(F.data.startswith("drtype:"))
async def dr_dtype(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.update_data(dtype=cb.data.split(":")[1])
    deps = await db.list_departments()
    await cb.message.answer("Kimlardan talab qilinsin?", reply_markup=kb.dr_target_kb(deps))
    await cb.answer()


@router.callback_query(F.data.startswith("drtar:"))
async def dr_target(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    parts = cb.data.split(":")
    dep_id = None if parts[1] == "all" else int(parts[2])
    await state.update_data(dep_id=dep_id)
    await state.set_state(NewReq.deadline)
    await cb.message.answer("Muddat (sana) kiriting: YYYY-MM-DD.\n"
                            "Muddat kerak bo'lmasa - (chiziqcha) yuboring:")
    await cb.answer()


@router.message(NewReq.deadline, F.text)
async def dr_deadline(msg: Message, state: FSMContext):
    val = msg.text.strip()
    deadline = None
    if val != "-":
        try:
            deadline = dt.datetime.strptime(val, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            await msg.answer("❌ Noto'g'ri format. YYYY-MM-DD yoki - yuboring.")
            return
    await state.update_data(deadline=deadline)
    await state.set_state(None)
    await msg.answer("Bu talab majburiymi yoki ixtiyoriy?", reply_markup=kb.dr_mandatory_kb())


@router.callback_query(F.data.startswith("drman:"))
async def dr_mandatory(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    data = await state.get_data()
    if "title" not in data or "dtype" not in data:
        await cb.answer("Sessiya tugagan, qaytadan boshlang", show_alert=True)
        await state.clear()
        return
    mandatory = cb.data.split(":")[1] == "1"
    req_id = await db.add_data_request(
        data["title"], data["dtype"], data.get("dep_id"), data.get("deadline"), mandatory)
    await state.clear()

    req = await db.get_data_request(req_id)
    eligible = await db.eligible_linked_for_request(req)
    dl = f"\n📅 Muddat: {req['deadline']}" if req["deadline"] else ""
    mm = "🔴 Majburiy" if mandatory else "🟢 Ixtiyoriy"
    tmap = {"text": "matn", "photo": "rasm", "file": "fayl"}
    note = (f"📋 Yangi ma'lumot talabi: {req['title']}\n"
            f"Turi: {tmap.get(req['dtype'])}\n{mm}{dl}\n\n"
            f"To'ldirish uchun «📋 To'ldirish» tugmasini bosing.")
    sent = 0
    for e in eligible:
        try:
            await cb.bot.send_message(e["telegram_id"], note, reply_markup=kb.pending_reqs_kb([{
                "id": req["id"], "title": req["title"], "mandatory": req["mandatory"]}]))
            sent += 1
        except Exception:
            pass
    await cb.message.answer(
        f"✅ Talab qo'shildi va {sent} ta xodimga yuborildi.", reply_markup=kb.admin_menu())
    await cb.answer()


# ---------- ADMIN: talablar ro'yxati ----------
@router.callback_query(F.data == "dr:list")
async def dr_list(cb: CallbackQuery):
    reqs = await db.list_data_requests()
    if not reqs:
        await cb.message.answer("Hozircha talab yo'q.")
    else:
        await cb.message.answer("📋 Talablar:", reply_markup=kb.dr_list_kb(reqs))
    await cb.answer()


@router.callback_query(F.data.startswith("drshow:"))
async def dr_show(cb: CallbackQuery):
    req = await db.get_data_request(int(cb.data.split(":")[1]))
    if not req:
        return await cb.answer("Topilmadi", show_alert=True)
    dep = "Hammaga" if not req["dep_id"] else (await db.get_department(req["dep_id"]))["name"]
    dl = req["deadline"] or "yo'q"
    mm = "Majburiy" if req["mandatory"] else "Ixtiyoriy"
    tmap = {"text": "matn", "photo": "rasm", "file": "fayl"}
    await cb.message.answer(
        f"📋 {req['title']}\nTuri: {tmap.get(req['dtype'])}\nKim: {dep}\n"
        f"Muddat: {dl}\n{mm}", reply_markup=kb.dr_actions_kb(req["id"]))
    await cb.answer()


@router.callback_query(F.data.startswith("drsubs:"))
async def dr_subs(cb: CallbackQuery):
    req_id = int(cb.data.split(":")[1])
    subs = await db.request_submissions(req_id)
    if not subs:
        await cb.message.answer("Hali hech kim topshirmagan.")
        await cb.answer()
        return
    await cb.message.answer(f"👁 Topshirganlar ({len(subs)}):")
    for s in subs:
        who = f"👤 {(str(s['first_name'] or '')+' '+str(s['last_name'] or '')).strip()} ({s['phone']})"
        if s["kind"] == "text":
            await cb.bot.send_message(cb.from_user.id, f"{who}\n✍️ {s['content']}")
        elif s["kind"] == "photo":
            await cb.bot.send_photo(cb.from_user.id, s["content"], caption=who)
        elif s["kind"] == "file":
            await cb.bot.send_document(cb.from_user.id, s["content"], caption=who)
    await cb.answer()


@router.callback_query(F.data.startswith("drdel:"))
async def dr_del(cb: CallbackQuery):
    await db.delete_data_request(int(cb.data.split(":")[1]))
    await cb.answer("O'chirildi")
    await cb.message.answer("🗑 Talab o'chirildi.", reply_markup=kb.admin_menu())


# ---------- XODIM: to'ldirish ----------
@router.message(F.text == "📋 To'ldirish")
async def fill_menu(msg: Message):
    emp = await db.get_employee_by_telegram(msg.from_user.id)
    if not emp:
        await msg.answer("Avval /start bosing.")
        return
    reqs = await db.pending_requests_for(emp)
    if not reqs:
        await msg.answer("✅ Hozircha to'ldirish kerak bo'lgan ma'lumot yo'q.")
        return
    await msg.answer("📋 To'ldirilishi kerak (🔴 majburiy, 🟢 ixtiyoriy):",
                     reply_markup=kb.pending_reqs_kb(reqs))


@router.callback_query(F.data.startswith("fillreq:"))
async def fill_start(cb: CallbackQuery, state: FSMContext):
    req = await db.get_data_request(int(cb.data.split(":")[1]))
    if not req:
        return await cb.answer("Topilmadi", show_alert=True)
    await state.set_state(FillReq.wait)
    await state.update_data(req_id=req["id"], dtype=req["dtype"])
    prompts = {"text": "matn yozing", "photo": "rasm yuboring", "file": "faylni yuboring"}
    await cb.message.answer(f"«{req['title']}» uchun {prompts.get(req['dtype'])}:")
    await cb.answer()


@router.message(FillReq.wait)
async def fill_receive(msg: Message, state: FSMContext):
    data = await state.get_data()
    emp = await db.get_employee_by_telegram(msg.from_user.id)
    dtype = data["dtype"]
    content = kind = None
    if dtype == "text" and msg.text:
        content, kind = msg.text, "text"
    elif dtype == "photo" and msg.photo:
        content, kind = msg.photo[-1].file_id, "photo"
    elif dtype == "file" and msg.document:
        content, kind = msg.document.file_id, "file"
    else:
        need = {"text": "matn", "photo": "rasm", "file": "fayl"}
        await msg.answer(f"❌ Iltimos, {need.get(dtype)} yuboring.")
        return
    await db.add_submission(data["req_id"], emp["id"], content, kind)
    await state.clear()
    await msg.answer("✅ Qabul qilindi. Rahmat!", reply_markup=kb.user_menu())
