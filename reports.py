"""
Hisobotlarni hisoblash va matn ko'rinishida chiqarish (o'zbekcha).
"""
import datetime as dt
import db
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


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


UZ_MONTHS = ["", "yanvar", "fevral", "mart", "aprel", "may", "iyun",
             "iyul", "avgust", "sentyabr", "oktyabr", "noyabr", "dekabr"]


def uz_date(day_str):
    """'2026-09-04' -> '4-sentyabr 2026'"""
    y, m, d = day_str.split("-")
    return f"{int(d)}-{UZ_MONTHS[int(m)]} {y}"


def fmt_sum(x):
    return f"{int(x):,}".replace(",", " ")


def fine_rate(streak):
    """Ketma-ket kech qolish tartibiga qarab 1 daqiqa jarimasi (so'm)."""
    if streak <= 3:
        return 1000
    if streak <= 6:
        return 3000
    return 5000


async def _late_series(emp, day_from, day_to):
    """Kunlar bo'yicha (day, worked_min, late_min, r) ketma-ketligi (tartibda)."""
    rows = await db.events_between(emp["id"], day_from, day_to)
    by_day = {}
    for day, etype, ts in rows:
        by_day.setdefault(day, []).append((etype, ts))
    series = []
    for day in sorted(by_day):
        r = compute_day(emp, by_day[day])
        if not r:
            continue
        late = r["kechikish_min"] if emp["count_late"] else 0
        series.append((day, r, late))
    return series


def _apply_fines(series):
    """Ketma-ket kech qolishga qarab jarima. Qaytaradi: {day: (fine, streak, rate)}, total."""
    streak = 0
    total = 0
    info = {}
    for day, r, late in series:
        if late > 0:
            streak += 1
            rate = fine_rate(streak)
            fine = late * rate
        else:
            streak = 0
            rate = 0
            fine = 0
        info[day] = (fine, streak, rate)
        total += fine
    return info, total


def _month_bounds(day_str):
    y, m, _ = day_str.split("-")
    import calendar
    last = calendar.monthrange(int(y), int(m))[1]
    return f"{y}-{m}-01", f"{y}-{m}-{last:02d}"


async def show_fine_enabled():
    return (await db.get_setting("show_fine")) == "1"


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


async def daily_text(emp, day: str, for_admin=False) -> str:
    events = await db.events_for_day(emp["id"], day)
    r = compute_day(emp, events)
    head = f"👤 {emp['first_name']} {emp['last_name']}\n📅 Sana: {uz_date(day)}\n"
    if not r:
        return head + "\nBu kuni hech qanday qayd yo'q."
    kirish = r["kirish"].strftime("%H:%M") if r["kirish"] else "—"
    chiqish = r["chiqish"].strftime("%H:%M") if r["chiqish"] else "— (hali chiqmagan)"
    txt = head + (f"\n🟢 Kirish: {kirish}\n🔴 Chiqish: {chiqish}")
    if emp["count_late"]:
        if r["kechikish_min"] > 0:
            txt += f"\n⏰ Kech qolish: {r['kechikish_min']} daqiqa"
        else:
            txt += "\n⏰ Kech qolish: yo'q ✅"
    txt += f"\n⏱ Ishlangan vaqt: {fmt_duration(r['ishlangan_min'])}"

    # Jarima (oy boshidan shu kungacha ketma-ketlik bo'yicha)
    if emp["count_late"] and r["kechikish_min"] > 0:
        show = for_admin or await show_fine_enabled()
        if show:
            mf, mt = _month_bounds(day)
            series = await _late_series(emp, mf, day)
            info, _ = _apply_fines(series)
            fine = info.get(day, (0, 0, 0))[0]
            if fine:
                txt += f"\n💰 Jarima: {fmt_sum(fine)} so'm"
    return txt


async def period_text(emp, day_from: str, day_to: str, title: str, for_admin=False) -> str:
    series = await _late_series(emp, day_from, day_to)
    info, fine_total = _apply_fines(series)

    worked_total = 0
    late_total = 0
    late_days = 0
    worked_days = 0
    lines = []
    for day, r, late in series:
        worked_days += 1
        worked_total += r["ishlangan_min"]
        late_total += late
        if late > 0:
            late_days += 1
        kirish = r["kirish"].strftime("%H:%M") if r["kirish"] else "—"
        chiqish = r["chiqish"].strftime("%H:%M") if r["chiqish"] else "—"
        late_part = f" (Kech qolish {late} daqiqa)" if late > 0 else ""
        lines.append(f"{uz_date(day)} {kirish}-{chiqish} | "
                     f"{fmt_duration(r['ishlangan_min'])}{late_part}")

    head = (f"👤 {emp['first_name']} {emp['last_name']}\n"
            f"🗓 {title} ({uz_date(day_from)} … {uz_date(day_to)})\n\n")
    summary = (
        f"📊 Umumiy natija:\n"
        f"✅ Ishlagan kun: {worked_days} kun\n"
        f"⏱ Ishlagan vaqt: {fmt_duration(worked_total)}\n"
    )
    if emp["count_late"]:
        summary += (f"⏰ Kech qolish vaqti: {fmt_duration(late_total)}\n"
                    f"🔴 Kech qolgan kun: {late_days} kun\n")
        show = for_admin or await show_fine_enabled()
        if show and fine_total:
            summary += f"💰 Jami jarima: {fmt_sum(fine_total)} so'm\n"
    detail = "\n".join(lines) if lines else "Qayd yo'q."
    return head + summary + "\n" + detail


