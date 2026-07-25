import os
import time
import httpx

LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")

# 💡 簡易的記憶體快取字典（用來暫存完整文字，讓 Quick Reply 的按鈕 data 不會過長）
_tts_text_cache = {}

def store_tts_text(full_text: str) -> str:
    """將完整導覽文字存入快取，並回傳一個短代碼 (tts_id)"""
    tts_id = f"tts_{int(time.time() * 1000)}"
    _tts_text_cache[tts_id] = full_text
    
    # 簡單防呆：如果快取太大，清掉最舊的幾筆（正式上雲端也可以改用 Redis 或 Firestore）
    if len(_tts_text_cache) > 500:
        oldest_keys = list(_tts_text_cache.keys())[:100]
        for k in oldest_keys:
            _tts_text_cache.pop(k, None)
            
    return tts_id

def get_cached_tts_text(tts_id: str) -> str:
    """根據 tts_id 從快取中把完整文字拿出來"""
    return _tts_text_cache.get(tts_id, "")


async def send_text_with_audio_quick_reply(reply_token: str, ai_text: str):
    """
    💬 發送一般純文字回覆，並在下方掛上「🔊 聆聽語音導覽」按鈕
    """
    if not reply_token:
        print("🚨 [Error] replyToken 是空的，無法發送 LINE 訊息！")
        return

    # 1. 先把完整文字存起來拿到 id
    tts_id = store_tts_text(ai_text)

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    
    # 2. 建立 LINE Quick Reply 按鈕結構
    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": ai_text,
                "quickReply": {
                    "items": [
                        {
                            "type": "action",
                            "action": {
                                "type": "postback",
                                "label": "🔊 聆聽語音導覽",
                                "data": f"action=play_tts&tts_id={tts_id}",
                                "displayText": "我想聽這段語音導覽"
                            }
                        }
                    ]
                }
            }
        ]
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            print("LINE text with quick reply status:", response.status_code, response.text)
        except Exception as e:
            print(f"🚨 發送帶語音按鈕的文字失敗: {e}")