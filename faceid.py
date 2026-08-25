"""
FaceID qurilma bilan bog'lanish.

Qurilmalar har xil (Hikvision, ZKTeco, boshqa). Shuning uchun bu yerda
UNIVERSAL interfeys bor. FACEID_MODE orqali rejim tanlanadi:

  mock      -> test uchun soxta hodisalar (qurilmasiz sinash)
  generic   -> oddiy JSON API (o'zingiz sozlaysiz)
  hikvision -> Hikvision ISAPI namunasi

Har bir client fetch_events(since) -> list[Event] qaytaradi.
Event: dict -> {external_id, faceid_user_id, ts(datetime), event_type('in'|'out'|None)}
"""
import datetime as dt
import aiohttp
import db
from config import (FACEID_MODE, FACEID_API_URL, FACEID_API_TOKEN,
                    FACEID_API_USER, FACEID_API_PASS, FACEID_POLL_INTERVAL, TZ)


# ---------------- MOCK (test uchun) ----------------
class MockFaceIDClient:
    """Qurilma bo'lmasa ham botni sinash uchun. Hech narsa qaytarmaydi."""
    async def fetch_events(self, since: dt.datetime):
        return []


# ---------------- GENERIC JSON API ----------------
class GenericFaceIDClient:
    """
    Oddiy JSON API uchun. Sizning API'ingiz quyidagicha ro'yxat qaytaradi deb faraz qilamiz:
    [
      {"id": "1023", "user_id": "5", "time": "2026-08-16T08:05:03", "direction": "in"},
      ...
    ]
    Agar sizning API boshqacha bo'lsa — pastdagi _parse() ni moslashtiring.
    """
    def __init__(self, url, token=""):
        self.url = url
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _parse(self, item):
        ext = str(item.get("id") or item.get("event_id") or "")
        uid = str(item.get("user_id") or item.get("employee_no") or item.get("person_id") or "")
        raw_time = item.get("time") or item.get("timestamp") or item.get("dateTime")
        ts = dt.datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=TZ)
        ts = ts.astimezone(TZ)
        direction = item.get("direction") or item.get("event_type")
        etype = None
        if direction:
            d = str(direction).lower()
            if d in ("in", "entry", "check-in", "1"):
                etype = "in"
            elif d in ("out", "exit", "check-out", "0"):
                etype = "out"
        if not ext:
            ext = f"{uid}-{ts.isoformat()}"
        return {"external_id": ext, "faceid_user_id": uid, "ts": ts, "event_type": etype}

    async def fetch_events(self, since: dt.datetime):
        params = {"since": since.isoformat()}
        async with aiohttp.ClientSession(headers=self.headers) as s:
            async with s.get(self.url, params=params, timeout=20) as r:
                r.raise_for_status()
                data = await r.json()
        items = data if isinstance(data, list) else data.get("data", data.get("events", []))
        out = []
        for it in items:
            try:
                out.append(self._parse(it))
            except Exception:
                continue
        return out


# ---------------- HIKVISION ISAPI (namuna) ----------------
class HikvisionFaceIDClient:
    """
    Hikvision qurilmalari uchun namuna (ISAPI AcsEvent).
    Digest auth ishlatiladi. FACEID_API_URL = http://192.168.1.64 kabi bo'ladi.
    """
    def __init__(self, base, user, password):
        self.base = base.rstrip("/")
        self.auth = aiohttp.BasicAuth(user, password)

    async def fetch_events(self, since: dt.datetime):
        url = f"{self.base}/ISAPI/AccessControl/AcsEvent?format=json"
        payload = {
            "AcsEventCond": {
                "searchID": "1",
                "searchResultPosition": 0,
                "maxResults": 50,
                "major": 5, "minor": 0,
                "startTime": since.strftime("%Y-%m-%dT%H:%M:%S+05:00"),
                "endTime": dt.datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+05:00"),
            }
        }
        out = []
        try:
            async with aiohttp.ClientSession(auth=self.auth) as s:
                async with s.post(url, json=payload, timeout=20) as r:
                    r.raise_for_status()
                    data = await r.json()
            infos = data.get("AcsEvent", {}).get("InfoList", [])
            for it in infos:
                uid = str(it.get("employeeNoString") or it.get("employeeNo") or "")
                if not uid:
                    continue
                raw = it.get("time")
                ts = dt.datetime.fromisoformat(raw).astimezone(TZ)
                ext = str(it.get("serialNo") or f"{uid}-{raw}")
                # Hikvision'da yo'nalish har doim aniq bo'lavermaydi -> None (avto aniqlanadi)
                out.append({"external_id": ext, "faceid_user_id": uid,
                            "ts": ts, "event_type": None})
        except Exception:
            pass
        return out


async def effective_settings():
    """Bazadagi sozlamalarni oladi; bo'lmasa .env dan (config) qiymatlarni oladi."""
    s = await db.get_settings_dict()
    return {
        "mode": s.get("faceid_mode", FACEID_MODE),
        "url": s.get("faceid_url", FACEID_API_URL),
        "token": s.get("faceid_token", FACEID_API_TOKEN),
        "user": s.get("faceid_user", FACEID_API_USER),
        "pass": s.get("faceid_pass", FACEID_API_PASS),
        "interval": int(s.get("faceid_interval", FACEID_POLL_INTERVAL) or FACEID_POLL_INTERVAL),
    }


async def build_client():
    """Har safar joriy sozlamalar bilan yangi client quradi."""
    s = await effective_settings()
    if s["mode"] == "generic":
        return GenericFaceIDClient(s["url"], s["token"]), s["interval"]
    if s["mode"] == "hikvision":
        return HikvisionFaceIDClient(s["url"], s["user"], s["pass"]), s["interval"]
    return MockFaceIDClient(), s["interval"]
