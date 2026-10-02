"""Dars jadvali rasmini (HolliHop oylik ko'rinishi) o'qish.

Rasm sun'iy intellekt (vision) orqali tahlil qilinadi. Railway Variables'da
QUYIDAGILARDAN BITTASI kifoya:

  DEEPSEEK_API_KEY   - platform.deepseek.com dan (eng arzon)
  ANTHROPIC_API_KEY  - console.anthropic.com dan (Claude)

Ixtiyoriy:
  VISION_PROVIDER    - deepseek | anthropic | openai  (bo'lmasa — kalitga qarab avtomatik)
  VISION_MODEL       - model nomi (standart: deepseek -> deepseek-flash, anthropic -> claude-sonnet-5-5)
  VISION_BASE_URL    - OpenAI-uslubidagi boshqa xizmat uchun (masalan OpenRouter)
  VISION_API_KEY     - shu boshqa xizmatning kaliti

Oy tanlangach, katak sanaga quyidagicha bog'lanadi: kun raqami + hafta kuni (ustun)
tanlangan oydagi sanaga mos kelishi kerak — qo'shni oylarning kunlari chiqarib tashlanadi.
"""
import os
import re
import json
import base64
import calendar
import datetime as dt
import aiohttp

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
GENERIC_KEY = os.getenv("VISION_API_KEY", "").strip()
GENERIC_URL = os.getenv("VISION_BASE_URL", "").strip().rstrip("/")


def _provider():
    p = os.getenv("VISION_PROVIDER", "").strip().lower()
    if p:
        return p
    if DEEPSEEK_KEY:
        return "deepseek"
    if ANTHROPIC_KEY:
        return "anthropic"
    if GENERIC_KEY and GENERIC_URL:
        return "openai"
    return None


def _model(provider):
    m = os.getenv("VISION_MODEL", "").strip()
    if m:
        return m
    return {"deepseek": "deepseek-flash", "anthropic": "claude-sonnet-5-5"}.get(provider, "")


def provider_info():
    p = _provider()
    return f"{p} / {_model(p)}" if p else "sozlanmagan"

PROMPT = """Bu rasmda bitta o'qituvchining oylik dars jadvali (kalendar, Месяц ko'rinishi) bor.
Ustunlar: пн, вт, ср, чт, пт, сб, вс (dushanbadan yakshanbagacha).
Har bir katak chap yuqorisida kun raqami yozilgan. Katak ichida darslar (rangli bloklar) bo'lishi mumkin.
Har bir dars blokining boshida qalin raqam — dars boshlanish vaqti: "17" = 17:00, "9:30" = 09:30.

Faqat ICHIDA KAMIDA BITTA DARS BOR kataklarni qaytar. Har bir katak uchun:
- "row": yuqoridan qator raqami (0 dan boshlab, rasmda ko'ringan birinchi qator = 0)
- "col": ustun (0=пн, 1=вт, 2=ср, 3=чт, 4=пт, 5=сб, 6=вс)
- "day": katakdagi kun raqami (son)
- "start": shu katakdagi ENG ERTA dars boshlanish vaqti "HH:MM" formatida

Shuningdek "month_title": rasm tepasidagi oy nomi va yil (masalan "сентябрь 2026"), bo'lmasa null.

FAQAT JSON qaytar, boshqa hech narsa yozma, ``` belgilarisiz:
{"month_title": "...", "cells": [{"row":0,"col":3,"day":3,"start":"17:00"}]}"""

RU_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7,
    "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}


def norm_time(v):
    """'17' -> 1020, '9:30' -> 570, '17.00' -> 1020. Noto'g'ri bo'lsa None."""
    if v is None:
        return None
    s = str(v).strip().replace(".", ":")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?$", s)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return h * 60 + mi


