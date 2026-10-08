"""
Botni ishga tushirish nuqtasi.
Ishga tushirish:  python main.py
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ErrorEvent

import db
from config import BOT_TOKEN
import user_handlers
import admin_handlers
import forms_handlers
import survey_handlers
import group_handlers
from scheduler import faceid_poller, daily_report_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("main")

# Menyu tugmalari — bosilganda FSM holati tozalanadi (tiqilib qolmaslik uchun)
MENU_BUTTONS = {
    "📷 FaceID boshqarish", "👥 Ma'lumotlar", "🏢 Bo'limlar", "✉️ Xabar",
    "🔔 Eslatma", "📋 Ma'lumot talablari", "📊 So'rovnoma", "🔙 Oddiy menyu",
    "📷 FaceID", "👤 Mening ma'lumotlarim", "✉️ HR bo'limiga xabar",
    "📝 Jarima hisoblamaslik so'rash", "🏬 Filiallar",
}


class ResetStateMiddleware(BaseMiddleware):
    """Menyu tugmasi yoki komanda bosilsa, yarim qolgan holatni tozalaydi."""
    async def __call__(self, handler, event, data):
        text = getattr(event, "text", None)
        if text and (text in MENU_BUTTONS or text.startswith("/")):
            state = data.get("state")
            if state is not None:
                try:
                    await state.clear()
                except Exception:
                    pass
        return await handler(event, data)


def _menu_signature():
    """Menyu tugmalari matnlaridan imzo — tugmalar o'zgarsa, imzo ham o'zgaradi."""
    import hashlib
    import keyboards as kb
    texts = []
    for mk in (kb.user_menu(), kb.admin_menu()):
        for row in mk.keyboard:
            texts.append("|".join(b.text for b in row))
    return hashlib.md5("\n".join(texts).encode()).hexdigest()[:12]


async def refresh_menus(bot, note="🔄 Bot yangilandi — menyu yangilandi, yangi tugmalar pastda."):
    """Barcha ulangan xodim va adminlarga yangi menyuni yuboradi. Qaytaradi: (yuborildi, xato)."""
    import keyboards as kb
    admins = set(admin_handlers.all_admin_ids())
    targets = {}
    for e in await db.list_employees(active_only=True):
        if e.get("telegram_id"):
            targets[int(e["telegram_id"])] = "user"
    for a in admins:
        targets[int(a)] = "admin"
    ok = fail = 0
    for chat_id, kind in targets.items():
        markup = kb.admin_menu() if kind == "admin" else kb.user_menu()
        try:
            await bot.send_message(chat_id, note, reply_markup=markup, disable_notification=True)
            ok += 1
        except Exception as ex:
            fail += 1
            log.info("Menyu yuborilmadi %s: %s", chat_id, ex)
        await asyncio.sleep(0.07)   # Telegram limiti (~15 xabar/soniya)
    return ok, fail


async def auto_refresh_menus(bot):
    """Deploy'dan keyin menyu tugmalari o'zgargan bo'lsa — hammaga avtomatik yangilaydi."""
    try:
        await asyncio.sleep(5)
        sig = _menu_signature()
        old = await db.get_setting("menu_signature")
        if old == sig:
            log.info("Menyu o'zgarmagan — avtomatik yangilash shart emas.")
            return
        ok, fail = await refresh_menus(bot)
        await db.set_setting("menu_signature", sig)
        log.info("✅ Menyu hammaga yangilandi: %s ta yuborildi, %s ta xato", ok, fail)
    except Exception as e:
        log.warning("Menyuni avtomatik yangilashda xato: %s", e)


async def main():
    await db.init_db()
    import os
    from config import DB_PATH
    vol = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
    log.info("DB manzili: %s (fayl mavjud: %s)",
             os.path.abspath(DB_PATH), os.path.exists(DB_PATH))
    if vol and DB_PATH.startswith(vol):
        log.info("✅ Baza doimiy diskda (Volume: %s) — ma'lumot deploy'da o'chmaydi.", vol)
    else:
        log.warning("⚠️ Baza doimiy diskda EMAS! Har deploy'da ma'lumot (xodim profillari) "
                    "o'chishi mumkin. Railway'da Volume ulanganini tekshiring.")
    log.info("Bazada hozir %s ta xodim bor", await db.count_employees())
    await admin_handlers.load_admins()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    # Holatni tozalash middleware
    dp.message.middleware(ResetStateMiddleware())

    # Global xatolik ushlagich — hech qachon "jim qotish" bo'lmasin
    @dp.error()
    async def on_error(event: ErrorEvent):
        log.exception("Handler xatosi: %s", event.exception)
        err = str(event.exception)[:300]
        try:
            upd = event.update
            if upd.callback_query:
                await upd.callback_query.answer("Xatolik ❌", show_alert=True)
                await upd.callback_query.message.answer(f"❌ Xatolik:\n{err}")
            elif upd.message:
                await upd.message.answer(f"❌ Xatolik:\n{err}")
        except Exception:
            pass
        return True

    # Admin routeri birinchi (admin tugmalari ustunlik olishi uchun)
    dp.include_router(group_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(forms_handlers.router)
    dp.include_router(survey_handlers.router)
    dp.include_router(user_handlers.router)

    # Fon jarayonlari
    asyncio.create_task(faceid_poller(bot))
    asyncio.create_task(daily_report_loop(bot))
    asyncio.create_task(auto_refresh_menus(bot))

    # Admin: /yangilash — menyuni hammaga qo'lda yangilash
    from aiogram.filters import Command

    @dp.message(Command("yangilash"))
    async def cmd_refresh(msg: Message):
        if not admin_handlers.is_admin(msg.from_user.id):
            return
        await msg.answer("⏳ Menyu hammaga yuborilmoqda...")
        ok, fail = await refresh_menus(msg.bot)
        await db.set_setting("menu_signature", _menu_signature())
        await msg.answer(f"✅ Menyu yangilandi: {ok} ta odamga yuborildi"
                         + (f", {fail} tasiga yetmadi (botni bloklagan bo'lishi mumkin)." if fail else "."))

    # Userbot (guruhni o'qish) — sozlangan bo'lsa ishga tushadi
    try:
        from userbot import start_userbot
        await start_userbot(bot)
    except Exception as e:
        log.warning("Userbot ishga tushmadi: %s", e)

    log.info("Bot ishga tushdi. To'xtatish uchun Ctrl+C.")
    # Buyruqlar menyusi (Telegram'da "/" bosilganda ko'rinadi)
    try:
        from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats
        await bot.set_my_commands([
            BotCommand(command="jarima", description="Filial jarimalari: /jarima Filial oy"),
            BotCommand(command="jamoa", description="Filial xodimlari: /jamoa Filial"),
        ], scope=BotCommandScopeAllGroupChats())
        await bot.set_my_commands([
            BotCommand(command="start", description="Boshlash"),
            BotCommand(command="admin", description="Admin panel"),
            BotCommand(command="jarima", description="Filial jarimalari (admin)"),
            BotCommand(command="jamoa", description="Filial xodimlari (admin)"),
            BotCommand(command="id", description="Telegram ID"),
            BotCommand(command="yangilash", description="Menyuni hammaga yangilash (admin)"),
        ], scope=BotCommandScopeAllPrivateChats())
    except Exception as e:
        log.warning("Buyruqlar menyusini o'rnatib bo'lmadi: %s", e)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot to'xtatildi.")