# ==================== EXCEL HISOBOT ====================
_HEAD_FILL = PatternFill("solid", fgColor="2F5496")
_HEAD_FONT = Font(color="FFFFFF", bold=True)
_CENTER = Alignment(horizontal="center", vertical="center")
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _style_header(ws, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = _HEAD_FILL
        cell.font = _HEAD_FONT
        cell.alignment = _CENTER
        cell.border = _BORDER


def _autosize(ws):
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(width + 3, 40)


async def build_period_excel(employees, day_from, day_to, title):
    """Barcha xodimlar bo'yicha davr hisobotini .xlsx qilib yaratadi. Fayl yo'lini qaytaradi."""
    wb = Workbook()

    # 1-varaq: Umumiy
    ws = wb.active
    ws.title = "Umumiy"
    ws.append(["Xodim", "Telefon", "Ishlagan kun", "Ishlangan vaqt",
               "Soat (jami)", "Kech qolgan kun", "Kech qolish (daqiqa)", "Jarima (so'm)"])

    # 2-varaq: Kunlik
    ws2 = wb.create_sheet("Kunlik")
    ws2.append(["Xodim", "Sana", "Kirish", "Chiqish", "Ishlangan vaqt", "Kechikish (daqiqa)"])

    for emp in employees:
        series = await _late_series(emp, day_from, day_to)
        info, fine_total = _apply_fines(series)
        worked_total = late_total = late_days = worked_days = 0
        for day, r, late in series:
            worked_days += 1
            worked_total += r["ishlangan_min"]
            late_total += late
            if late > 0:
                late_days += 1
            ws2.append([
                f"{emp['first_name']} {emp['last_name']}", uz_date(day),
                r["kirish"].strftime("%H:%M") if r["kirish"] else "",
                r["chiqish"].strftime("%H:%M") if r["chiqish"] else "",
                fmt_duration(r["ishlangan_min"]), late,
            ])
        ws.append([
            f"{emp['first_name']} {emp['last_name']}", emp["phone"], worked_days,
            fmt_duration(worked_total), round(worked_total / 60, 1),
            late_days, late_total, fine_total if emp["count_late"] else 0,
        ])

    _style_header(ws, 8)
    _style_header(ws2, 6)
    _autosize(ws)
    _autosize(ws2)
    ws.freeze_panes = "A2"
    ws2.freeze_panes = "A2"

    safe = title.replace(" ", "_").replace("'", "")
    path = f"/tmp/{safe}_{day_from}_{day_to}.xlsx"
    wb.save(path)
    return path


# ==================== BILDIRISHNOMA MATNI (tahrirlanadigan) ====================
import string as _string


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def safe_format(template, **kwargs):
    """Shablonni to'ldiradi; noma'lum {joy} bo'lsa xato bermaydi, bo'sh qoldiradi."""
    try:
        return _string.Formatter().vformat(template, (), _SafeDict(**kwargs))
    except Exception:
        return template


async def notify_text(emp, etype, ts):
    """Xodimga yuboriladigan kirish/chiqish xabari (admin tahrirlagan shablon bilan)."""
    day = ts.strftime("%Y-%m-%d")
    events = await db.events_for_day(emp["id"], day)
    r = compute_day(emp, events) or {}
    worked = fmt_duration(r.get("ishlangan_min", 0))
    late_min = r.get("kechikish_min", 0)

    late = ""
    if etype == "in" and emp["count_late"] and late_min > 0:
        late = f"\n⏰ Siz {fmt_duration(late_min)} kech qoldingiz."
        if await show_fine_enabled():
            mf, _ = _month_bounds(day)
            series = await _late_series(emp, mf, day)
            info, _ = _apply_fines(series)
            fine = info.get(day, (0, 0, 0))[0]
            if fine:
                late += f"\n💰 Jarima: {fmt_sum(fine)} so'm"

    if etype == "in":
        tpl = await db.get_template("tpl_in", db.DEFAULT_TPL_IN)
    else:
        tpl = await db.get_template("tpl_out", db.DEFAULT_TPL_OUT)

    return safe_format(
        tpl,
        name=f"{emp['first_name']} {emp['last_name']}",
        time=ts.strftime("%H:%M"),
        date=ts.strftime("%d.%m.%Y"),
        worked=worked,
        late=late,
        late_min=late_min,
    )
