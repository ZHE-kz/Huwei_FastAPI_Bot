import base64
import csv
import io
import time
from datetime import datetime, timezone

import google.generativeai as genai
import httpx

from firestore_client import get_db

SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSQhKOMFVy6CQusZgXpKZ3rbDjxk0Z3a2Z9tG1MFKJ8hG3jxSUODM6lKDw2x-p1L5dd_SdPMPJOWaeE/pub?gid=531672485&single=true&output=csv"
PUZZLE_COLLECTION = "PuzzleConfig"
DEFAULT_SETTINGS = {"start_command": "壁虎我來幫忙", "start_stage": "STAGE_01"}

_config_cache = None
_config_cache_until = 0


def force_clear_puzzle_cache():
    global _config_cache, _config_cache_until
    _config_cache = None
    _config_cache_until = 0


def normalize_stage(stage_id, data):
    vision_target = str(data.get("vision_target", "")).strip()
    return {
        "stage_id": stage_id,
        "agent_intro": str(data.get("agent_intro") or data.get("puzzle_hint") or f"開始 {stage_id} 關卡！").strip(),
        "vision_target": vision_target,
        "puzzle_hint": str(data.get("puzzle_hint", "")).strip(),
        "puzzle_answer": str(data.get("puzzle_answer", "")).strip(),
        "success_text": str(data.get("success_text") or "答對了！").strip(),
        "next_stage_id": str(data.get("next_stage_id", "")).strip(),
        "requires_image": data.get("requires_image", bool(vision_target)) in (True, "true", "1", 1),
    }


async def load_puzzle_config():
    global _config_cache, _config_cache_until
    if _config_cache and time.monotonic() < _config_cache_until:
        return _config_cache

    stages = {}
    settings = DEFAULT_SETTINGS.copy()

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(SHEET_CSV_URL)
            response.raise_for_status()
        for row in csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))):
            stage_id = row.get("stage_id", "").strip()
            if stage_id:
                stages[stage_id] = normalize_stage(stage_id, row)
    except Exception as error:
        print(f"[PUZZLE] 讀取預設試算表失敗: {error}")

    try:
        for document in get_db().collection(PUZZLE_COLLECTION).stream():
            data = document.to_dict() or {}
            if document.id == "_settings":
                settings.update({key: str(data.get(key, settings[key])).strip() for key in settings})
            else:
                stages[document.id] = normalize_stage(document.id, data)
    except Exception as error:
        print(f"[PUZZLE] 讀取 Firestore 題庫失敗: {error}")

    _config_cache = {"settings": settings, "stages": stages}
    _config_cache_until = time.monotonic() + 300
    return _config_cache


async def should_route_to_puzzle(user_id, user_text=""):
    config = await load_puzzle_config()
    if user_text.strip() == config["settings"]["start_command"]:
        return True
    state = get_db().collection("PuzzleState").document(user_id).get()
    return state.exists and (state.to_dict() or {}).get("status") != "COMPLETED"


def stage_status(stage):
    return "WAITING_IMAGE" if stage.get("requires_image") else "WAITING_TEXT"


async def process_puzzle_event(
    reply_token,
    user_id,
    user_text,
    message_id,
    image_base64,
    line_token,
    gemini_key,
):
    config = await load_puzzle_config()
    settings = config["settings"]
    stages = config["stages"]
    state_ref = get_db().collection("PuzzleState").document(user_id)
    state_doc = state_ref.get()
    state = state_doc.to_dict() if state_doc.exists else {}
    now = datetime.now(timezone.utc)

    if not state or state.get("status") == "COMPLETED":
        if user_text.strip() != settings["start_command"]:
            return False
        start_stage = settings["start_stage"]
        stage = stages.get(start_stage)
        if not stage:
            await send_line_reply(line_token, reply_token, f"找不到起始關卡：{start_stage}")
            return True
        state_ref.set({"current_stage": start_stage, "status": stage_status(stage), "last_active": now})
        await send_line_reply(line_token, reply_token, stage["agent_intro"])
        return True

    if user_text.strip() == "結束解謎":
        state_ref.update({"status": "COMPLETED", "last_active": now})
        await send_line_reply(line_token, reply_token, "已結束解謎遊戲。")
        return True

    current_stage = state.get("current_stage", settings["start_stage"])
    game_status = state.get("status", "WAITING_TEXT")
    stage = stages.get(current_stage)
    if not stage:
        await send_line_reply(line_token, reply_token, f"找不到目前關卡：{current_stage}")
        return True

    if game_status == "WAITING_IMAGE" and image_base64:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = (
            f"請檢查照片是否符合目標：{stage['vision_target']}。"
            "符合只回答「辨識成功」；不符合請簡述原因。請嚴格判斷。"
        )
        try:
            response = await model.generate_content_async(
                [prompt, {"mime_type": "image/jpeg", "data": base64.b64decode(image_base64)}]
            )
            if "辨識成功" in response.text:
                state_ref.update({"status": "WAITING_TEXT", "last_active": now})
                await send_line_reply(line_token, reply_token, stage["puzzle_hint"] or "照片正確，請輸入答案。")
            else:
                await send_line_reply(line_token, reply_token, "照片似乎不符合目標，請再拍一張看看！")
        except Exception as error:
            print(f"[PUZZLE] 圖片辨識失敗: {error}")
            await send_line_reply(line_token, reply_token, "圖片辨識發生錯誤，請稍後再試。")
        return True

    if game_status == "WAITING_TEXT" and user_text:
        answer = stage["puzzle_answer"]
        if answer and answer.casefold() in user_text.strip().casefold():
            next_stage_id = stage["next_stage_id"]
            next_stage = stages.get(next_stage_id)
            if next_stage:
                state_ref.update({
                    "current_stage": next_stage_id,
                    "status": stage_status(next_stage),
                    "last_active": now,
                })
                await send_line_reply(
                    line_token,
                    reply_token,
                    f"{stage['success_text']}\\n\\n{next_stage['agent_intro']}",
                )
            else:
                state_ref.update({"status": "COMPLETED", "last_active": now})
                await send_line_reply(line_token, reply_token, stage["success_text"])
        else:
            await send_line_reply(line_token, reply_token, f"❌ 答錯囉！\\n\\n提示：{stage['puzzle_hint']}")
        return True

    prompt = "📸 請依任務指示上傳照片。" if game_status == "WAITING_IMAGE" else "✍️ 請直接輸入解謎答案。"
    await send_line_reply(line_token, reply_token, prompt)
    return True


async def send_line_reply(line_token, reply_token, text):
    if not text or not text.strip():
        return
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        response = await client.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={"Authorization": f"Bearer {line_token}"},
            json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
        )
    if response.status_code != 200:
        print(f"[PUZZLE] LINE 回覆失敗: {response.status_code} - {response.text}")