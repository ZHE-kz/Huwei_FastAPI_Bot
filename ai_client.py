import os
import google.generativeai as genai

# 載入環境變數[cite: 4]
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def configure_gemini(api_key: str):
    if api_key:
        genai.configure(api_key=api_key)

async def generate_itinerary_async(prompt: str, model_name: str = "gemini-2.5-flash"):
    """
    非同步呼叫 Gemini API，並具備防崩潰與錯誤回傳機制
    """
    try:
        model = genai.GenerativeModel(model_name)
        response = await model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        print(f"🚨 [AI_CLIENT ERROR] Gemini API 呼叫失敗: {e}")
        # 如果 API 崩潰，回傳一個安全的 JSON 格式讓後端不會解析失敗
        return '{"type": "error", "text": "哎呀，導遊的雲端大腦剛好被五分車的汽笛聲干擾了，請稍後再試一次！"}'