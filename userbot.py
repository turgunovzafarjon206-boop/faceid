"""
Userbot — qurilma yuboradigan GURUHDAGI xabarlarni o'qiydi.

Nega kerak: bir bot boshqa bot yuborgan xabarni o'qiy olmaydi (Telegram cheklovi).
Shuning uchun haqiqiy akkaunt (telefon raqamli) guruhda o'tirib, xabarlarni o'qiydi,
ismdan xodimni topadi, bazaga yozadi va o'sha xodimga bot orqali xabar yuboradi.

Sozlamalar (Railway Variables):
  API_ID          - my.telegram.org dan
  API_HASH        - my.telegram.org dan
  SESSION_STRING  - login.py orqali bir marta olinadi
  GROUP_ID        - (ixtiyoriy) faqat shu guruhni o'qish uchun
"""
import os
import re
import asyncio
import datetime as dt
import logging

from telethon import TelegramClient, events
from telethon.sessions import StringSession

import db
from scheduler import _notify
from config import TZ

log = logging.getLogger("userbot")

API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "").strip()
SESSION_STRING = os.getenv("SESSION_STRING", "").strip()
GROUP_ID = os.getenv("GROUP_ID", "").strip()


def parse_device_message(text: str):
    """
    Qurilma xabarini tahlil qiladi.
    Qaytaradi: {"event_type": "in|out", "name": str, "ts": datetime} yoki None.
    """
    if not text:
        return None

    if "KELDI" in text:
        etype = "in"
    elif "KETDI" in text:
        etype = "out"
    else:
        return None

    # Ism: "... ish joyiga yetib keldi" yoki "... ish joyidan chiqdi"
    name = None
    for line in text.splitlines():
        line = line.strip()
        if "ish joyiga" in line:
            name = line.split("ish joyiga")[0].strip()
            break
        if "ish joyidan" in line:
            name = line.split("ish joyidan")[0].strip()
            break

    # Vaqt: "Kelish: 09:19" yoki "Ketish: 19:43"
    tm = re.search(r"(?:Kelish|Ketish)\s*:\s*(\d{1,2}):(\d{2})", text)
    # Sana: DD.MM.YYYY
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
        return True  # cheklov yo'q — barcha chatlar
    a = "".join(ch for ch in str(chat_id) if ch.isdigit())
    b = "".join(ch for ch in GROUP_ID if ch.isdigit())
    return a.endswith(b) or b.endswith(a)


async def start_userbot(bot):
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
            emp = await db.get_employee_by_name(parsed["name"])
            if not emp:
                log.info("Xodim topilmadi: '%s' (guruhda bor, bazada yo'q)", parsed["name"])
                return
            ext = f"tg-{event.chat_id}-{event.id}"
            etype, inserted = await db.add_event(
                emp["id"], parsed["ts"], external_id=ext,
                event_type=parsed["event_type"])
            if inserted:
                await _notify(bot, emp, etype, parsed["ts"])
                log.info("Qayd: %s %s %s", parsed["name"], etype, parsed["ts"].strftime("%H:%M"))
        except Exception as e:
            log.warning("Userbot handler xatosi: %s", e)

    await client.start()
    me = await client.get_me()
    log.info("Userbot ishga tushdi: %s (guruh filtri: %s)",
             me.username or me.first_name, GROUP_ID or "yo'q")
    asyncio.create_task(client.run_until_disconnected())
