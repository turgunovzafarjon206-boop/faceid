# FaceID Davomat Telegram Bot

Xodimlarning FaceID qurilmasidan kirish/chiqish vaqtlarini kuzatuvchi Telegram bot.
Kunlik/oylik/sana/davr hisobotlari, real vaqt xabarnomalari va admin panel bilan.

---

## 0. Muhim: tokenni yangilang

Siz tokenni ochiq yozgansiz. Xavfsizlik uchun:

1. Telegramda **@BotFather** ga kiring
2. `/mybots` → botingiz → **API Token** → **Revoke current token**
3. Yangi tokenni oling va `.env` fayliga yozing (kodga emas!)

Telegram ID ni bilish uchun: **@userinfobot** ga `/start` yozing.

---

## 1. Fayllar

```
faceid_bot/
├── main.py            # ishga tushirish nuqtasi
├── config.py          # sozlamalar (.env dan o'qiydi)
├── db.py              # baza (SQLite)
├── faceid.py          # FaceID qurilma bilan bog'lanish
├── reports.py         # hisobotlar
├── keyboards.py       # tugmalar
├── user_handlers.py   # xodim menyusi
├── admin_handlers.py  # admin panel
├── scheduler.py       # poller + kunlik hisobot
├── requirements.txt
└── .env.example       # namuna sozlama
```

---

## 2. Kompyuterda sinash (Windows/Mac/Linux)

```bash
# 1) Python 3.10+ o'rnatilgan bo'lsin
python --version

# 2) Papkaga kiring
cd faceid_bot

# 3) Virtual muhit
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 4) Kutubxonalar
pip install -r requirements.txt

# 5) Sozlama faylini yarating
cp .env.example .env      # Windows: copy .env.example .env
# .env ni ochib BOT_TOKEN va ADMIN_IDS ni to'ldiring

# 6) Ishga tushiring
python main.py
```

Botga Telegramdan `/start` yozing. Admin `/admin` orqali panelga kiradi.

> `FACEID_MODE=mock` — qurilmasiz sinash uchun (kirish/chiqish o'qilmaydi).
> Qurilma ulanganda `generic` yoki `hikvision` qiling.

---

## 3. Ishlatish tartibi

1. **Admin** `/admin` → **➕ Xodim qo'shish** → Ism, Familiya, Telefon,
   FaceID ID, ish grafigi (`08:00-18:00`).
2. **Xodim** botga `/start` → o'z telefon raqamini yuboradi → ulanadi.
3. Xodim FaceID'dan o'tganda botga avtomatik xabar keladi (kirish/chiqish).
4. Xodim menyudan **Bugun / Bu oy / Sana / Davr** hisobotini ko'radi.
5. Kun oxirida (`DAILY_REPORT_TIME`) har bir xodimga kun yakuni yuboriladi.

**Admin panel:**
- 👥 Xodimlar → tanlash → tahrirlash, kechikishni hisoblash/hisoblamaslik, o'chirish
- 📊 Hisobot → bugungi umumiy hisobot

---

## 4. FaceID qurilmani ulash

`faceid.py` universal qilib yozilgan. `.env` da `FACEID_MODE` ni tanlang:

- **generic** — oddiy JSON API. `FACEID_API_URL` va (kerak bo'lsa) `FACEID_API_TOKEN`
  ni to'ldiring. Agar API'ingiz javob formati boshqacha bo'lsa,
  `faceid.py` dagi `GenericFaceIDClient._parse()` funksiyasini moslashtiring.
- **hikvision** — Hikvision qurilmalari (ISAPI). `FACEID_API_URL=http://IP`,
  `FACEID_API_USER`, `FACEID_API_PASS` ni to'ldiring.

`faceid_user_id` — bu qurilmadagi xodim ID'si. Uni admin xodim qo'shayotganda kiritadi.

---

## 5. BEPUL 24/7 ishga tushirish (Oracle Cloud Always Free)

Bu haqiqiy bepul, doimiy VPS (kartadan pul yechilmaydi).

### 5.1. Server yaratish
1. https://www.oracle.com/cloud/free/ → ro'yxatdan o'ting (karta faqat tasdiqlash uchun)
2. **Create a VM instance** → **Always Free eligible** shaklni tanlang
   (Canonical **Ubuntu 22.04**)
3. SSH kalitni yuklab oling, **Create**
4. Instance IP manzilini eslab qoling

### 5.2. Serverga ulaning
```bash
ssh -i kalit.key ubuntu@SERVER_IP
```

### 5.3. Kerakli narsalarni o'rnating
```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

### 5.4. Loyihani yuklang
```bash
# faceid_bot papkasini serverga ko'chiring (scp yoki git orqali).
# scp misoli (o'z kompyuteringizdan):
#   scp -i kalit.key -r faceid_bot ubuntu@SERVER_IP:/home/ubuntu/

cd /home/ubuntu/faceid_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env      # BOT_TOKEN, ADMIN_IDS va FaceID sozlamalarini yozing
```

### 5.5. 24/7 avtomatik ishlashi uchun (systemd)
```bash
sudo nano /etc/systemd/system/faceidbot.service
```
Ichiga yozing:
```ini
[Unit]
Description=FaceID Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/faceid_bot
ExecStart=/home/ubuntu/faceid_bot/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Saqlang (Ctrl+O, Enter, Ctrl+X), so'ng:
```bash
sudo systemctl daemon-reload
sudo systemctl enable faceidbot
sudo systemctl start faceidbot

# Holatini ko'rish:
sudo systemctl status faceidbot
# Loglarni ko'rish:
journalctl -u faceidbot -f
```

Endi bot server o'chib-yonsa ham avtomatik qayta ishga tushadi — 24/7.

> **Eslatma:** FaceID qurilma lokal tarmoqda (masalan 192.168.x.x) bo'lsa,
> bulutli server unga ulanolmaydi. Bu holda botni **ofisdagi doim yoniq
> kompyuter** yoki **Raspberry Pi** da ishga tushiring (yuqoridagi systemd
> qadamlari Ubuntu'da bir xil). Yoki qurilmaga tashqaridan kirish uchun
> "port forwarding" / VPN sozlang.

---

## 6. Boshqa bepul variantlar

- **Ofisdagi kompyuter / Raspberry Pi** — qurilma lokal tarmoqda bo'lsa eng qulay.
  Ubuntu'da yuqoridagi systemd bilan bir xil ishlaydi.
- **Railway / Render / Fly.io** — bepul tariflari bor, lekin lokal FaceID
  qurilmaga ulana olmaydi (faqat internetdagi API uchun).

---

## 7. Ko'p uchraydigan savollar

**Kechikishni ba'zi xodimga hisoblamaslik?**
Admin → Xodimlar → xodim → "Kechikish hisoblanmaydi" tugmasi.

**Ish grafigini o'zgartirish?**
Admin → Xodimlar → xodim → 🕐 Ish grafigi.

**Kechikishga imtiyoz (masalan 5 daqiqa kechiksa hisoblanmasin)?**
`.env` da `GRACE_MINUTES=5`.

**Baza qayerda?**
`faceid_bot.db` fayli (SQLite). Zaxira uchun shu faylni nusxalab qo'ying.
