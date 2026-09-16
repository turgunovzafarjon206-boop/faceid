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
    exempt_days = await db.exempt_days_for(emp["id"])
    series = []
    for day in sorted(by_day):
        r = compute_day(emp, by_day[day])
        if not r:
            continue
        # Kechirim: bu kun uchun kechikish hisoblanmasin
        if r["kechikish_min"] and day in exempt_days:
            r["kechikish_min"] = 0
            r["kech_qoldi"] = False
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


async def show_fine_for(emp, for_admin=False):
    """Jarima shu xodimga ko'rinadimi? Admin har doim ko'radi."""
    if for_admin:
        return True
    v = await db.get_setting("fine_deps")
    if v == "all":
        return True
    if not v:
        return False
    ids = set()
    for x in v.split(","):
        x = x.strip()
        if x.isdigit():
            ids.add(int(x))
    return emp.get("department_id") in ids


def months_list(n=12):
    """Oxirgi n oy: [(label, 'YYYY-MM'), ...] (yangi -> eski)."""
    now = dt.datetime.now()
    out = []
    y, m = now.year, now.month
    for _ in range(n):
        out.append((f"{UZ_MONTHS[m]} {y}", f"{y}-{m:02d}"))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def month_bounds(ym):
    """'2026-09' -> ('2026-09-01', '2026-09-30')"""
    import calendar
    y, m = ym.split("-")
    last = calendar.monthrange(int(y), int(m))[1]
    return f"{y}-{m}-01", f"{y}-{m}-{last:02d}"


