from datetime import datetime, timedelta
from typing import List
import httpx


ARCHIVE_LOCATIONS_URL = "https://nfu-digital-archive.zheforge.com/api/locations"

# 預設白名單快取 (包含失效時間)[cite: 7]
_whitelist_cache = {
    "data": "虎尾驛, 虎尾糖廠, 虎尾鐵橋, 雲林布袋戲館, 雲林故事館",
    "expire_time": datetime.min,
}

def fetch_whitelist_sync() -> str:
    """從虎尾地方記憶地圖抓取白名單並更新快取"""
    global _whitelist_cache
    now = datetime.now()

    # 如果快取還沒過期，直接回傳[cite: 7]
    if now < _whitelist_cache["expire_time"]:
        print("⚡ [快取] 光速讀取白名單，不須連線 Firestore")
        return _whitelist_cache["data"]

    try:
        response = httpx.get(ARCHIVE_LOCATIONS_URL, timeout=10.0)
        response.raise_for_status()
        locations = response.json().get("locations", [])
        items: List[str] = []
        for location in locations:
            name = str(location.get("title", "")).strip()
            if not name:
                continue
            category = str(location.get("category") or "地方記憶").strip()
            feature = " ".join(str(location.get("summary") or "地方記憶地圖地點").split())[:300]
            latitude = location.get("latitude")
            longitude = location.get("longitude")
            coordinates = f", 座標: {latitude},{longitude}" if latitude is not None and longitude is not None else ""
            items.append(
                f"- {name} (類別: {category}, 特色: {feature}{coordinates})"
            )

        if not items:
            raise ValueError("虎尾地方記憶地圖沒有可用地點")
        result = "\n".join(items)

        # 更新快取，設定 12 小時過期[cite: 7]
        _whitelist_cache["data"] = result
        _whitelist_cache["expire_time"] = now + timedelta(hours=12)
        print("☁️ [更新] 已從虎尾地方記憶地圖重新抓取白名單並存入快取")

        return result

    except Exception as e:
        print(f"🚨 數位典藏館讀取白名單失敗: {e}")
        # 失敗時回傳舊快取或預設值[cite: 7]
        return _whitelist_cache["data"] 

def force_clear_whitelist_cache():
    """強制清空快取 (觸發重新連線)[cite: 7]"""
    global _whitelist_cache
    _whitelist_cache["expire_time"] = datetime.min
    print("🗑️ [清空] 白名單快取已強制清除")