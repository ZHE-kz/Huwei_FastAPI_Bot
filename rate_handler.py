import traceback
from datetime import datetime
from typing import Any, Dict
import httpx

from config import PROMOTE_TO_DB_THRESHOLD
from firestore_client import get_db

def update_stats_transaction(transaction, stats_ref, hist_doc_snapshot, score_val: float):
    stats_doc = stats_ref.get(transaction=transaction)
    if stats_doc.exists:
        sdata = stats_doc.to_dict() or {}
        prev_avg = sdata.get("avg_score", 0.0) or 0.0
        prev_count = sdata.get("rating_count", 0) or 0
        new_count = prev_count + 1
        new_avg = (prev_avg * prev_count + score_val) / new_count
        transaction.update(
            stats_ref,
            {
                "avg_score": new_avg,
                "rating_count": new_count,
                "last_rated_at": datetime.utcnow(),
            },
        )
        return

    rep_title = ""
    rep_stops = []
    if hist_doc_snapshot and hist_doc_snapshot.exists:
        h = hist_doc_snapshot.to_dict() or {}
        rep_title = h.get("title", "")
        rep_stops = h.get("stops", [])

    transaction.set(
        stats_ref,
        {
            "avg_score": score_val,
            "rating_count": 1,
            "example_title": rep_title,
            "example_stops": rep_stops,
            "first_rated_at": datetime.utcnow(),
            "last_rated_at": datetime.utcnow(),
        },
    )

def handle_rate(
    itinerary_id: str,
    score_val: float,
    rater_id: str | None = None,
    reply_token: str | None = None,
    line_token: str | None = None,
) -> Dict[str, Any]:
    db = get_db()
    try:
        hist_ref = db.collection("ItineraryHistory").document(itinerary_id)
        hist_doc = hist_ref.get()
        
        # 🌟 防狂點機制：檢查是否已經評分過
        if hist_doc.exists and hist_doc.to_dict().get("status") == "RATED":
            print(f"⚠️ 行程 {itinerary_id} 已被評分過，攔截重複寫入！")
            # 已經評分過，直接回傳 OK，不要再去資料庫灌水
            if reply_token and line_token:
                _send_line_reply(reply_token, line_token, "你已經評分過這個行程囉，感謝你的熱情參與！")
            return {"status": "OK"}

        rating_doc = {
            "score": score_val,
            "status": "RATED",
            "rated_at": datetime.utcnow(),
            "rater_id": rater_id or "",
        }

        if hist_doc.exists:
            hist_ref.update(rating_doc)
        else:
            hist_ref.set(rating_doc)

        stats_ref = db.collection("ItineraryStats").document(itinerary_id)
        txn = db.transaction()

        def _txn_fun(transaction):
            update_stats_transaction(transaction, stats_ref, hist_doc, score_val)

        txn.call(_txn_fun)

        stats_doc = stats_ref.get()
        stats_data = stats_doc.to_dict() if stats_doc.exists else {}
        
        try:
            # 如果超過門檻，自動升級為公用行程資料庫[cite: 9]
            if stats_data and stats_data.get("avg_score", 0) >= PROMOTE_TO_DB_THRESHOLD:
                it_db_ref = db.collection("ItineraryDB").document(itinerary_id)
                it_db_ref.set(
                    {
                        "placeName": stats_data.get("example_title", f"熱門行程 {itinerary_id}"),
                        "imageUrl": "",
                        "category": "user_generated",
                        "duration": "依行程安排",
                        "feature": "這是由許多遊客高分推薦的優質行程喔！",
                        "updated_at": datetime.utcnow(),
                        "rating_avg": stats_data.get("avg_score"),
                        "rating_count": stats_data.get("rating_count"),
                        "stops_example": stats_data.get("example_stops", []),
                    },
                    merge=True,
                )
        except Exception:
            traceback.print_exc()

        if reply_token and line_token:
            _send_line_reply(reply_token, line_token, f"收到你的評價（{score_val} 星）！以後大腦會越排越好喔！")

        return {"status": "OK"}
    except Exception as e:
        print("評分寫入錯誤:", e)
        traceback.print_exc()
        return {"status": "ERROR", "error": str(e)}

def _send_line_reply(reply_token: str, line_token: str, text_content: str):
    """內部輔助函式：發送 LINE 文字回覆"""
    try:
        line_url = "https://api.line.me/v2/bot/message/reply"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_token}",
        }
        text_msg = {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text_content}],
        }
        r = httpx.post(line_url, headers=headers, json=text_msg, timeout=5.0)
        print("LINE rate reply status:", r.status_code, r.text)
    except Exception:
        traceback.print_exc()