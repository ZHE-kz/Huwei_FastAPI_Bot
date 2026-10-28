import asyncio
import hashlib
import re
from datetime import datetime, timezone

import httpx
from google.cloud import firestore

from firestore_client import get_db


BEACON_COLLECTION = "LineBeacons"
COOLDOWN_COLLECTION = "LineBeaconCooldowns"
BEACON_EVENT_TYPES = {"enter", "leave", "banner"}


def parse_beacon_event(event):
    if event.get("type") != "beacon":
        return None
    beacon = event.get("beacon") or {}
    hwid = str(beacon.get("hwid", "")).strip()
    event_type = str(beacon.get("type", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", hwid):
        return None
    if event_type not in BEACON_EVENT_TYPES:
        return None
    return hwid, event_type


def normalize_beacon_config(data):
    data = data or {}
    place_name = str(data.get("place_name", "")).strip()[:100]
    cooldown_seconds = data.get("cooldown_seconds", 300)
    try:
        cooldown_seconds = max(0, min(int(cooldown_seconds), 86400))
    except (TypeError, ValueError):
        cooldown_seconds = 300
    return {
        "enabled": data.get("enabled") is True,
        "place_name": place_name,
        "message": str(data.get("message", "")).strip()[:2000],
        "enter_message": str(data.get("enter_message", "")).strip()[:2000],
        "leave_message": str(data.get("leave_message", "")).strip()[:2000],
        "banner_message": str(data.get("banner_message", "")).strip()[:2000],
        "cooldown_seconds": cooldown_seconds,
    }


def build_beacon_message(config, event_type):
    event_message = config.get(f"{event_type}_message", "")
    if event_message:
        return event_message
    if config["message"]:
        return config["message"]
    place_name = config["place_name"] or "此地點"
    if event_type == "leave":
        return f"你已離開「{place_name}」。"
    if event_type == "banner":
        return f"你正在「{place_name}」附近。"
    return f"你已抵達「{place_name}」！"


def cooldown_document_id(account_id, user_id, hwid, event_type):
    value = f"{account_id}\0{user_id}\0{hwid}\0{event_type}".encode()
    return hashlib.sha256(value).hexdigest()


def is_within_cooldown(last_sent_at, now, cooldown_seconds):
    return bool(
        last_sent_at
        and (now - last_sent_at).total_seconds() < cooldown_seconds
    )


def claim_notification(db, document_id, cooldown_seconds, now):
    reference = db.collection(COOLDOWN_COLLECTION).document(document_id)
    transaction = db.transaction()

    @firestore.transactional
    def claim(current_transaction):
        snapshot = reference.get(transaction=current_transaction)
        if snapshot.exists:
            last_sent_at = (snapshot.to_dict() or {}).get("last_sent_at")
            if is_within_cooldown(last_sent_at, now, cooldown_seconds):
                return False
        current_transaction.set(reference, {"last_sent_at": now})
        return True

    return claim(transaction)


async def process_beacon_event(event, line_token, account_id="default"):
    parsed = parse_beacon_event(event)
    if parsed is None:
        return False
    hwid, event_type = parsed
    user_id = str((event.get("source") or {}).get("userId", "")).strip()
    reply_token = str(event.get("replyToken", "")).strip()
    if not user_id or not reply_token:
        return True

    db = get_db()
    snapshot = await asyncio.to_thread(
        db.collection(BEACON_COLLECTION).document(hwid).get
    )
    if not snapshot.exists:
        return True
    config = normalize_beacon_config(snapshot.to_dict())
    if not config["enabled"]:
        return True

    document_id = cooldown_document_id(account_id, user_id, hwid, event_type)
    now = datetime.now(timezone.utc)
    claimed = await asyncio.to_thread(
        claim_notification,
        db,
        document_id,
        config["cooldown_seconds"],
        now,
    )
    if not claimed:
        return True

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={"Authorization": f"Bearer {line_token}"},
            json={
                "replyToken": reply_token,
                "messages": [
                    {"type": "text", "text": build_beacon_message(config, event_type)}
                ],
            },
        )
    if response.status_code != 200:
        print(f"[BEACON] LINE 回覆失敗: {response.status_code}")
    return True
