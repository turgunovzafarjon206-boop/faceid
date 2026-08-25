"""
Hisobotlarni hisoblash va matn ko'rinishida chiqarish (o'zbekcha).
"""
import datetime as dt
import db


def fmt_duration(minutes: int) -> str:
    minutes = max(0, int(minutes))
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h} soat {m} daqiqa"
    if h:
        return f"{h} soat"
    return f"{m} daqiqa"


def _parse_hm(s: str) -> dt.time:
    hh, mm = s.split(":")
    return dt.time(int(hh), int(mm))


def compute_day(emp, events):
    """
    events: [(event_type, ts_iso), ...] shu kun uchun.
    Qaytaradi: dict(kirish, chiqish, ishlangan_min, kechikish_min, kech_qoldi)
    """
    if not events:
        return None
    times = [(t, dt.datetime.fromisoformat(ts)) for t, ts in events]
    ins = [d for t, d in times if t == "in"]
    outs = [d for t, d in times if t == "out"]

    first_in = min(ins) if ins else times[0][1]
    last_out = max(outs) if outs else (times[-1][1] if len(times) > 1 else None)

    worked = 0
    if last_out and last_out > first_in:
        worked = int((last_out - first_in).total_seconds() // 60)

    late_min = 0
    if emp["count_late"] and first_in:
        ws = _parse_hm(emp["work_start"])
        start_dt = first_in.replace(hour=ws.hour, minute=ws.minute,
                                    second=0, microsecond=0)
        grace = int(emp.get("grace_minutes") or 0)
        limit = start_dt + dt.timedelta(minutes=grace)
        if first_in > limit:
            late_min = int((first_in - start_dt).total_seconds() // 60)

    return {
        "kirish": first_in,
        "chiqish": last_out,
        "ishlangan_min": worked,
        "kechikish_min": late_min,
        "kech_qoldi": late_min > 0,
    }


async def daily_text(emp, day: str) -> str:
    events = await db.events_for_day(emp["id"], day)
    r = compute_day(emp, events)
    head = f"👤 {emp['first_name']} {emp['last_name']}\n📅 Sana: {day}\n"
    if not r:
        return head + "\nBu kuni hech qanday qayd yo'q."
    kirish = r["kirish"].strftime("%H:%M") if r["kirish"] else "—"
    chiqish = r["chiqish"].strftime("%H:%M") if r["chiqish"] else "— (hali chiqmagan)"
    txt = head + (
        f"\n🟢 Kirish: {kirish}"
        f"\n🔴 Chiqish: {chiqish}"
    )
    if emp["count_late"]:
        if r["kechikish_min"] > 0:
            txt += f"\n⏰ Kech qolish: {fmt_duration(r['kechikish_min'])}"
        else:
            txt += "\n⏰ Kech qolish: yo'q ✅"
    txt += f"\n⏱ Ishlangan vaqt: {fmt_duration(r['ishlangan_min'])}"
    return txt


async def period_text(emp, day_from: str, day_to: str, title: str) -> str:
    rows = await db.events_between(emp["id"], day_from, day_to)
    by_day = {}
    for day, etype, ts in rows:
        by_day.setdefault(day, []).append((etype, ts))

    worked_total = 0
    late_total = 0
    late_days = 0
    worked_days = 0
    lines = []
    for day in sorted(by_day):
        r = compute_day(emp, by_day[day])
        if not r:
            continue
        worked_days += 1
        worked_total += r["ishlangan_min"]
        late_total += r["kechikish_min"]
        if r["kech_qoldi"]:
            late_days += 1
        kirish = r["kirish"].strftime("%H:%M") if r["kirish"] else "—"
        chiqish = r["chiqish"].strftime("%H:%M") if r["chiqish"] else "—"
        mark = f" ⏰+{r['kechikish_min']}daq" if r["kech_qoldi"] else ""
        lines.append(f"• {day}: {kirish}–{chiqish} | {fmt_duration(r['ishlangan_min'])}{mark}")

    head = (f"👤 {emp['first_name']} {emp['last_name']}\n"
            f"🗓 {title} ({day_from} … {day_to})\n\n")
    summary = (
        f"📊 Umumiy natija:\n"
        f"✅ Ishlagan kun: {worked_days} kun\n"
        f"⏱ Ishlagan vaqt: {fmt_duration(worked_total)}\n"
    )
    if emp["count_late"]:
        summary += (f"⏰ Kech qolish vaqti: {fmt_duration(late_total)}\n"
                    f"🔴 Kech qolgan kun: {late_days} kun\n")
    detail = "\n".join(lines) if lines else "Qayd yo'q."
    return head + summary + "\n" + detail
