# src/itinerary_processor.py
import json
import html
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
from prompt_store import render_prompt
from bot_i18n import gemini_language_instruction, text as i18n_text
from user_profiles import DEFAULT_PREFERENCES, get_profile, normalize_preferences
from account_links import get_login_identity
from line_messaging import fit_line_reply_payload

# 🌟 全域宣告模型
model = genai.GenerativeModel("gemini-2.5-flash")
ARCHIVE_ARTICLES_URL = "https://nfu-digital-archive.zheforge.com/api/articles?category=history"

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
    account_id: str = "default",
):
    # 🚀 一進來立刻觸發 LINE 思考中動畫，提升體驗感！
    await send_loading_animation(user_id, line_token, seconds=60)
    
    db = get_db()
    try:
        login_identity = await asyncio.to_thread(
            get_login_identity, account_id, user_id
        )
        if login_identity:
            profile = await asyncio.to_thread(get_profile, login_identity)
            preferences = normalize_preferences(profile.get("preferences"))
            has_saved_preferences = profile.get("updated_at") is not None
        else:
            preferences = normalize_preferences(DEFAULT_PREFERENCES)
            has_saved_preferences = False
    except Exception:
        preferences = normalize_preferences(DEFAULT_PREFERENCES)
        has_saved_preferences = False
    language = preferences["language"]
    
    # 🌟 1. 閒聊與打招呼快速攔截 (Fast Path)
    casual_greetings = ["你好", "妳好", "哈囉", "嗨", "早安", "午安", "晚安", "hi", "hello"]
    if user_text.strip().lower() in casual_greetings:
        welcome_text = i18n_text(language, "welcome")
        
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
            await client.post(line_url, headers=headers, json=fit_line_reply_payload(reply_payload), timeout=10.0)
        return

    # 🔊 播放語音指令快速攔截 (直接從記憶體 0 延遲抓取)
    if user_text.strip() == "播放語音":
        target_text = get_user_cache(user_id)

        from voice_service import get_http_client, get_or_create_tts_audio
        voice = preferences["voice"]
        audio_result = await get_or_create_tts_audio(
            target_text,
            speaker=voice["speaker"] if has_saved_preferences else None,
            speed=voice["speed"] if has_saved_preferences else None,
            pitch=voice["pitch"] if has_saved_preferences else None,
        )

        # 直接透過免費的 Reply API 一次性回覆給使用者！
        if audio_result:
            audio_url, duration_ms = audio_result
            reply_payload = {
                "replyToken": reply_token,
                "messages": [
                    {
                        "type": "audio",
                        "originalContentUrl": audio_url,
                        "duration": duration_ms
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
                "messages": [{"type": "text", "text": i18n_text(language, "tts_error")}]
            }

        client = get_http_client()
        line_url = "https://api.line.me/v2/bot/message/reply"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {line_token}"}
        res = await client.post(line_url, headers=headers, json=fit_line_reply_payload(reply_payload), timeout=30.0)
        print(f"✅ Reply 語音回覆狀態: {res.status_code}")
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
            await client.post(line_url, headers=headers, json=fit_line_reply_payload(reply_payload))
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

    preference_context = {
        "language": language,
        "interests": preferences["interests"],
        "content_depth": preferences["content_depth"],
        "preferred_duration": preferences["preferred_duration"],
        "transportation": preferences["transportation"],
        "walking_preference": preferences["walking_preference"],
        "preferred_stay_minutes": preferences["stay_minutes"],
    }
    history_context += (
        "\n[User Preferences]\n"
        + json.dumps(preference_context, ensure_ascii=False)
        + "\n"
        + gemini_language_instruction(language)
        + "\n"
    )

    # 🧠 三模式 AI 判斷 Prompt
    prompt = render_prompt(
        "itinerary",
        history_context=history_context,
        current_time=current_time,
        current_day=current_day,
        weather=weather,
        user_text=user_text,
        whitelist=whitelist,
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
            "account_id": account_id,
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
        r = await client.post(line_url, headers=headers, json=fit_line_reply_payload(reply_payload), timeout=10.0)
        print("LINE reply status:", r.status_code, r.text)


# ==========================================
# 🌟 模組二：滿血圖片辨識 (加入記憶體快取)
# ==========================================
def _build_recognition_context(articles):
    knowledge_by_place = {}
    aliases_by_place = {}
    recognition_lines = []

    for article in articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title", "")).strip()
        recognition = article.get("recognition")
        if not isinstance(recognition, dict) or not title or recognition.get("enabled") is not True:
            continue

        def clean_values(field, limit):
            values = recognition.get(field)
            if not isinstance(values, list):
                return []
            return [str(value).strip()[:200] for value in values[:limit] if str(value).strip()]

        aliases = clean_values("aliases", 10)
        sign_texts = clean_values("sign_texts", 10)
        visual_features = clean_values("visual_features", 15)
        knowledge_by_place[title] = article
        aliases_by_place[title] = title
        aliases_by_place.update({alias: title for alias in aliases})
        recognition_lines.append(
            f"{title}\n"
            f"  別名：{'、'.join(aliases) or '無'}\n"
            f"  招牌文字：{'、'.join(sign_texts) or '無'}\n"
            f"  可見特徵：{'；'.join(visual_features) or '無'}"
        )

    return knowledge_by_place, aliases_by_place, recognition_lines


def _build_reference_image_urls(knowledge_by_place, limit=12):
    archive_origin = urllib.parse.urlparse(ARCHIVE_ARTICLES_URL)
    references = []
    for title, article in knowledge_by_place.items():
        values = (article.get("recognition") or {}).get("reference_images")
        if not isinstance(values, list):
            continue
        for value in values[:3]:
            url = urllib.parse.urljoin(ARCHIVE_ARTICLES_URL, str(value).strip())
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme == "https" and parsed.netloc == archive_origin.netloc:
                references.append((title, url))
                if len(references) == limit:
                    return references
    return references


def _build_article_video(article):
    recognition = article.get("recognition") or {}
    video_value = str(recognition.get("video_url", "")).strip()
    preview_value = str(recognition.get("video_preview_url", "")).strip()
    if not video_value or not preview_value:
        return None
    video_url = urllib.parse.urljoin(ARCHIVE_ARTICLES_URL, video_value)
    preview_url = urllib.parse.urljoin(ARCHIVE_ARTICLES_URL, preview_value)
    archive_host = urllib.parse.urlparse(ARCHIVE_ARTICLES_URL).netloc

    def is_archive_https(url):
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme == "https" and parsed.netloc == archive_host

    if not is_archive_https(video_url) or not is_archive_https(preview_url):
        return None
    return {"videoUrl": video_url, "videoPreviewUrl": preview_url}


def _image_mime_type(image_bytes):
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


async def process_image_identification(image_bytes, user_id, account_id="default"):
    """從數位典藏歷史館抓取文章，進行視覺辨識與導覽生成"""
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    try:
        login_identity = await asyncio.to_thread(
            get_login_identity, account_id, user_id
        )
        profile = await asyncio.to_thread(get_profile, login_identity) if login_identity else {}
        language = normalize_preferences(profile.get("preferences"))["language"]
    except Exception:
        language = "zh-TW"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            archive_response = await client.get(ARCHIVE_ARTICLES_URL)
            archive_response.raise_for_status()
        articles = archive_response.json().get("articles", [])
        knowledge_by_place, aliases_by_place, recognition_lines = _build_recognition_context(articles)
        if not knowledge_by_place:
            raise ValueError("數位典藏站沒有啟用圖片辨識的歷史文章")
    except Exception as e:
        print("抓取數位典藏站資料失敗:", e)
        ai_response_text = "目前無法讀取數位典藏歷史資料，請稍後再試。"
        set_user_cache(user_id, ai_response_text)
        return {"aiResponse": ai_response_text, "locationName": "", "hash": image_hash}

    places_str = "\n- ".join(recognition_lines)
    reference_parts = []
    exact_match = None
    async with httpx.AsyncClient(timeout=10) as client:
        for title, url in _build_reference_image_urls(knowledge_by_place):
            try:
                reference_response = await client.get(url)
                reference_response.raise_for_status()
                reference_bytes = reference_response.content
                if not reference_response.headers.get("content-type", "").lower().startswith("image/"):
                    continue
                if not reference_bytes or len(reference_bytes) > 10 * 1024 * 1024:
                    continue
                if hashlib.sha256(reference_bytes).hexdigest() == image_hash:
                    exact_match = title
                    break
                reference_parts.extend([
                    f"「{title}」的已知參考照片：",
                    {"mime_type": _image_mime_type(reference_bytes), "data": reference_bytes},
                ])
            except Exception as error:
                print(f"讀取典藏參考照片失敗: {error}")

    prompt = render_prompt("image_identification", places_str=places_str) + """

參考照片規則：
1. 已知參考照片是最高優先證據。
2. 比較待辨識照片與參考照片的建築結構及固定特徵。
3. 歷史背景不可作為照片辨識證據。
4. 第一行必須使用白名單正式地點名稱。
""" + "\n" + gemini_language_instruction(language)

    if exact_match:
        best_place = exact_match
        visual_text = f"鑑定結果：{best_place}\n與典藏參考照片完全一致。"
    else:
        response = model.generate_content([
            prompt,
            "待辨識照片：",
            {"mime_type": _image_mime_type(image_bytes), "data": image_bytes},
            *reference_parts,
        ])
        visual_text = response.text
        best_place = "未知地點"
        if "鑑定結果：" in visual_text:
            first_line = visual_text.split("\n")[0]
            inferred_place = first_line.replace("鑑定結果：", "").strip()
            for candidate in sorted(aliases_by_place, key=len, reverse=True):
                if candidate in inferred_place:
                    best_place = aliases_by_place[candidate]
                    break

    if best_place == "未知地點":
        observation = visual_text.replace("鑑定結果：未知地點", "").strip()
        ai_response_text = f"{i18n_text(language, 'unknown_place')}\n\n{observation}"
        
        # ⚡ 存入口袋
        set_user_cache(user_id, ai_response_text)
        
        return {
            "aiResponse": ai_response_text,
            "locationName": "未知地點",
            "hash": image_hash,
            "visualText": visual_text,
            "needsConfirmation": True
        }

    article = knowledge_by_place[best_place]
    content = html.unescape(re.sub(r"<[^>]+>", " ", article.get("content", "")))
    content = re.sub(r"\s+", " ", content).strip()
    local_knowledge = (
        f"【館藏類型】：{article.get('collection_type', '')}\n"
        f"【年代】：{article.get('period', '')}\n"
        f"【地點】：{article.get('location_name', '')}\n"
        f"【摘要】：{article.get('summary', '')}\n"
        f"【正文】：{content}"
    )

    intro_prompt = render_prompt(
        "history_intro",
        best_place=best_place,
        local_knowledge=local_knowledge,
    ) + "\n" + gemini_language_instruction(language)

    intro_response = model.generate_content(intro_prompt)
    
    easter_egg_plot = (
        i18n_text(language, "sugar_factory_easter_egg")
        if best_place == "虎尾糖廠第一工場"
        else ""
    )
    final_ai_text = f"{intro_response.text}{easter_egg_plot}"
    video = _build_article_video(article) or {}

    # ⚡ 完美將圖片辨識結果存入記憶體口袋，語音秒抓！
    set_user_cache(user_id, final_ai_text)

    return {
        "aiResponse": final_ai_text,
        "locationName": best_place,
        "hash": image_hash,
        "visualText": visual_text,
        "needsConfirmation": True,
        **video,
    }
