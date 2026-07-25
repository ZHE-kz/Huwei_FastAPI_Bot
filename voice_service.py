import base64
import traceback
import httpx
from typing import Optional, Tuple

# 🚨 你的 Modal Serverless 語音生成端點
MODAL_URL = "https://kuizhelin--huwei-tts-service-huweittsmodel-synthesize-text.modal.run"
MAX_TEXT_LENGTH = 120

def split_text_gracefully(text: str, max_length: int = MAX_TEXT_LENGTH) -> Tuple[str, str]:
    """
    ✂️ 終極魔法：文字優雅切塊
    將過長的文字從最接近 120 字的標點符號處切斷，避免話講一半被卡掉。
    回傳 (目前這段要唸的字, 剩下還沒講完的字)
    """
    if not text:
        return "", ""
        
    if len(text) <= max_length:
        return text, ""

    chunk = text[:max_length]
    # 優先尋找句號、驚嘆號等斷句感強的標點
    punctuations = ["。", "！", "？", "，", "\n", ".", "!", "?", ","]
    split_idx = -1
    
    for p in punctuations:
        idx = chunk.rfind(p)
        if idx > split_idx:
            split_idx = idx

    # 如果整段 120 字連一個標點符號都沒有，就只能硬切
    if split_idx == -1:
        split_idx = max_length - 1

    current_chunk = text[:split_idx + 1]
    remaining_text = text[split_idx + 1:].strip()

    return current_chunk, remaining_text


async def generate_tts_audio_bytes(text: str) -> Optional[bytes]:
    """
    🚀 呼叫 Modal Serverless GPU 產生語音
    回傳音檔的二進位資料 (bytes)，準備交給 Firebase Storage 存檔
    """
    if not text:
        return None
        
    try:
        payload = {"text": text}
        # 設定 timeout 為 30 秒，因為喚醒冷機的 Modal GPU 可能需要一點時間
        async with httpx.AsyncClient() as client:
            print(f"🚀 正在發送文字至 Modal GPU 錄音室: {text[:20]}...")
            response = await client.post(MODAL_URL, json=payload, timeout=180.0)

            if response.status_code == 200:
                json_res = response.json()
                audio_base64 = json_res.get("audio_data")

                if audio_base64:
                    print("✅ 語音生成成功！取得音檔二進位資料。")
                    # 將 Base64 解碼回真實的音檔 bytes
                    return base64.b64decode(audio_base64)
                else:
                    print(f"🚨 Modal 回傳成功，但找不到 audio_data 欄位: {response.text}")
                    return None
            else:
                print(f"🚨 Modal 請求失敗，狀態碼: {response.status_code}, 原因: {response.text}")
                return None

    except Exception as e:
        print(f"🚨 generate_tts_audio_bytes 發生未預期錯誤:\n{traceback.format_exc()}")
        return None