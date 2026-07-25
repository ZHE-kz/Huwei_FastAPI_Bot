# src/itinerary_processor.py
import json
import traceback
import hashlib
import asyncio
import urllib.parse  
import re
from typing import Optional
import httpx
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
import google.generativeai as genai

from firestore_client import get_db
from weather import fetch_weather_async, force_clear_weather_cache
from whitelist import fetch_whitelist_sync, force_clear_whitelist_cache
from ai_client import configure_gemini, generate_itinerary_async
from flex_builder import create_itinerary_flex, create_simple_location_flex
from config import PROMOTE_TO_DB_THRESHOLD

# 🌟 全域宣告模型
model = genai.GenerativeModel("gemini-2.5-flash")

# ==========================================
# ⚡ 記憶體暫存口袋 (0 延遲且不用讀資料庫)
# ==========================================
_latest_response_cache = {}

def set_user_cache(user_id: str, text: str):
    global _latest_response_cache
    if len(_latest_response_cache) > 500:
        _latest_response_cache.pop(next(iter(_latest_response_cache)))
    _latest_response_cache[user_id] = text

def get_user_cache(user_id: str) -> str:
    return _latest_response_cache.get(user_id, "歡迎來到虎尾，這裡有豐富的歷史與文化...")

# --- 輔助函式：觸發 LINE 官方聊天室載入動畫 ---
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

# --- 輔助函式：用來將資料庫查詢包裝給並行處理 ---
def fetch_best_examples_sync(db):
    best_examples = []
    try:
        stats_docs = db.collection("ItineraryStats").order_by("avg_score", direction=firestore.Query.DESCENDING).limit(3).stream()
        for sdoc in stats_docs:
            best_examples.append(sdoc.to_dict() or {})
    except Exception:
        pass
    
    if not best_examples:
        try:
            hist_docs = db.collection("ItineraryHistory").where("status", "==", "RATED").order_by("score", direction=firestore.Query.DESCENDING).limit(3).stream()
            for h in hist_docs:
                best_examples.append(h.to_dict() or {})
        except Exception:
            pass
    return best_examples


