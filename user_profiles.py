import asyncio
from datetime import datetime, timezone

import httpx
from config import get_line_account_credentials, get_rich_menu_id
from firestore_client import get_db
from liff_auth import LiffIdentity, owner_key


PROFILE_COLLECTION = "UserProfiles"
FAVORITE_COLLECTION = "UserFavorites"
SUPPORTED_LANGUAGES = {"zh-TW", "en-US", "ja-JP"}
DEFAULT_PREFERENCES = {
    "language": "zh-TW",
    "interests": [],
    "content_depth": "story",
    "preferred_duration": "1h",
    "transportation": "walking",
    "walking_preference": "medium",
    "stay_minutes": 60,
    "voice": {"speaker": "default", "speed": 1.0, "pitch": 0.0},
}


def _timestamp_sort_key(value) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value or "")


def profile_document_id(identity: LiffIdentity) -> str:
    return owner_key(identity.account_id, identity.user_id)


def normalize_preferences(data=None) -> dict:
    data = data or {}
    voice = data.get("voice") if isinstance(data.get("voice"), dict) else {}
    language = data.get("language", "zh-TW")
    if language not in SUPPORTED_LANGUAGES:
        language = "zh-TW"
    interests = data.get("interests") if isinstance(data.get("interests"), list) else []
    interests = [str(value).strip()[:50] for value in interests[:10] if str(value).strip()]
    content_depth = data.get("content_depth", "story")
    if content_depth not in {"quick", "story", "deep", "field"}:
        content_depth = "story"
    preferred_duration = data.get("preferred_duration", "1h")
    if preferred_duration not in {"30m", "1h", "half_day", "full_day"}:
        preferred_duration = "1h"
    walking = data.get("walking_preference", "medium")
    if walking not in {"low", "medium", "high"}:
        walking = "medium"
    transportation = data.get("transportation", "walking")
    if transportation not in {"walking", "bicycle", "transit", "driving"}:
        transportation = "walking"
    try:
        stay_minutes = max(15, min(int(data.get("stay_minutes", 60)), 480))
        speed = max(0.5, min(float(voice.get("speed", 1.0)), 2.0))
        pitch = max(-12.0, min(float(voice.get("pitch", 0.0)), 12.0))
    except (TypeError, ValueError):
        stay_minutes, speed, pitch = 60, 1.0, 0.0
    speaker = str(voice.get("speaker", "default")).strip()[:64] or "default"
    return {
        "language": language,
        "interests": interests,
        "content_depth": content_depth,
        "preferred_duration": preferred_duration,
        "transportation": transportation,
        "walking_preference": walking,
        "stay_minutes": stay_minutes,
        "voice": {"speaker": speaker, "speed": speed, "pitch": pitch},
    }


def get_profile(identity: LiffIdentity) -> dict:
    snapshot = get_db().collection(PROFILE_COLLECTION).document(profile_document_id(identity)).get()
    data = snapshot.to_dict() if snapshot.exists else {}
    return {
        "preferences": normalize_preferences((data or {}).get("preferences")),
        "created_at": (data or {}).get("created_at"),
        "updated_at": (data or {}).get("updated_at"),
    }


def save_preferences(identity: LiffIdentity, preferences: dict) -> dict:
    normalized = normalize_preferences(preferences)
    now = datetime.now(timezone.utc)
    get_db().collection(PROFILE_COLLECTION).document(profile_document_id(identity)).set(
        {
            "account_id": identity.account_id,
            "preferences": normalized,
            "created_at": now,
            "updated_at": now,
        },
        merge=True,
    )
    return normalized


def clear_preferences(identity: LiffIdentity) -> dict:
    return save_preferences(identity, DEFAULT_PREFERENCES)


def favorite_document_id(identity: LiffIdentity, place_id: str) -> str:
    return owner_key(identity.account_id, f"{identity.user_id}\0{place_id}")


def list_favorites(identity: LiffIdentity) -> list:
    key = profile_document_id(identity)
    documents = (
        get_db().collection(FAVORITE_COLLECTION)
        .where("owner_key", "==", key)
        .limit(100)
        .stream()
    )
    result = []
    for document in documents:
        data = document.to_dict() or {}
        result.append(
            {
                "id": document.id,
                "place_id": data.get("place_id", ""),
                "title": data.get("title", ""),
                "created_at": data.get("created_at"),
            }
        )
    return sorted(result, key=lambda item: _timestamp_sort_key(item.get("created_at")), reverse=True)


def add_favorite(identity: LiffIdentity, place_id: str, title: str = "") -> dict:
    data = {
        "owner_key": profile_document_id(identity),
        "account_id": identity.account_id,
        "place_id": place_id,
        "title": title,
        "created_at": datetime.now(timezone.utc),
    }
    get_db().collection(FAVORITE_COLLECTION).document(
        favorite_document_id(identity, place_id)
    ).set(data)
    return {
        "place_id": data["place_id"],
        "title": data["title"],
        "created_at": data["created_at"],
    }


def delete_favorite(identity: LiffIdentity, place_id: str):
    get_db().collection(FAVORITE_COLLECTION).document(
        favorite_document_id(identity, place_id)
    ).delete()


def clear_favorites(identity: LiffIdentity) -> int:
    documents = list_favorites(identity)
    for item in documents:
        delete_favorite(identity, item["place_id"])
    return len(documents)


def delete_profile(identity: LiffIdentity):
    get_db().collection(PROFILE_COLLECTION).document(profile_document_id(identity)).delete()


def list_history(identity: LiffIdentity) -> list:
    documents = (
        get_db().collection("ItineraryHistory")
        .where("user_id", "==", identity.user_id)
        .limit(100)
        .stream()
    )
    result = []
    for document in documents:
        data = document.to_dict() or {}
        stored_account = data.get("account_id", "default")
        if stored_account == identity.account_id:
            result.append(
                {
                    "id": document.id,
                    "query": data.get("query", ""),
                    "status": data.get("status", ""),
                    "full_itinerary": data.get("full_itinerary", ""),
                    "created_at": data.get("created_at"),
                }
            )
    return sorted(result, key=lambda item: _timestamp_sort_key(item.get("created_at")), reverse=True)


def clear_history(identity: LiffIdentity) -> int:
    documents = list_history(identity)
    for item in documents:
        get_db().collection("ItineraryHistory").document(item["id"]).delete()
    return len(documents)


def puzzle_state_document_id(identity: LiffIdentity) -> str:
    return identity.user_id if identity.account_id == "default" else profile_document_id(identity)


def get_puzzle_state(identity: LiffIdentity) -> dict:
    snapshot = get_db().collection("PuzzleState").document(puzzle_state_document_id(identity)).get()
    return snapshot.to_dict() if snapshot.exists else {}


def clear_puzzle_state(identity: LiffIdentity):
    get_db().collection("PuzzleState").document(puzzle_state_document_id(identity)).delete()


async def bind_rich_menu(identity: LiffIdentity, language: str):
    menu_id = get_rich_menu_id(identity.account_id, language)
    if not menu_id:
        return
    credentials = get_line_account_credentials(identity.account_id)
    if identity.account_id == "default":
        from config import LINE_ACCESS_TOKEN

        access_token = LINE_ACCESS_TOKEN
    elif credentials:
        _, access_token = credentials
    else:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"https://api.line.me/v2/bot/user/{identity.user_id}/richmenu/{menu_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code not in {200, 404}:
        print(f"[LIFF] Rich Menu 綁定失敗: {response.status_code}")


async def get_profile_async(identity: LiffIdentity) -> dict:
    return await asyncio.to_thread(get_profile, identity)
