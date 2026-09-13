"""
Fon jarayonlari:
1) FaceID polleri — qurilmadan yangi kirish/chiqishlarni oladi va xabar yuboradi.
2) Kunlik hisobot — belgilangan vaqtda har bir xodimga kun yakunini yuboradi.
"""
import asyncio
import datetime as dt
import logging

import db
import reports
from faceid import build_client
from config import FACEID_POLL_INTERVAL, DAILY_REPORT_TIME, TZ

log = logging.getLogger("scheduler")


async def faceid_poller(bot):
    # Bot ishga tushgan vaqtdan oldingi hodisalarni qayta yubormaslik uchun
    since = dt.datetime.now(TZ) - dt.timedelta(minutes=5)
    log.info("FaceID poller ishga tushdi")

    while True:
        interval = FACEID_POLL_INTERVAL
        try:
            client, interval = await build_client()
            events = await client.fetch_events(since)
            events.sort(key=lambda e: e["ts"])
            for ev in events:
                emp = await db.get_employee_by_faceid(ev["faceid_user_id"])
                if not emp or not emp["active"]:
                    continue
                etype, inserted = await db.add_event(
                    emp["id"], ev["ts"],
                    external_id=ev["external_id"],
                    event_type=ev.get("event_type"))
                if not inserted:
                    continue  # takror hodisa
                if ev["ts"] > since:
                    since = ev["ts"]
                await _notify(bot, emp, etype, ev["ts"])
        except Exception as e:
            log.warning("Poller xatosi: %s", e)
        await asyncio.sleep(interval)


async def _notify(bot, emp, etype, ts):
    if not emp["telegram_id"]:
        return
    text = await reports.notify_text(emp, etype, ts)
    try:
        await bot.send_message(emp["telegram_id"], text)
    except Exception as e:
        log.warning("Xabar yuborilmadi (%s): %s", emp["telegram_id"], e)


async def daily_report_loop(bot):
    """Har kuni DAILY_REPORT_TIME da kun yakunini yuboradi."""
    hh, mm = map(int, DAILY_REPORT_TIME.split(":"))
    sent_for = None
    log.info("Kunlik hisobot rejalashtirildi: %s", DAILY_REPORT_TIME)
    while True:
        now = dt.datetime.now(TZ)
        today = now.strftime("%Y-%m-%d")
        if now.hour == hh and now.minute == mm and sent_for != today:
            sent_for = today
            await _send_daily(bot, today)
        await asyncio.sleep(30)


async def _send_daily(bot, day):
    emps = await db.list_employees()
    for emp in emps:
        if not emp["telegram_id"]:
            continue
        events = await db.events_for_day(emp["id"], day)
        if not events:
            continue
        try:
            text = "📋 Kun yakuni\n\n" + await reports.daily_text(emp, day)
            await bot.send_message(emp["telegram_id"], text)
        except Exception as e:
            log.warning("Kunlik hisobot yuborilmadi: %s", e)
