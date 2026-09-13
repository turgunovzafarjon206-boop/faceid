"""B: So'rovnoma — admin yaratadi, xodim javob beradi, admin statistika ko'radi."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import db
import keyboards as kb

router = Router()


def is_admin(uid):
    import admin_handlers
    return admin_handlers.is_admin(uid)


class NewSurvey(StatesGroup):
    title = State()
    target = State()
    qtext = State()
    options = State()


# ==================== ADMIN: yaratish ====================
@router.message(F.text == "📊 So'rovnoma")
async def sv_menu(msg: Message):
    if is_admin(msg.from_user.id):
        await msg.answer("📊 So'rovnomalar:", reply_markup=kb.survey_menu_kb())


@router.callback_query(F.data == "sv:add")
async def sv_add(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(NewSurvey.title)
    await cb.message.answer("So'rovnoma nomini yozing (masalan: Ish sharoiti):")
    await cb.answer()


@router.message(NewSurvey.title, F.text)
async def sv_title(msg: Message, state: FSMContext):
    await state.update_data(title=msg.text.strip())
    await state.set_state(None)
    deps = await db.list_departments()
    await msg.answer("Kimlarga yuborilsin?", reply_markup=kb.sv_target_kb(deps))


@router.callback_query(F.data.startswith("svtar:"))
async def sv_target(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    data = await state.get_data()
    if "title" not in data:
        await cb.answer("Sessiya tugagan, qaytadan boshlang", show_alert=True)
        return
    parts = cb.data.split(":")
    dep_id = None if parts[1] == "all" else int(parts[2])
    sid = await db.create_survey(data["title"], dep_id)
    await state.update_data(survey_id=sid, qcount=0)
    await state.set_state(NewSurvey.qtext)
    await cb.message.answer(
        "Endi savollarni qo'shamiz.\n\n1-savol matnini yozing.\n"
        "💡 Savolga rasm qo'shmoqchi bo'lsangiz — rasmni izoh (caption) sifatida savol matni bilan yuboring.")
    await cb.answer()


@router.message(NewSurvey.qtext)
async def sv_qtext(msg: Message, state: FSMContext):
    qtext = None
    image = None
    if msg.photo:
        image = msg.photo[-1].file_id
        qtext = (msg.caption or "").strip()
    elif msg.text:
        qtext = msg.text.strip()
    if not qtext:
        await msg.answer("❌ Savol matnini yozing (rasm bo'lsa, izoh sifatida).")
        return
    await state.update_data(cur_q=qtext, cur_img=image)
    await state.set_state(NewSurvey.options)
    await msg.answer("Javob variantlarini yuboring — har birini yangi qatordan.\n"
                     "Masalan:\nHa\nYo'q\nQisman")


@router.message(NewSurvey.options, F.text)
async def sv_options(msg: Message, state: FSMContext):
    opts = [x.strip() for x in msg.text.split("\n") if x.strip()]
    if len(opts) < 2:
        await msg.answer("❌ Kamida 2 ta variant kerak. Har birini yangi qatordan yozing.")
        return
    data = await state.get_data()
    ord_q = data.get("qcount", 0)
    qid = await db.add_question(data["survey_id"], data["cur_q"], data.get("cur_img"), ord_q)
    for i, o in enumerate(opts):
        await db.add_option(qid, o, i)
    await state.update_data(qcount=ord_q + 1)
    await msg.answer(f"✅ {ord_q + 1}-savol saqlandi. Yana savol qo'shasizmi?",
                     reply_markup=kb.sv_addq_kb())


@router.callback_query(F.data == "svq:more")
async def sv_more(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    n = data.get("qcount", 0) + 1
    await state.set_state(NewSurvey.qtext)
    await cb.message.answer(f"{n}-savol matnini yozing (rasm bo'lsa — izoh sifatida):")
    await cb.answer()


@router.callback_query(F.data == "svq:done")
async def sv_done(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sid = data.get("survey_id")
    await state.clear()
    survey = await db.get_survey(sid)
    qs = await db.survey_questions(sid)
    if not qs:
        await db.delete_survey(sid)
        await cb.message.answer("❌ Savol qo'shilmadi, so'rovnoma bekor qilindi.",
                                reply_markup=kb.admin_menu())
        await cb.answer()
        return
    # tegishli xodimlarga yuboramiz
    eligible = await db.eligible_linked_for_survey(survey)
    intro = await db.get_template("tpl_survey", db.DEFAULT_TPL_SURVEY)
    sent = 0
    for e in eligible:
        try:
            await cb.bot.send_message(
                e["telegram_id"],
                f"{intro}\n\n📊 {survey['title']}",
                reply_markup=kb.pending_surveys_kb([{"id": sid, "title": survey["title"]}]))
            sent += 1
        except Exception:
            pass
    await cb.message.answer(
        f"✅ So'rovnoma tayyor ({len(qs)} savol) va {sent} ta xodimga yuborildi.",
        reply_markup=kb.admin_menu())
    await cb.answer()


# ==================== ADMIN: ro'yxat va statistika ====================
@router.callback_query(F.data == "sv:list")
async def sv_list(cb: CallbackQuery):
    surveys = await db.list_surveys()
    if not surveys:
        await cb.message.answer("Hozircha so'rovnoma yo'q.")
    else:
        await cb.message.answer("📋 So'rovnomalar:", reply_markup=kb.sv_list_kb(surveys))
    await cb.answer()


@router.callback_query(F.data.startswith("svshow:"))
async def sv_show(cb: CallbackQuery):
    sid = int(cb.data.split(":")[1])
    s = await db.get_survey(sid)
    dep = "Hammaga" if not s["dep_id"] else (await db.get_department(s["dep_id"]))["name"]
    qs = await db.survey_questions(sid)
    await cb.message.answer(
        f"📊 {s['title']}\nKim: {dep}\nSavollar: {len(qs)}\n"
        f"Holat: {'faol' if s['active'] else 'to‘xtatilgan'}",
        reply_markup=kb.sv_actions_kb(sid, s["active"]))
    await cb.answer()


@router.callback_query(F.data.startswith("svstat:"))
async def sv_stat(cb: CallbackQuery):
    sid = int(cb.data.split(":")[1])
    stats = await db.survey_stats(sid)
    lines = ["📊 Statistika (raqamli):\n"]
    for i, q in enumerate(stats, 1):
        lines.append(f"\n{i}. {q['qtext']}  (jami {q['total']})")
        for o in q["options"]:
            pct = round(o["count"] / q["total"] * 100) if q["total"] else 0
            bar = "█" * (pct // 10)
            lines.append(f"   {o['otext']}: {o['count']} ({pct}%) {bar}")
    await cb.message.answer("\n".join(lines))
    await cb.answer()


@router.callback_query(F.data.startswith("svdet:"))
async def sv_detail(cb: CallbackQuery):
    sid = int(cb.data.split(":")[1])
    det = await db.survey_detailed(sid)
    if not det:
        await cb.message.answer("Hali javoblar yo'q.")
        await cb.answer()
        return
    lines = ["👥 Kim nima javob berdi:\n"]
    for name, answers in det.items():
        lines.append(f"\n👤 {name}:")
        for qt, ot in answers:
            lines.append(f"   • {qt} → {ot}")
    text = "\n".join(lines)
    # uzun bo'lsa bo'laklarga bo'lamiz
    for i in range(0, len(text), 3500):
        await cb.message.answer(text[i:i+3500])
    await cb.answer()


@router.callback_query(F.data.startswith("svstop:"))
async def sv_stop(cb: CallbackQuery):
    sid = int(cb.data.split(":")[1])
    await db.set_setting(f"_sv_noop", "")  # no-op guard
    async with __import__("aiosqlite").connect(db.DB_PATH) as d:
        await d.execute("UPDATE surveys SET active=0 WHERE id=?", (sid,))
        await d.commit()
    await cb.answer("To'xtatildi")
    await cb.message.answer("⏹ So'rovnoma to'xtatildi (endi yangi javob qabul qilinmaydi).")


@router.callback_query(F.data.startswith("svdel:"))
async def sv_del(cb: CallbackQuery):
    await db.delete_survey(int(cb.data.split(":")[1]))
    await cb.answer("O'chirildi")
    await cb.message.answer("🗑 So'rovnoma o'chirildi.", reply_markup=kb.admin_menu())


# ==================== XODIM: javob berish ====================
@router.message(F.text == "📊 So'rovnomalar")
async def sv_pending(msg: Message):
    emp = await db.get_employee_by_telegram(msg.from_user.id)
    if not emp:
        await msg.answer("Avval /start bosing.")
        return
    surveys = await db.pending_surveys_for(emp)
    if not surveys:
        await msg.answer("✅ Hozircha to'ldirilmagan so'rovnoma yo'q.")
        return
    await msg.answer("📊 To'ldirilishi kerak:", reply_markup=kb.pending_surveys_kb(surveys))


async def _send_question(bot, chat_id, survey_id, q):
    q = dict(q)
    q["_options"] = await db.question_options(q["id"])
    markup = kb.survey_options_kb(survey_id, q)
    if q.get("image_file_id"):
        await bot.send_photo(chat_id, q["image_file_id"], caption=q["qtext"], reply_markup=markup)
    else:
        await bot.send_message(chat_id, q["qtext"], reply_markup=markup)


@router.callback_query(F.data.startswith("svstart:"))
async def sv_start(cb: CallbackQuery):
    sid = int(cb.data.split(":")[1])
    emp = await db.get_employee_by_telegram(cb.from_user.id)
    if not emp:
        return await cb.answer("Avval /start", show_alert=True)
    if await db.has_completed_survey(emp["id"], sid):
        await cb.message.answer("✅ Siz bu so'rovnomani allaqachon to'ldirgansiz.")
        return await cb.answer()
    qs = await db.survey_questions(sid)
    await _send_question(cb.bot, cb.from_user.id, sid, qs[0])
    await cb.answer()


@router.callback_query(F.data.startswith("svans:"))
async def sv_answer(cb: CallbackQuery):
    _, sid, qid, oid = cb.data.split(":")
    sid, qid, oid = int(sid), int(qid), int(oid)
    emp = await db.get_employee_by_telegram(cb.from_user.id)
    if not emp:
        return await cb.answer("Avval /start", show_alert=True)
    survey = await db.get_survey(sid)
    if not survey or not survey["active"]:
        await cb.answer("So'rovnoma yopilgan", show_alert=True)
        return
    await db.record_answer(sid, qid, oid, emp["id"])
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    # keyingi savol
    qs = await db.survey_questions(sid)
    idx = next((i for i, q in enumerate(qs) if q["id"] == qid), -1)
    if idx != -1 and idx + 1 < len(qs):
        await _send_question(cb.bot, cb.from_user.id, sid, qs[idx + 1])
    else:
        await cb.message.answer("✅ Rahmat! So'rovnoma yakunlandi.")
    await cb.answer("Qabul qilindi")
