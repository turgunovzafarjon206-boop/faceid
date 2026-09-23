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
    dp.include_router(admin_handlers.router)
    dp.include_router(forms_handlers.router)
    dp.include_router(survey_handlers.router)
    dp.include_router(user_handlers.router)

    # Fon jarayonlari
    asyncio.create_task(faceid_poller(bot))
    asyncio.create_task(daily_report_loop(bot))

    # Userbot (guruhni o'qish) — sozlangan bo'lsa ishga tushadi
    try:
        from userbot import start_userbot
        await start_userbot(bot)
    except Exception as e:
        log.warning("Userbot ishga tushmadi: %s", e)

    log.info("Bot ishga tushdi. To'xtatish uchun Ctrl+C.")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot to'xtatildi.")