# ==========================================
# 🌟 模組一：智慧行程規劃 (雙模式切換版)
# ==========================================
async def process_itinerary(
    reply_token: str,
    user_id: str,
    user_text: str,
    line_token: str,
    gemini_key: str,
    cwa_key: str,
):
    # 🚀 一進來立刻觸發 LINE 思考中動畫，提升體驗感！
    await send_loading_animation(user_id, line_token, seconds=60)
    
    db = get_db()
    
    # 🌟 1. 閒聊與打招呼快速攔截 (Fast Path)
    casual_greetings = ["你好", "妳好", "哈囉", "嗨", "早安", "午安", "晚安", "hi", "hello"]
    if user_text.strip().lower() in casual_greetings:
        welcome_text = "汪汪！你好呀！我是你的虎尾專屬導遊。請問今天想去哪裡走走，還是需要我為你推薦什麼特色景點呢？✨"
        
        # ⚡ 記入口袋
        set_user_cache(user_id, welcome_text)

        reply_payload = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": welcome_text,
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
            ],
        }
        async with httpx.AsyncClient() as client:
            line_url = "https://api.line.me/v2/bot/message/reply"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {line_token}"}
            await client.post(line_url, headers=headers, json=reply_payload, timeout=10.0)
        return

    # 🔊 播放語音指令快速攔截 (直接從記憶體 0 延遲抓取)
    if user_text.strip() == "播放語音":
        target_text = get_user_cache(user_id)

        # 呼叫 voice_service 取得音檔 bytes
        from voice_service import generate_tts_audio_bytes
        audio_bytes = await generate_tts_audio_bytes(target_text)

        audio_url = ""
        if audio_bytes:
            try:
                import uuid
                file_name = f"tts_audio_{user_id}_{uuid.uuid4().hex[:6]}.mp3"
                
                # 🌟 改用 uguu.se 免費直連上傳 API
                files = {'files[]': (file_name, audio_bytes, 'audio/mpeg')}
                
                async with httpx.AsyncClient() as client:
                    response = await client.post("https://uguu.se/upload.php", files=files, timeout=30.0)
                    
                    if response.status_code == 200:
                        try:
                            res_json = response.json()
                            if res_json.get("success"):
                                files_data = res_json.get("files", [])
                                if files_data:
                                    audio_url = files_data[0].get("url", "")
                        except Exception as parse_err:
                            print(f"🚨 解析 uguu JSON 失敗: {parse_err}")
            except Exception as e:
                print(f"🚨 上傳語音過程發生例外:\n{e}")

        # 直接透過免費的 Reply API 一次性回覆給使用者！
        if audio_url:
            reply_payload = {
                "replyToken": reply_token,
                "messages": [
                    {
                        "type": "audio",
                        "originalContentUrl": audio_url,
                        "duration": 15000
                    },
                    {
                        "type": "text",
                        "text": f"🔗 如果上面語音條播不出來，請點擊下方連結直接線上聽：\n{audio_url}"
                    }
                ],
            }
        else:
            reply_payload = {
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": "🔊 語音生成發生了一點小狀況，請再試一次！"}]
            }

        async with httpx.AsyncClient() as client:
            line_url = "https://api.line.me/v2/bot/message/reply"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {line_token}"}
            res = await client.post(line_url, headers=headers, json=reply_payload, timeout=30.0)
            print(f"✅免費 Reply 語音回覆結果: {res.status_code} - {res.text}")
        return

    # 🕵️‍♂️ 管理員隱藏密語攔截 (清空快取)
    if user_text.strip() == "助理更新大腦":
        force_clear_weather_cache()
        force_clear_whitelist_cache()
        reply_payload = {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": "任務完成！已為您強制清空快取，現在大腦是最新狀態囉！😎✨"}]
        }
        async with httpx.AsyncClient() as client:
            line_url = "https://api.line.me/v2/bot/message/reply"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {line_token}"}
            await client.post(line_url, headers=headers, json=reply_payload)
        return
       
    # 🌟 取得台灣當下時間
    tw_tz = timezone(timedelta(hours=8))
    current_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M")
    current_day = datetime.now(tw_tz).strftime("%A")

    # 🚀 並行處理
    async with httpx.AsyncClient() as client:
        weather_task = fetch_weather_async(client, cwa_key)
        whitelist_task = asyncio.to_thread(fetch_whitelist_sync)
        examples_task = asyncio.to_thread(fetch_best_examples_sync, db)
        
        weather, whitelist, best_examples = await asyncio.gather(
            weather_task, whitelist_task, examples_task
        )

    history_context = ""
    if best_examples:
        history_context = "\n[High Rated Examples]\nUse these as style reference.\n"
        for it in best_examples:
            stops = it.get("stops") or it.get("example_stops") or []
            title = it.get("title") or it.get("example_title") or "Untitled"
            history_context += f"- Title: {title}\n  Stops: {json.dumps(stops, ensure_ascii=False)}\n"

    # 🧠 三模式 AI 判斷 Prompt
    prompt = (
        "[Role] Huwei Tour Guide Agent (Professional, Friendly & Strategic)\n"
        f"{history_context}"
        "[Crucial Context]\n"
        f"- Current Time: {current_time} ({current_day})\n"
        f"- Weather: {weather}\n\n"
        "[Rules]\n"
        "1. WHITELIST ONLY: For itineraries or locations, you must ONLY use places provided in the [Whitelist Database].\n"
        "2. INTENT DETECTION:\n"
        "   - If user is just greeting, chatting, or asking casual questions (e.g., '你好', '早安', '你是誰'), choose CHAT and reply warmly in traditional Chinese.\n"
        "   - If user asks for a trip, route, or multiple places, choose ITINERARY.\n"
        "   - If user asks for a single place recommendation, choose LOCATION.\n"
        "3. Output raw JSON only.\n\n"
        f"[Query] {user_text}\n"
        f"[Whitelist Database]\n{whitelist}\n"
        "[Format]\n"
        "You MUST strictly output ONE of the following JSON structures based on intent:\n\n"
        "IF CHAT:\n"
        '{"type":"chat","text":"[Your friendly conversational response]"}\n\n'
        "IF ITINERARY:\n"
        '{"type":"itinerary","title":"...","total_distance":"...","stops":[{"time":"HH:MM","location":"...","note":"..."}]}\n\n'
        "IF LOCATION:\n"
        '{"type":"location","name":"[Place Name]","category":"...","time":"[Opening hours]","description":"[A rich, friendly description]"}'
    )

    configure_gemini(gemini_key)
    raw = await generate_itinerary_async(prompt)
    ai_json = raw.strip()
    
    # 清除 Markdown 反引號
    backticks = chr(96) * 3
    if ai_json.startswith(backticks + "json"):
        ai_json = ai_json[7:]
    elif ai_json.startswith(backticks):
        ai_json = ai_json[3:]
    if ai_json.endswith(backticks):
        ai_json = ai_json[:-3]
    ai_json = ai_json.strip()

    json_match = re.search(r'\{.*\}', ai_json, re.DOTALL)
    if json_match:
        ai_json = json_match.group(0)

    try:
        parsed = json.loads(ai_json, strict=False)
        parsed["weather_summary"] = weather
        intent_type = str(parsed.get("type", "")).lower()
        
        if intent_type == "location":
            parsed["type"] = "location"
            if not parsed.get("name"): parsed["name"] = "精選推薦景點"
        elif intent_type == "chat":
            parsed["type"] = "chat"
        else:
            parsed["type"] = "itinerary"
            if not parsed.get("title"): parsed["title"] = "在地精選深度遊"
    except Exception as e:
        print(f"JSON 解析失敗: {e}\n原始字串: {ai_json}")
        parsed = {
            "type": "itinerary",
            "title": "虎尾特色導覽行程",
            "stops": [],
            "total_distance": "依地圖導航為主",
            "weather_summary": weather
        }

    # 產生語音朗讀文本並存入記憶體快取
    intent_type = str(parsed.get("type", "")).lower()
    if intent_type == "chat":
        tts_cache_text = parsed.get("text", "哈囉！請問今天想去虎尾哪裡玩呢？")
    elif intent_type == "location":
        tts_cache_text = f"為您介紹 {parsed.get('name')}。{parsed.get('description')}"
    else:
        stops_list = parsed.get("stops", [])
        stops_str = "、".join([s.get("location", "") for s in stops_list])
        tts_cache_text = f"為您規劃的行程是 {parsed.get('title')}。途經景點包含：{stops_str}。"

    # ⚡ 瞬間存入口袋！
    set_user_cache(user_id, tts_cache_text)

    # 寫入歷史紀錄 (保留背景記錄，但不影響語音速度)
    hist_ref = db.collection("ItineraryHistory").document()
    itinerary_id = hist_ref.id
    try:
        payload_doc = {
            "user_id": user_id,
            "query": user_text,
            "raw_ai_response": ai_json,
            "status": "READY",
            "created_at": datetime.utcnow(),
            "weather": weather,
        }
        if parsed:
            payload_doc["full_itinerary"] = parsed
        hist_ref.set(payload_doc, merge=True)
    except Exception:
        traceback.print_exc()

    # 發送 LINE 訊息
    if parsed:
        if intent_type == "chat":
            reply_payload = {
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": tts_cache_text}],
            }
        elif intent_type == "location":
            location_name = parsed.get("name")
            db_data = None
            if location_name:
                try:
                    doc_ref = db.collection("ItineraryDB").document(location_name)
                    doc = doc_ref.get()
                    if doc.exists:
                        db_data = doc.to_dict()
                except Exception as e:
                    print(f"讀取單點資料庫失敗: {e}")
            
            flex = create_simple_location_flex(parsed, weather, db_data)
            alt_text = f"💡 為您推薦：{parsed.get('name')}"
            reply_payload = {
                "replyToken": reply_token,
                "messages": [{"type": "flex", "altText": alt_text, "contents": flex}],
            }
        else:
            flex = create_itinerary_flex(db, parsed, itinerary_id, weather)
            alt_text = "🗺️ 已為你產生推薦行程"
            reply_payload = {
                "replyToken": reply_token,
                "messages": [{"type": "flex", "altText": alt_text, "contents": flex}],
            }
    else:
        reply_payload = {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": f"不好意思，導遊剛剛恍神了，請再對我說一次你想去哪裡？"}],
        }

    async with httpx.AsyncClient() as client:
        line_url = "https://api.line.me/v2/bot/message/reply"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {line_token}"}
        r = await client.post(line_url, headers=headers, json=reply_payload, timeout=10.0)
        print("LINE reply status:", r.status_code, r.text)


