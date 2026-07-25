from datetime import datetime, timedelta
from typing import List
from firestore_client import get_db

# 預設白名單快取 (包含失效時間)[cite: 7]
_whitelist_cache = {
    "data": "虎尾驛, 虎尾糖廠, 虎尾鐵橋, 雲林布袋戲館, 雲林故事館",
    "expire_time": datetime.min,
}

def fetch_whitelist_sync() -> str:
    """從 ItineraryDB 抓取白名單並更新快取"""
    global _whitelist_cache
    now = datetime.now()

    # 如果快取還沒過期，直接回傳[cite: 7]
    if now < _whitelist_cache["expire_time"]:
        print("⚡ [快取] 光速讀取白名單，不須連線 Firestore")
        return _whitelist_cache["data"]

    try:
        db = get_db()
        docs = db.collection("ItineraryDB").stream()
        items: List[str] = []
        for doc in docs:
            data = doc.to_dict() or {}
            name = data.get("placeName", "未知景點")
            category = data.get("category", "未分類")
            duration = data.get("duration", "未知")
            feature = data.get("feature", "無特色說明")
            opening = data.get("openingHours", "營業時間未提供")
            items.append(
                f"- {name} (類別: {category}, 停留時間: {duration}, 特色: {feature}, 營業時間: {opening})"
            )

        result = "\n".join(items) if items else "目前無可用白名單資料"

        # 更新快取，設定 12 小時過期[cite: 7]
        _whitelist_cache["data"] = result
        _whitelist_cache["expire_time"] = now + timedelta(hours=12)
        print("☁️ [更新] 已從 Firestore 重新抓取白名單並存入快取")

        return result

    except Exception as e:
        print(f"🚨 Firestore 讀取白名單失敗: {e}")
        # 失敗時回傳舊快取或預設值[cite: 7]
        return _whitelist_cache["data"] 

def force_clear_whitelist_cache():
    """強制清空快取 (觸發重新連線)[cite: 7]"""
    global _whitelist_cache
    _whitelist_cache["expire_time"] = datetime.min
    print("🗑️ [清空] 白名單快取已強制清除")