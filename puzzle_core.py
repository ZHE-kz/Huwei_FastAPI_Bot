import base64
import csv
import io
from datetime import datetime, timezone

import google.generativeai as genai
import httpx

from firestore_client import get_db

SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSQhKOMFVy6CQusZgXpKZ3rbDjxk0Z3a2Z9tG1MFKJ8hG3jxSUODM6lKDw2x-p1L5dd_SdPMPJOWaeE/pub?gid=531672485&single=true&output=csv"
START_STAGE = "STAGE_01"


async def process_puzzle_event(
    reply_token,
    user_id,
    user_text,
    message_id,
    image_base64,
    line_token,
    gemini_key,
):
    db = get_db()
    current_time = datetime.now(timezone.utc)
    state_ref = db.collection("PuzzleState").document(user_id)
    state_doc = state_ref.get()

    puzzle_config = {}
    try:
        async with httpx.AsyncClient() as client:
            sheet_resp = await client.get(SHEET_CSV_URL)
            sheet_resp.raise_for_status()

            # 支援 utf-8-sig 格式以正確處理 Google 試算表的 BOM 標頭
            csv_text = sheet_resp.content.decode("utf-8-sig")

            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                stage_id = row.get("stage_id", "").strip()
                if stage_id:
                    puzzle_config[stage_id] = row

    except Exception as e:
        print(f"[ERROR] 讀取 Google 試算表失敗: {e}")
        return False

    # ==========================================
    # 狀態 A：尚未開始遊戲或已完成，等待觸發指令
    # ==========================================
    if not state_doc.exists or state_doc.to_dict().get("status") == "COMPLETED":
        if user_text and user_text.strip() == "壁虎我來幫忙":
            if START_STAGE not in puzzle_config:
                error_msg = (
                    f"哎呀... 找不到起始關卡設定 {START_STAGE}。"
                    f"目前的關卡清單：{list(puzzle_config.keys())}"
                )
                await send_line_reply(line_token, reply_token, error_msg)
                return True

            state_ref.set(
                {
                    "current_stage": START_STAGE,
                    "status": "WAITING_IMAGE",
                    "last_active": current_time,
                }
            )
            await send_line_reply(
                line_token,
                reply_token,
                puzzle_config[START_STAGE]["agent_intro"],
            )
            return True

    # 狀態 B：遊戲進行中
    user_state = state_doc.to_dict() if state_doc.exists else {}
    current_stage = user_state.get("current_stage", "STAGE_01")
    game_status = user_state.get("status", "WAITING_IMAGE")
    stage_data = puzzle_config.get(current_stage)

    if not stage_data:
        return False

    # 1. 狀態：等待玩家上傳解謎圖片
    if game_status == "WAITING_IMAGE" and image_base64:
        genai.configure(api_key=gemini_key)
        vision_model = genai.GenerativeModel("gemini-2.5-flash")
        image_bytes = base64.b64decode(image_base64)

        prompt = (
            f"請幫我檢查這張照片是否符合目標：{stage_data['vision_target']}。"
            "如果符合，請回答「辨識成功」；如果不符合，請簡述原因。"
            "請嚴格判斷，不要輕易放行。"
        )

        try:
            response = vision_model.generate_content(
                [prompt, {"mime_type": "image/jpeg", "data": image_bytes}]
            )
            if "辨識成功" in response.text:
                state_ref.update({"status": "WAITING_TEXT", "last_active": current_time})
                await send_line_reply(line_token, reply_token, stage_data["puzzle_hint"])
            else:
                await send_line_reply(
                    line_token,
                    reply_token,
                    "唔... 這張照片似乎還差了一點，請再拍一張看看！",
                )
        except Exception:
            await send_line_reply(line_token, reply_token, "大腦思考時發生了一點小意外，請再傳一次照片。")

        return True

    # 2. 狀態：等待玩家輸入文字答案
    if game_status == "WAITING_TEXT" and user_text:
        user_reply = user_text.strip()
        correct_answer = str(stage_data.get("puzzle_answer", "")).strip()

        if correct_answer in user_reply:
            state_ref.update({"status": "COMPLETED", "last_active": current_time})
            await send_line_reply(line_token, reply_token, stage_data["success_text"])
        else:
            # 🌟 修復原本斷行與亂碼錯誤的 f-string
            hint_msg = f"❌ 答錯囉！\n\n提示：{stage_data['puzzle_hint']}"
            await send_line_reply(line_token, reply_token, hint_msg)

        return True

    # 3. 防呆提示處理
    if game_status == "WAITING_IMAGE":
        await send_line_reply(
            line_token,
            reply_token,
            "📸 收到！現在請依照任務指示，拍下對應的照片傳給我喔！",
        )
        return True

    if game_status == "WAITING_TEXT":
        await send_line_reply(
            line_token,
            reply_token,
            "✍️ 收到！請直接輸入你的解謎答案文字給我！",
        )
        return True

    return False


async def send_line_reply(line_token, reply_token, text):
    if not text or not text.strip():
        print("⚠️ 警告：嘗試發送空訊息，已攔截！")
        return

    async with httpx.AsyncClient() as client:
        url = "https://api.line.me/v2/bot/message/reply"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_token}",
        }
        payload = {
            "replyToken": reply_token, 
            "messages": [{"type": "text", "text": text}]
        }
        r = await client.post(url, headers=headers, json=payload)
        
        # 🌟 印出 LINE 的真實抱怨內容
        if r.status_code != 200:
            print(f"🚨 LINE Reply 400 報錯詳情: {r.status_code} - {r.text}")