# ==========================================
# 🌟 模組二：滿血圖片辨識 (加入記憶體快取)
# ==========================================
async def process_image_identification(image_bytes, user_id):
    """動態從 Firestore 抓取白名單與知識庫，進行視覺辨識與導覽生成"""
    db = get_db()
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    
    whitelist_places = []
    try:
        docs = db.collection("KnowledgeDB").stream()
        whitelist_places = [doc.id for doc in docs]
    except Exception as e:
        print("抓取白名單失敗:", e)
        whitelist_places = ["虎尾驛", "虎尾糖廠", "虎尾鐵橋", "雲林布袋戲館", "雲林故事館"]
    whitelist_places.sort(key=len, reverse=True)
    places_str = "\n    - ".join(whitelist_places) if whitelist_places else "無可用白名單"

    prompt = f"""請仔細觀察這張圖片中的建築、招牌、街景、文字與空間特徵。
    
    我們有一個「專屬景點白名單」：
    - {places_str}
    
    請你扮演極度嚴格的鑑定官：
    1. 判斷這張照片是否明確屬於上述白名單中的「某一個地點」。
    2. 如果非常確定，請在第一行直接且只能輸出：「鑑定結果：[地點名稱]」。
    3. 如果只是普通街景、特徵不足、或不在白名單內，請在第一行輸出：「鑑定結果：未知地點」。
    4. 第二行開始，請用繁體中文詳細描述你看到了什麼特徵，以及你的判斷依據。
    """
    
    response = model.generate_content([
        prompt,
        {"mime_type": "image/jpeg", "data": image_bytes}
    ])
    visual_text = response.text
    
    best_place = "未知地點"
    if "鑑定結果：" in visual_text:
        first_line = visual_text.split("\n")[0]
        inferred_place = first_line.replace("鑑定結果：", "").strip()
        for valid_place in whitelist_places:
            if valid_place in inferred_place:
                best_place = valid_place
                break

    if best_place == "未知地點":
        observation = visual_text.replace("鑑定結果：未知地點", "").strip()
        ai_response_text = f"哎呀，我判斷不出來這是哪裡，或者該景點的「資料庫尚未建立」哦！\n\n🔍 導遊的觀察筆記：\n{observation}"
        
        # ⚡ 存入口袋
        set_user_cache(user_id, ai_response_text)
        
        return {
            "aiResponse": ai_response_text,
            "locationName": "未知地點",
            "hash": image_hash,
            "visualText": visual_text,
            "needsConfirmation": True
        }

    local_knowledge = "這是一個承載著在地記憶的獨特空間，非常值得前來細細品味。"
    try:
        doc_ref = db.collection("KnowledgeDB").document(best_place)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            context = data.get("context", "")
            speaker = data.get("speaker", "")
            category = data.get("category", "")
            local_knowledge = f"【類別】：{category}\n【詳細背景】：\n{context}"
            if speaker:
                local_knowledge += f"\n【資料來源/與談人】：{speaker}"
    except Exception as e:
        print(f"讀取 {best_place} 知識庫失敗:", e)

    intro_prompt = f"""你是一個專業、熱情的在地導遊。請根據以下關於「{best_place}」的歷史背景知識，為遊客寫一段生動、引人入勝的景點導覽介紹。
    
    ⚠️【最高限制原則】：
    1. 輸出的文字一定要精簡洗鍊，且內容要盡可能地還原資料庫的內容不要加過多的修飾
    2. 語氣要文青、親切，充滿故事感，讓人一聽就想深入探索。
    
    【景點背景知識】：
    {local_knowledge}
    """
    
    intro_response = model.generate_content(intro_prompt)
    
    easter_egg_plot = ""
    if best_place == "虎尾糖廠第一工場":
        easter_egg_plot = (
            "\n\n─── ⚠️ 系統異常：收到一則加密通訊 ───\n\n"
            "「滋...滋... 你好，我是壁虎。既然你來到了糖廠，看來你就是我要找的人。\n"
            "昨晚，虎尾糖廠珍貴的『黃金蔗糖配方』被偷走了！\n"
            "現場只留下了一串奇怪的腳印，一直延伸到旁邊的舊鐵橋...\n"
            "你願意幫我找回配方嗎？如果願意，請對我輸入：『壁虎我來幫忙』！」"
        )

    final_ai_text = f"我判斷這裡應該是「{best_place}」。\n\n{intro_response.text}{easter_egg_plot}"

    # ⚡ 完美將圖片辨識結果存入記憶體口袋，語音秒抓！
    set_user_cache(user_id, final_ai_text)

    return {
        "aiResponse": final_ai_text,
        "locationName": best_place,
        "hash": image_hash,
        "visualText": visual_text,
        "needsConfirmation": True
    }