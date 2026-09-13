"""
BIR MARTALIK LOGIN — SESSION_STRING olish uchun.
Buni O'Z KOMPYUTERINGIZDA ishga tushiring (serverda emas).

Ishga tushirish:
    pip install telethon
    python login.py

So'raydi: api_id, api_hash, telefon raqam, Telegramga kelgan kod (va agar
ikki bosqichli parol bo'lsa — parol). Oxirida SESSION_STRING chiqadi —
uni nusxalab, Railway Variables ga SESSION_STRING nomi bilan qo'yasiz.
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

print("=== FaceID userbot login ===\n")
api_id = int(input("api_id ni kiriting: ").strip())
api_hash = input("api_hash ni kiriting: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    session_str = client.session.save()
    print("\n=========== SESSION_STRING (nusxalang) ===========\n")
    print(session_str)
    print("\n==================================================\n")

    print("Sizning guruhlaringiz (GROUP_ID uchun kerak bo'lsa):\n")
    try:
        for d in client.iter_dialogs():
            if getattr(d, "is_group", False) or getattr(d, "is_channel", False):
                print(f"  {d.id}  -  {d.name}")
    except Exception as e:
        print("  (guruhlar ro'yxatini olishda xatolik:", e, ")")

    print("\nTayyor! Yuqoridagi SESSION_STRING ni Railway Variables ga qo'ying.")