def detect_month(title):
    """'сентябрь 2026' -> '2026-09'."""
    if not title:
        return None
    t = str(title).lower()
    ym = re.search(r"(20\d{2})", t)
    if not ym:
        return None
    # uzunroq kalitlarni oldin tekshiramiz ('май' 'март' bilan aralashmasin)
    for key in sorted(RU_MONTHS, key=len, reverse=True):
        if key in t and not (key == "ма" and ("март" in t)):
            return f"{ym.group(1)}-{RU_MONTHS[key]:02d}"
    return None


import logging as _logging
_log = _logging.getLogger("lesson_vision")

RETRY_PROMPT = PROMPT + """

MUHIM: Javobing FAQAT bitta JSON obyekt bo'lsin. Izoh, tushuntirish, markdown yozma.
Agar rasmni yaxshi ko'ra olmasang ham, ko'ringan kataklarni JSON shaklida qaytar."""


async def _call_anthropic(image_bytes, media_type, model, prompt):
    payload = {
        "model": model, "max_tokens": 8000,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                         "data": base64.b64encode(image_bytes).decode()}},
            {"type": "text", "text": prompt}]}],
    }
    headers = {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    body = await _post("https://api.anthropic.com/v1/messages", payload, headers)
    return "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")


async def _call_openai_style(image_bytes, media_type, model, base_url, key, prompt):
    """DeepSeek, OpenRouter va boshqa OpenAI-uslubidagi xizmatlar."""
    data_url = f"data:{media_type};base64,{base64.b64encode(image_bytes).decode()}"
    base = {
        "model": model, "max_tokens": 8000, "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}}]}],
    }
    headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    url = f"{base_url}/chat/completions"
    # Avval JSON rejimi bilan; xizmat qo'llamasa (400) — oddiy so'rov
    try:
        body = await _post(url, dict(base, response_format={"type": "json_object"}), headers)
    except RuntimeError as e:
        if "(400)" not in str(e) and "(422)" not in str(e):
            raise
        body = await _post(url, base, headers)
    msg = (body.get("choices") or [{}])[0].get("message", {}) or {}
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    content = content or ""
    # "Fikrlash" rejimida javob boshqa maydonga tushishi mumkin
    if "{" not in content:
        alt = msg.get("reasoning_content") or msg.get("reasoning") or ""
        if isinstance(alt, str) and "{" in alt:
            content = alt
    return content


async def _post(url, payload, headers):
    timeout = aiohttp.ClientTimeout(total=150)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(url, json=payload, headers=headers) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200:
                err = body.get("error") if isinstance(body, dict) else None
                msg = (err.get("message") if isinstance(err, dict) else str(err or body))[:300]
                raise RuntimeError(f"API xatosi ({resp.status}): {msg}")
            return body


_CELL_RE = re.compile(r"\{[^{}]*?\"day\"[^{}]*?\}")
_TITLE_RE = re.compile(r"\"month_title\"\s*:\s*\"([^\"]*)\"")


def _extract(text):
    """Javobdan kataklarni ajratadi. JSON to'liq bo'lmasa ham alohida kataklarni topadi.
    Qaytaradi: (cells, month_title)."""
    text = (text or "").replace("```json", "").replace("```", "").strip()
    raw_cells, title = None, None
    i, j = text.find("{"), text.rfind("}")
    if i != -1 and j > i:
        try:
            data = json.loads(text[i:j + 1])
            if isinstance(data, dict):
                raw_cells, title = data.get("cells"), data.get("month_title")
            elif isinstance(data, list):
                raw_cells = data
        except (ValueError, TypeError):
            pass
    if raw_cells is None:   # buzilgan/kesilgan JSON — kataklarni birma-bir yig'amiz
        raw_cells = []
        for m in _CELL_RE.finditer(text):
            try:
                raw_cells.append(json.loads(m.group(0)))
            except ValueError:
                continue
        tm = _TITLE_RE.search(text)
        title = tm.group(1) if tm else None
    cells = []
    for c in raw_cells or []:
        if not isinstance(c, dict):
            continue
        try:
            cells.append({
                "row": int(c["row"]) if c.get("row") is not None else None,
                "col": int(c["col"]) if c.get("col") is not None else None,
                "day": int(c.get("day")),
                "start": norm_time(c.get("start")),
            })
        except (TypeError, ValueError, KeyError):
            continue
    return [c for c in cells if c["start"] is not None], title


