"""
Userbot — qurilma yuboradigan GURUHDAGI xabarlarni o'qiydi.

Bir bot boshqa bot xabarini o'qiy olmagani uchun, haqiqiy akkaunt (telefon
raqamli) guruhda o'tirib xabarlarni o'qiydi, ismdan xodimni topadi, bazaga
yozadi va o'sha xodimga bot orqali (rasm bilan birga) xabar yuboradi.
"""
import os
import re
import asyncio
import datetime as dt
import logging

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from aiogram.types import FSInputFile

import db
import reports
from scheduler import _notify
from config import TZ

log = logging.getLogger("userbot")

API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "").strip()
SESSION_STRING = os.getenv("SESSION_STRING", "").strip()
GROUP_ID = os.getenv("GROUP_ID", "").strip()

_CLIENT = None  # guruhga eslatma yuborish uchun saqlanadi


def parse_device_message(text: str):
    if not text:
        return None
    if "KELDI" in text:
        etype = "in"
    elif "KETDI" in text:
        etype = "out"
    else:
        return None

    name = None
    for line in text.splitlines():
        line = line.strip()
        if "ish joyiga" in line:
            name = line.split("ish joyiga")[0].strip()
            break
        if "ish joyidan" in line:
            name = line.split("ish joyidan")[0].strip()
            break

    tm = re.search(r"(?:Kelish|Ketish)\s*:\s*(\d{1,2}):(\d{2})", text)
    dm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if not (name and tm and dm):
        return None

    hh, mm = int(tm.group(1)), int(tm.group(2))
    dd, mo, yy = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
    try:
        ts = dt.datetime(yy, mo, dd, hh, mm, tzinfo=TZ)
    except ValueError:
        return None
    return {"event_type": etype, "name": name, "ts": ts}


def _group_matches(chat_id) -> bool:
    if not GROUP_ID:
        return True
    a = "".join(ch for ch in str(chat_id) if ch.isdigit())
    b = "".join(ch for ch in GROUP_ID if ch.isdigit())
    return a.endswith(b) or b.endswith(a)


async def post_to_group(text: str) -> bool:
    """Guruhga xabar yuboradi (eslatma uchun). Guruh ID avtomatik eslab qolinadi."""
    gid = await db.get_setting("group_chat_id")
    if not (_CLIENT and gid):
        return False
    try:
        await _CLIENT.send_message(int(gid), text)
        return True
    except Exception as e:
        log.warning("Guruhga yuborilmadi: %s", e)
        return False


async def start_userbot(bot):
    global _CLIENT
    if not (API_ID and API_HASH and SESSION_STRING):
        log.warning("Userbot sozlanmagan (API_ID/API_HASH/SESSION_STRING yo'q) — o'tkazib yuborildi.")
        return

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

    @client.on(events.NewMessage)
    async def handler(event):
        try:
            if not _group_matches(event.chat_id):
                return
            parsed = parse_device_message(event.raw_text or "")
            if not parsed:
                return
            # Guruh ID'sini eslab qolamiz (eslatma yuborish uchun)
            await db.set_setting("group_chat_id", str(event.chat_id))

            emp = await db.get_employee_by_name(parsed["name"])
            if not emp:
                await db.record_unknown(parsed["name"])
                log.info("Xodim topilmadi: '%s' (guruhda bor, bazada yo'q)", parsed["name"])
                return

            ext = f"tg-{event.chat_id}-{event.id}"
            etype, inserted = await db.add_event(
                emp["id"], parsed["ts"], external_id=ext, event_type=parsed["event_type"])
            if not inserted:
                return

            log.info("Qayd: %s %s %s", parsed["name"], etype, parsed["ts"].strftime("%H:%M"))

            if not emp["telegram_id"]:
                return  # xodim botga ulanmagan

            text = await reports.notify_text(emp, etype, parsed["ts"])

            # Guruhdagi rasm bo'lsa — xodimga rasm bilan yuboramiz
            if event.message and event.message.photo:
                path = None
                try:
                    path = await event.download_media(file="/tmp/")
                    await bot.send_photo(emp["telegram_id"], FSInputFile(path), caption=text)
                except Exception as e:
                    log.warning("Rasm yuborilmadi, matn yuboriladi: %s", e)
                    await bot.send_message(emp["telegram_id"], text)
                finally:
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
            else:
                await bot.send_message(emp["telegram_id"], text)
        except Exception as e:
            log.warning("Userbot handler xatosi: %s", e)

    await client.start()
    _CLIENT = client
    me = await client.get_me()
    log.info("Userbot ishga tushdi: %s (guruh filtri: %s)",
             me.username or me.first_name, GROUP_ID or "yo'q")
    asyncio.create_task(client.run_until_disconnected())
