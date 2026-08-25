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
from scheduler import faceid_poller, daily_report_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("main")


async def main():
    await db.init_db()
    log.info("Baza tayyor.")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    # Admin routeri birinchi (admin tugmalari ustunlik olishi uchun)
    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)

    # Fon jarayonlari
    asyncio.create_task(faceid_poller(bot))
    asyncio.create_task(daily_report_loop(bot))

    log.info("Bot ishga tushdi. To'xtatish uchun Ctrl+C.")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot to'xtatildi.")
