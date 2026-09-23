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
    mm = "🔴 Majburiy" if mandatory else "🟢 Ixtiyoriy"
    dl = f"\n📅 Muddat: {data.get('deadline')}" if data.get("deadline") else ""
    await cb.message.answer(
        f"✅ Talab qo'shildi: {data['title']}\n{mm}{dl}\n\n"
        "Xodimlarga hozir xabar yuborilmadi. Ular «🔔 Eslatma» orqali "
        "ogohlantirilganda to'ldirish so'raladi.", reply_markup=kb.admin_menu())
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


# ==================== ADMIN: Xodim ma'lumoti ====================
import io, zipfile, os
from aiogram.types import InputMediaPhoto, InputMediaDocument


class EmpData(StatesGroup):
    search = State()


def _nm(e):
    return (str(e['first_name'] or '') + ' ' + str(e['last_name'] or '')).strip()


@router.callback_query(F.data == "a:empdata")
async def empdata_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(EmpData.search)
    await cb.message.answer("🗂 Xodim ma'lumoti.\nXodim ismini (username) qidiring:")
    await cb.answer()


@router.callback_query(F.data == "ed:search")
async def empdata_search_again(cb: CallbackQuery, state: FSMContext):
    await state.set_state(EmpData.search)
    await cb.message.answer("Xodim ismini yozing:")
    await cb.answer()


@router.message(EmpData.search, F.text)
async def empdata_search(msg: Message, state: FSMContext):
    found = await db.search_employees(msg.text.strip(), linked_only=False)
    await state.set_state(None)
    if not found:
        await msg.answer("Topilmadi. Qaytadan qidiring:")
        return
    await msg.answer("Xodimni tanlang:", reply_markup=kb.empdata_select_kb(found))


@router.callback_query(F.data.startswith("edshow:"))
async def empdata_show(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    subs = await db.employee_submissions(emp["id"])
    dep = "yo'q"
    if emp.get("department_id"):
        d = await db.get_department(emp["department_id"])
        dep = d["name"] if d else "yo'q"
    header = (f"🗂 <b>{_nm(emp)}</b>\n📞 {emp['phone']}\n🏢 Bo'lim: {dep}\n"
              f"🕐 Grafik: {emp['work_start']}-{emp['work_end']}\n"
              f"{'━'*20}\n")
    if not subs:
        await cb.message.answer(header + "\nHali hech qanday ma'lumot topshirmagan.",
                                reply_markup=kb.empdata_actions_kb(emp["id"]))
        return await cb.answer()

    lines = [header]
    for i, s in enumerate(subs, 1):
        if s["kind"] == "text":
            lines.append(f"{i}. <b>{s['title']}</b>:\n   {s['content']}")
        elif s["kind"] == "photo":
            lines.append(f"{i}. <b>{s['title']}</b>: 🖼 rasm (pastda)")
        else:
            lines.append(f"{i}. <b>{s['title']}</b>: 📎 fayl (pastda)")
    await cb.message.answer("\n\n".join(lines), reply_markup=kb.empdata_actions_kb(emp["id"]))

    # rasmlar va fayllarni alohida albom qilib yuboramiz
    photos = [InputMediaPhoto(media=s["content"], caption=s["title"])
              for s in subs if s["kind"] == "photo"]
    docs = [InputMediaDocument(media=s["content"], caption=s["title"])
            for s in subs if s["kind"] == "file"]
    for i in range(0, len(photos), 10):
        try:
            await cb.bot.send_media_group(cb.from_user.id, photos[i:i+10])
        except Exception:
            pass
    for i in range(0, len(docs), 10):
        try:
            await cb.bot.send_media_group(cb.from_user.id, docs[i:i+10])
        except Exception:
            pass
    await cb.answer()


@router.callback_query(F.data.startswith("eddl:"))
async def empdata_download(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    emp = await db.get_employee_by_id(int(cb.data.split(":")[1]))
    subs = await db.employee_submissions(emp["id"])
    await cb.answer("Tayyorlanmoqda...")

    summary = [f"Xodim: {_nm(emp)}", f"Telefon: {emp['phone']}",
               f"Grafik: {emp['work_start']}-{emp['work_end']}", "=" * 30, ""]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        idx = 0
        for s in subs:
            idx += 1
            safe_title = "".join(c for c in s["title"] if c.isalnum() or c in " _-").strip()
            if s["kind"] == "text":
                summary.append(f"{idx}. {s['title']}: {s['content']}")
            else:
                summary.append(f"{idx}. {s['title']}: (fayl ilova qilindi)")
                try:
                    f = await cb.bot.get_file(s["content"])
                    bio = io.BytesIO()
                    await cb.bot.download_file(f.file_path, destination=bio)
                    ext = os.path.splitext(f.file_path)[1] or (".jpg" if s["kind"] == "photo" else "")
                    zf.writestr(f"{idx:02d}_{safe_title}{ext}", bio.getvalue())
                except Exception as e:
                    summary.append(f"    (faylni olishda xatolik: {e})")
        zf.writestr("00_MALUMOTLAR.txt", "\n".join(summary))

    buf.seek(0)
    fname = "".join(c for c in _nm(emp) if c.isalnum() or c in " _-").strip().replace(" ", "_")
    path = f"/tmp/{fname or 'xodim'}_malumotlari.zip"
    with open(path, "wb") as fp:
        fp.write(buf.getvalue())
    await cb.message.answer_document(FSInputFile(path, filename=f"{fname or 'xodim'}_malumotlari.zip"),
                                     caption=f"⬇️ {_nm(emp)} — barcha ma'lumotlari (bitta fayl)")


@router.callback_query(F.data == "ed:incomplete")
async def empdata_incomplete(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    rep = await db.incomplete_report()
    if not rep:
        await cb.message.answer("✅ Hamma xodim barcha ma'lumotlarni to'ldirgan.")
        return await cb.answer()
    lines = [f"📋 To'liq to'ldirmaganlar ({len(rep)} ta):\n"]
    for r in rep:
        emp = r["emp"]
        lines.append(f"👤 {_nm(emp)} ({emp['phone']})\n   Yetishmaydi: {', '.join(r['missing'])}")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await cb.message.answer(text[i:i+3500])
    await cb.answer()