def compute_day(emp, events):
    """
    events: [(event_type, ts_iso), ...] shu kun uchun.
    Faqat kirish yoki faqat chiqish bo'lsa: bori olinadi, yo'g'i None,
    ish vaqti 0. Kech qolish faqat KIRISH bo'lsa hisoblanadi.
    """
    if not events:
        return None
    times = [(t, dt.datetime.fromisoformat(ts)) for t, ts in events]
    ins = [d for t, d in times if t == "in"]
    outs = [d for t, d in times if t == "out"]

    first_in = min(ins) if ins else None
    last_out = max(outs) if outs else None

    # Ish vaqti faqat kirish va chiqish ikkalasi bo'lsa hisoblanadi
    worked = 0
    if first_in and last_out and last_out > first_in:
        worked = int((last_out - first_in).total_seconds() // 60)

    # Kech qolish faqat KIRISH bo'lsa
    late_min = 0
    if emp["count_late"] and first_in:
        ws = _parse_hm(emp["work_start"])
        start_dt = first_in.replace(hour=ws.hour, minute=ws.minute,
                                    second=0, microsecond=0)
        grace = int(emp.get("grace_minutes") or 0)
        limit = start_dt + dt.timedelta(minutes=grace)
        if first_in > limit:
            late_min = int((first_in - start_dt).total_seconds() // 60)

    # Ish grafigidan ortiqcha ishlangan (chiqish ish oxiridan keyin)
    overtime = 0
    if last_out:
        we = _parse_hm(emp["work_end"])
        end_dt = last_out.replace(hour=we.hour, minute=we.minute,
                                  second=0, microsecond=0)
        if last_out > end_dt:
            overtime = int((last_out - end_dt).total_seconds() // 60)

    return {
        "kirish": first_in,
        "chiqish": last_out,
        "ishlangan_min": worked,
        "kechikish_min": late_min,
        "kech_qoldi": late_min > 0,
        "ortiqcha_min": overtime,
    }


async def daily_text(emp, day: str, for_admin=False) -> str:
    events = await db.events_for_day(emp["id"], day)
    r = compute_day(emp, events)
    head = f"👤 {db.full_name(emp)}\n📅 Sana: {uz_date(day)}\n"
    if not r:
        return head + "\nBu kuni hech qanday qayd yo'q."
    kirish = r["kirish"].strftime("%H:%M") if r["kirish"] else "-"
    chiqish = r["chiqish"].strftime("%H:%M") if r["chiqish"] else "-"
    # Kechirim
    exempt = r["kechikish_min"] and await db.is_exempt(emp["id"], day)
    if exempt:
        r["kechikish_min"] = 0
        r["kech_qoldi"] = False
    txt = head + (f"\n🟢 Kirish: {kirish}\n🔴 Chiqish: {chiqish}")
    if emp["count_late"]:
        if r["kechikish_min"] > 0:
            txt += f"\n❗️Kech qolish: {r['kechikish_min']} daqiqa"
        elif exempt:
            txt += "\n⏰ Kech qolish: hisobga olinmadi (kechirim) ✅"
        else:
            txt += "\n⏰ Kech qolish: yo'q ✅"
    txt += f"\n⏱ Ishlangan vaqt: {fmt_duration(r['ishlangan_min'])}"
    if r.get("ortiqcha_min", 0) > 0:
        txt += f"\n➕ Ortiqcha ishlangan: {fmt_duration(r['ortiqcha_min'])}"

    # Jarima (oy boshidan shu kungacha ketma-ketlik bo'yicha)
    if emp["count_late"] and r["kechikish_min"] > 0:
        show = await show_fine_for(emp, for_admin)
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
    over_total = 0
    lines = []
    for day, r, late in series:
        worked_days += 1
        worked_total += r["ishlangan_min"]
        late_total += late
        over_total += r.get("ortiqcha_min", 0)
        if late > 0:
            late_days += 1
        kirish = r["kirish"].strftime("%H:%M") if r["kirish"] else "-"
        chiqish = r["chiqish"].strftime("%H:%M") if r["chiqish"] else "-"
        late_part = f"❗️Kech qolish {late} daqiqa" if late > 0 else ""
        over_part = f" ➕Ortiqcha {fmt_duration(r['ortiqcha_min'])}" if r.get("ortiqcha_min", 0) > 0 else ""
        lines.append(f"{uz_date(day)} {kirish}-{chiqish} | "
                     f"{fmt_duration(r['ishlangan_min'])}{late_part}{over_part}")

    head = (f"👤 {db.full_name(emp)}\n"
            f"🗓 {title} ({uz_date(day_from)} … {uz_date(day_to)})\n\n")
    summary = (
        f"📊 Umumiy natija:\n"
        f"✅ Ishlagan kun: {worked_days} kun\n"
        f"⏱ Ishlagan vaqt: {fmt_duration(worked_total)}\n"
    )
    if over_total > 0:
        summary += f"➕ Ortiqcha ishlangan: {fmt_duration(over_total)}\n"
    if emp["count_late"]:
        summary += (f"⏰ Kech qolish vaqti: {fmt_duration(late_total)}\n"
                    f"🔴 Kech qolgan kun: {late_days} kun\n")
        show = await show_fine_for(emp, for_admin)
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


def _safe_sheet_name(name, used):
    for ch in r'[]:*?/\\':
        name = name.replace(ch, " ")
    name = name.strip()[:28] or "Xodim"
    base = name
    i = 1
    while name.lower() in used:
        i += 1
        name = f"{base} {i}"[:31]
    used.add(name.lower())
    return name


async def build_period_excel(employees, day_from, day_to, title):
    """1-list: umumiy. Keyingi listlar: har bir xodim uchun kunlik + oylik jami."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Umumiy"
    ws.append(["Xodim", "Telefon", "Bo'lim", "Ishlagan kun", "Ishlangan vaqt",
               "Soat (jami)", "Ortiqcha", "Kech qolgan kun", "Kech qolish (daqiqa)", "Jarima (so'm)"])

    used_names = {"umumiy"}
    # bo'lim nomlari keshi
    dep_cache = {}

    async def dep_name(dep_id):
        if not dep_id:
            return ""
        if dep_id not in dep_cache:
            d = await db.get_department(dep_id)
            dep_cache[dep_id] = d["name"] if d else ""
        return dep_cache[dep_id]

    for emp in employees:
        series = await _late_series(emp, day_from, day_to)
        info, fine_total = _apply_fines(series)
        worked_total = late_total = late_days = worked_days = 0

        # xodim uchun alohida list
        sheet = wb.create_sheet(_safe_sheet_name(db.full_name(emp), used_names))
        sheet.append([f"👤 {db.full_name(emp)}  |  📞 {emp['phone']}  |  🏢 {await dep_name(emp.get('department_id')) or 'Bo‘limsiz'}"])
        sheet.append(["Sana", "Kirish", "Chiqish", "Ishlangan vaqt",
                      "Ortiqcha (daqiqa)", "Kechikish (daqiqa)", "Jarima (so'm)"])

        over_total = 0
        for day, r, late in series:
            worked_days += 1
            worked_total += r["ishlangan_min"]
            late_total += late
            over_total += r.get("ortiqcha_min", 0)
            if late > 0:
                late_days += 1
            fine = info.get(day, (0, 0, 0))[0] if emp["count_late"] else 0
            sheet.append([
                uz_date(day),
                r["kirish"].strftime("%H:%M") if r["kirish"] else "-",
                r["chiqish"].strftime("%H:%M") if r["chiqish"] else "-",
                fmt_duration(r["ishlangan_min"]),
                r.get("ortiqcha_min", 0),
                late,
                fine,
            ])

        # oylik jami (pastda)
        sheet.append([])
        sheet.append(["OYLIK JAMI:"])
        sheet.append(["Ishlagan kun", worked_days])
        sheet.append(["Umumiy ishlangan vaqt", fmt_duration(worked_total)])
        sheet.append(["Soat (jami)", round(worked_total / 60, 1)])
        sheet.append(["Ortiqcha ishlangan", fmt_duration(over_total)])
        sheet.append(["Kech qolgan kun", late_days])
        sheet.append(["Jami kechikish (daqiqa)", late_total])
        sheet.append(["Jami jarima (so'm)", fine_total if emp["count_late"] else 0])

        # sarlavha (2-qator) bezaklari
        for c in range(1, 8):
            cell = sheet.cell(row=2, column=c)
            cell.fill = _HEAD_FILL
            cell.font = _HEAD_FONT
            cell.alignment = _CENTER
        _autosize(sheet)

        # umumiy varaqqa qator
        ws.append([
            db.full_name(emp), emp["phone"], await dep_name(emp.get("department_id")),
            worked_days, fmt_duration(worked_total), round(worked_total / 60, 1),
            fmt_duration(over_total), late_days, late_total,
            fine_total if emp["count_late"] else 0,
        ])

    _style_header(ws, 10)
    _autosize(ws)
    ws.freeze_panes = "A2"

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
        if await show_fine_for(emp):
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
        name=db.full_name(emp),
        time=ts.strftime("%H:%M"),
        date=ts.strftime("%d.%m.%Y"),
        worked=worked,
        late=late,
        late_min=late_min,
    )
