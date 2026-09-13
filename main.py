"""
Botni ishga tushirish nuqtasi.
Ishga tushirish:  python main.py
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

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


async def main():
    await db.init_db()
    import os
    from config import DB_PATH
    log.info("DB manzili: %s (fayl mavjud: %s)",
             os.path.abspath(DB_PATH), os.path.exists(DB_PATH))
    log.info("Bazada hozir %s ta xodim bor", await db.count_employees())
    await admin_handlers.load_admins()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

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
