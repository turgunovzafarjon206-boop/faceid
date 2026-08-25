"""
Konfiguratsiya. Barcha maxfiy ma'lumotlar .env faylidan o'qiladi.
Hech qachon token/parolni to'g'ridan-to'g'ri kodga yozmang.
"""
import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
]

# --- FaceID qurilma API ---
# FACEID_MODE: mock | generic | hikvision
FACEID_MODE = os.getenv("FACEID_MODE", "mock").strip()
FACEID_API_URL = os.getenv("FACEID_API_URL", "").strip()
FACEID_API_TOKEN = os.getenv("FACEID_API_TOKEN", "").strip()
FACEID_API_USER = os.getenv("FACEID_API_USER", "").strip()
FACEID_API_PASS = os.getenv("FACEID_API_PASS", "").strip()
FACEID_POLL_INTERVAL = int(os.getenv("FACEID_POLL_INTERVAL", "15"))  # soniya

# --- Ish grafigi (standart) ---
DEFAULT_WORK_START = os.getenv("DEFAULT_WORK_START", "08:00")
DEFAULT_WORK_END = os.getenv("DEFAULT_WORK_END", "18:00")
GRACE_MINUTES = int(os.getenv("GRACE_MINUTES", "0"))  # kechikishga beriladigan imtiyoz

# --- Kunlik hisobot vaqti (HH:MM) ---
DAILY_REPORT_TIME = os.getenv("DAILY_REPORT_TIME", "23:30")

# --- Boshqa ---
TZ = ZoneInfo(os.getenv("TZ", "Asia/Tashkent"))

# --- Baza manzili ---
# Railway Volume ulangan bo'lsa (RAILWAY_VOLUME_MOUNT_PATH), baza AVTOMATIK
# o'sha diskka yoziladi — mount path /data, /date yoki boshqa bo'lsa ham farqi yo'q.
# Bu ma'lumot deploy paytida o'chib ketmasligini kafolatlaydi.
_vol = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip().rstrip("/")
if _vol:
    DB_PATH = f"{_vol}/faceid_bot.db"
else:
    DB_PATH = os.getenv("DB_PATH", "faceid_bot.db")

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN topilmadi. .env faylini to'ldiring.")
