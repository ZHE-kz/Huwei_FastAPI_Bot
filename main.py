import base64
import hashlib
import hmac
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import RedirectResponse
import httpx
from datetime import datetime
from admin_tools import record_deployment_changelog, router as puzzle_admin_router
from config import CWA_API_KEY, GEMINI_API_KEY, LINE_ACCESS_TOKEN, LINE_CHANNEL_SECRET
from itinerary_processor import process_image_identification, process_itinerary
from puzzle_core import process_puzzle_event, should_route_to_puzzle
from firestore_client import get_db
from maps import build_itinerary_google_map_url

@asynccontextmanager
async def lifespan(_app):
    try:
        record_deployment_changelog()
    except Exception as error:
        print(f"[CHANGELOG] 自動建立部署日誌失敗: {error}")
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(puzzle_admin_router)

missing_env = [
    name
    for name, value in {
        "LINE_ACCESS_TOKEN": LINE_ACCESS_TOKEN,
        "LINE_CHANNEL_SECRET": LINE_CHANNEL_SECRET,
        "GEMINI_API_KEY": GEMINI_API_KEY,
    }.items()
    if not value
]
if missing_env:
    raise RuntimeError(f"缺少必要環境變數: {', '.join(missing_env)}")
async def send_loading_animation(user_id: str, line_token: str, seconds: int = 60):
    """觸發 LINE 官方的聊天室載入動畫"""
    url = "https://api.line.me/v2/bot/chat/loading/start"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {line_token}"
    }
    payload = {
        "chatId": user_id,       
        "loadingSeconds": seconds 
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, headers=headers, json=payload, timeout=5.0)
        except Exception as e:
            print(f"觸發 Loading 動畫失敗: {e}")

async def background_task_router(payload: dict):
    """背景分發中心：處理所有耗時的 AI 任務"""
    print("🔥 [DEBUG 0] 成功進入 background_task_router 函式！")
    try:
        events = payload.get("events", [])
        if not events:
            return

        for idx, event in enumerate(events):
            reply_token = event.get("replyToken")
            source = event.get("source", {})
            user_id = source.get("userId")
            
            message = event.get("message", {})
            message_type = message.get("type")
            
            raw_text = message.get("text") if message_type == "text" else None
            user_text = raw_text.strip() if raw_text else ""

            if not reply_token or not user_id:
                continue

            await send_loading_animation(user_id, LINE_ACCESS_TOKEN, seconds=60)

            route_to_puzzle = await should_route_to_puzzle(user_id, user_text)
            puzzle_image = None
            if route_to_puzzle and message_type == "image" and message.get("id"):
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.get(
                        f"https://api-data.line.me/v2/bot/message/{message['id']}/content",
                        headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"},
                    )
                    response.raise_for_status()
                    puzzle_image = base64.b64encode(response.content).decode()

            if route_to_puzzle and await process_puzzle_event(
                reply_token=reply_token,
                user_id=user_id,
                user_text=user_text,
                message_id=message.get("id"),
                image_base64=puzzle_image,
                line_token=LINE_ACCESS_TOKEN,
                gemini_key=GEMINI_API_KEY,
            ):
                continue
            
            # 1. 處理圖片辨識
            if message_type == "image":
                message_id = message.get("id")
                if message_id:
                    try:
                        print(f"🖼️ 收到圖片訊息，正在向 LINE 下載圖片，Message ID: {message_id}")
                        # 使用系統 CA 驗證 LINE API HTTPS 憑證
                        async with httpx.AsyncClient() as client:
                            content_url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
                            headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
                            img_res = await client.get(content_url, headers=headers)
                            
                            if img_res.status_code == 200:
                                image_bytes = img_res.content
                                print(f"✅ 成功下載圖片，大小: {len(image_bytes)} bytes，準備進行辨識...")
                                
                                # 呼叫圖片辨識核心
                                result = await process_image_identification(
                                    image_bytes=image_bytes,
                                    user_id=user_id
                                )
                                
                                # 取得辨識後的文字並回傳給 LINE
                                ai_response_text = result.get("aiResponse", "辨識完成，但沒有回傳內容。")
                                
                                # 🌟【修復這裡】確實將圖片辨識結果存入歷史紀錄，讓語音抓得到！
                                try:
                                    db = get_db()
                                    hist_ref = db.collection("ItineraryHistory").document()
                                    hist_ref.set({
                                        "user_id": user_id,
                                        "query": "圖片辨識",
                                        "raw_ai_response": ai_response_text,
                                        "status": "READY",
                                        "created_at": datetime.utcnow(),
                                    })
                                except Exception as e:
                                    print(f"存入圖片辨識歷史紀錄失敗: {e}")
                                
                                line_url = "https://api.line.me/v2/bot/message/reply"
                                line_headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
                                reply_payload = {
                                    "replyToken": reply_token,
                                    "messages": [
                                        {
                                            "type": "text",
                                            "text": ai_response_text,
                                            "quickReply": {
                                                "items": [
                                                    {
                                                        "type": "action",
                                                        "action": {
                                                            "type": "message",
                                                            "label": "🔊 播放語音訊息",
                                                            "text": "播放語音"
                                                        }
                                                    }
                                                ]
                                            }
                                        }
                                    ]
                                }
                                res = await client.post(line_url, headers=line_headers, json=reply_payload)
                                print(f"🚀 圖片辨識結果回傳 LINE: {res.status_code} - {res.text}")
                            else:
                                print(f"🚨 下載 LINE 圖片失敗: {img_res.status_code} - {img_res.text}")
                    except Exception as e:
                        import traceback
                        print(f"🚨 圖片處理過程發生錯誤:\n{traceback.format_exc()}")
                continue

            # 2. 交給行程與一般導覽大腦
            await process_itinerary(
                reply_token,
                user_id,
                user_text,
                LINE_ACCESS_TOKEN,
                GEMINI_API_KEY,
                CWA_API_KEY,
            )

    except Exception as e:
        import traceback
        print(f"🚨 [DEBUG 崩潰] 抓到例外:\n{traceback.format_exc()}")

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/maps/route/{itinerary_id}")
async def itinerary_maps_route(itinerary_id: str):
    if len(itinerary_id) != 20 or not itinerary_id.isalnum():
        raise HTTPException(status_code=404, detail="Itinerary not found")

    document = get_db().collection("ItineraryHistory").document(itinerary_id).get()
    if not document.exists:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    stops = (document.to_dict().get("full_itinerary") or {}).get("stops") or []
    if not stops:
        raise HTTPException(status_code=404, detail="Itinerary has no stops")

    return RedirectResponse(build_itinerary_google_map_url(stops))


@app.post("/")
async def generate_itinerary_endpoint(request: Request, background_tasks: BackgroundTasks):
    """Webhook 接收端點"""
    try:
        body = await request.body()
        signature = request.headers.get("x-line-signature", "")
        expected_signature = base64.b64encode(
            hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
        ).decode()
        if not signature or not hmac.compare_digest(signature, expected_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

        payload = json.loads(body)
        if not payload:
            raise HTTPException(status_code=400, detail="Invalid Request")

        background_tasks.add_task(background_task_router, payload)
        return {"status": "Processing in background"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
