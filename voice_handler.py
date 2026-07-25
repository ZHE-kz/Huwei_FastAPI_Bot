import os
import httpx
from fastapi import APIRouter, Request, BackgroundTasks
from voice_service import split_text_gracefully, generate_tts_audio_bytes
from drive_service import upload_audio_bytes_to_drive

router = APIRouter()
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")

@router.post("/callback/voice")
async def handle_voice_postback(request: Request, background_tasks: BackgroundTasks):
    """
    接收 LINE 的 Postback 事件（當遊客點擊「🔊 聆聽語音導覽」或「繼續聽下一段」時觸發）
    """
    body = await request.json()
    events = body.get("events", [])
    
    for event in events:
        if event.get("type") == "postback":
            reply_token = event.get("replyToken")
            user_id = event.get("source", {}).get("userId")
            data_str = event.get("postback", {}).get("data", "")
            
            # 解析 postback 帶的參數 (例如 action=play_tts&text=...)
            params = dict(item.split("=") for item in data_str.split("&") if "=" in item)
            
            if params.get("action") == "play_tts":
                full_text = params.get("text", "歡迎來到虎尾！")
                
                # 1. ✂️ 使用我們寫好的優雅斷句，切出前 120 字與剩下的部分
                current_chunk, remaining_text = split_text_gracefully(full_text)
                
                # 2. 🚀 呼叫 Modal GPU 產生語音 Bytes
                audio_bytes = await generate_tts_audio_bytes(current_chunk)
                
                if audio_bytes:
                    # 3. ☁️ 將語音 Bytes 上傳到 Google Drive 拿公開網址
                    audio_url = upload_audio_bytes_to_drive(audio_bytes)
                    
                    if audio_url:
                        # 4. 📦 準備回傳給 LINE 的訊息結構
                        messages = [
                            {"type": "text", "text": f"🎧 導遊語音導覽：\n{current_chunk}"},
                            {"type": "audio", "originalContentUrl": audio_url, "duration": 5000}
                        ]
                        
                        # 如果還有故事沒講完，動態掛上「繼續聽」的 Quick Reply 按鈕！
                        if remaining_text:
                            # 為了避免網址太長，這裡可以把剩下的文字暫存到 Firestore 或 Cache，
                            # 或是透過加密/簡短 ID 傳遞。這裡以簡化邏輯呈現：
                            messages[1]["quickReply"] = {
                                "items": [{
                                    "type": "action",
                                    "action": {
                                        "type": "postback",
                                        "label": "🔊 繼續聽下一段故事",
                                        "data": f"action=play_tts&text={remaining_text}",
                                        "displayText": "我想繼續聽故事！"
                                    }
                                }]
                            }
                        
                        # 5. 發送給 LINE
                        await send_line_message_async(reply_token, messages)
                        return {"status": "OK"}
                        
    return {"status": "Ignored"}


async def send_line_message_async(reply_token: str, messages: list):
    """非同步發送訊息給 LINE"""
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": messages
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=10.0)
        print("LINE audio reply status:", response.status_code, response.text)