async def _ask(provider, model, image_bytes, media_type, prompt):
    if provider == "anthropic":
        return await _call_anthropic(image_bytes, media_type, model, prompt)
    if provider == "deepseek":
        if not DEEPSEEK_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY o'rnatilmagan.")
        return await _call_openai_style(image_bytes, media_type, model,
                                        "https://api.deepseek.com", DEEPSEEK_KEY, prompt)
    if not (GENERIC_URL and GENERIC_KEY):
        raise RuntimeError("VISION_BASE_URL va VISION_API_KEY o'rnatilmagan.")
    return await _call_openai_style(image_bytes, media_type, model, GENERIC_URL, GENERIC_KEY, prompt)


async def parse_image(image_bytes, media_type="image/jpeg"):
    """Qaytaradi: (cells, month_title). Bir marta avtomatik qayta urinadi."""
    provider = _provider()
    if not provider:
        raise RuntimeError(
            "Rasm o'qish uchun API kalit o'rnatilmagan. Railway → Variables ga "
            "DEEPSEEK_API_KEY (yoki ANTHROPIC_API_KEY) qo'shing.")
    model = _model(provider)
    last_text = ""
    for attempt, prompt in enumerate((PROMPT, RETRY_PROMPT), 1):
        text = await _ask(provider, model, image_bytes, media_type, prompt)
        last_text = text
        _log.info("Vision javobi (%s/%s, urinish %s): %s", provider, model, attempt, (text or "")[:300])
        cells, title = _extract(text)
        if cells:
            return cells, title
    snippet = " ".join((last_text or "(bo'sh javob)").split())[:160]
    raise RuntimeError(
        f"Rasmdan jadval o'qib bo'lmadi ({provider} / {model}).\nModel javobi: «{snippet}»")


def parse_text(text):
    """Zaxira usul (rasmsiz): har qatorda 'kun vaqt', masalan '3 17:00' yoki '05.09 9:30'."""
    cells = []
    for line in str(text).splitlines():
        tokens = re.findall(r"\d{1,2}(?:[:.]\d{2,4})*", line)
        if len(tokens) < 2:
            continue
        day = int(re.split(r"[:.]", tokens[0])[0])     # '3' yoki '05.09' -> 3 / 5
        start = norm_time(tokens[-1])                   # '17:00', '9.30', '17'
        if start is not None and 1 <= day <= 31:
            cells.append({"row": None, "col": None, "day": day, "start": start})
    return cells


def map_to_month(cells, ym):
    """Kataklarni tanlangan oyning sanalariga bog'laydi. Qaytaradi: {'YYYY-MM-DD': start_min}."""
    y, m = map(int, ym.split("-"))
    last = calendar.monthrange(y, m)[1]
    candidates = {}  # sana -> [(row, start)]
    for c in cells:
        d = c["day"]
        if not (1 <= d <= last):
            continue
        date = dt.date(y, m, d)
        if c["col"] is not None and date.weekday() != c["col"]:
            continue  # qo'shni oyning kuni (hafta kuni mos emas)
        candidates.setdefault(date.isoformat(), []).append((c["row"], c["start"]))
    result = {}
    for date, lst in candidates.items():
        if len(lst) == 1 or lst[0][0] is None:
            result[date] = min(s for _, s in lst)
            continue
        # Bir xil sana ikki katakda (masalan fevral 28 kunlik): kichik kunlar — yuqori qator,
        # katta kunlar — pastki qator
        d = int(date[-2:])
        rows = [r for r, _ in lst if r is not None]
        pick = min(rows) if d <= 14 else max(rows)
        result[date] = min(s for r, s in lst if r == pick)
    return result
