import base64
import binascii
import asyncio
import hashlib
import io
import os
import re
from urllib.parse import quote
import httpx
from typing import Optional, Tuple

MAX_TEXT_LENGTH = 120
MIN_AUDIO_BYTES = 128
MAX_AUDIO_BYTES = 10 * 1024 * 1024
RETRYABLE_STATUS_CODES = {429, 502, 503}
MAX_RETRIES = 2
_http_client: Optional[httpx.AsyncClient] = None

ACRONYM_SPEECH = {
    "AI": "人工智慧",
    "API": "應用程式介面",
    "GPS": "全球定位系統",
    "GPU": "圖形處理器",
    "LINE": "LINE",
    "TTS": "文字轉語音",
    "URL": "網址",
}


def get_http_client() -> httpx.AsyncClient:
    """共用連線池，避免每次語音請求重新建立 TCP/TLS 連線。"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=180.0)
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


def get_tts_cache_key(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def get_tts_public_url(object_name: str) -> str:
    base_url = os.environ.get("PUBLIC_BASE_URL", "https://linebot.zheforge.com")
    return f"{base_url.rstrip('/')}/tts/{quote(object_name.removeprefix('tts/'))}"


def _integer_to_chinese(value: int) -> str:
    if value == 0:
        return "零"
    if value < 0:
        return "負" + _integer_to_chinese(-value)
    if value >= 10000:
        high, low = divmod(value, 10000)
        connector = "零" if 0 < low < 1000 else ""
        return _integer_to_chinese(high) + "萬" + connector + (
            _integer_to_chinese(low) if low else ""
        )

    digits = "零一二三四五六七八九"
    units = ((1000, "千"), (100, "百"), (10, "十"), (1, ""))
    parts = []
    pending_zero = False
    for unit_value, unit_name in units:
        digit, value = divmod(value, unit_value)
        if digit:
            if pending_zero:
                parts.append("零")
                pending_zero = False
            if not (unit_value == 10 and digit == 1 and not parts):
                parts.append(digits[digit])
            parts.append(unit_name)
        elif parts and value:
            pending_zero = True
    return "".join(parts)


def _speak_number(match: re.Match) -> str:
    value = match.group(0)
    if "." in value:
        integer, decimal = value.split(".", 1)
        digits = "零一二三四五六七八九"
        return _integer_to_chinese(int(integer)) + "點" + "".join(
            digits[int(digit)] for digit in decimal
        )
    return _integer_to_chinese(int(value))


def prepare_text_for_speech(text: str) -> str:
    """清理顯示用語法，並把常見日期、數字、縮寫轉為口語。"""
    if not isinstance(text, str):
        return ""

    value = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"https?://\S+|www\.\S+", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*(?:[-+] |\d+[.)] )", "", value, flags=re.MULTILINE)
    value = re.sub(r"[*_~>|]", "", value)
    value = re.sub(
        "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]",
        "",
        value,
    )

    def speak_date(match: re.Match) -> str:
        year, month, day = match.groups()
        year_text = "".join("零一二三四五六七八九"[int(d)] for d in year)
        return f"{year_text}年{_integer_to_chinese(int(month))}月{_integer_to_chinese(int(day))}日"

    value = re.sub(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", speak_date, value)
    value = re.sub(
        r"\b[A-Z]{2,8}\b",
        lambda match: ACRONYM_SPEECH.get(match.group(0), " ".join(match.group(0))),
        value,
    )
    value = re.sub(
        r"(?<![A-Za-z0-9])\d+(?:\.\d+)?(?![A-Za-z0-9])",
        _speak_number,
        value,
    )
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", "。", value)
    return re.sub(r"。{2,}", "。", value).strip(" 。")


def split_text_gracefully(text: str, max_length: int = MAX_TEXT_LENGTH) -> Tuple[str, str]:
    """只在完整句子邊界分段；單句過長時保留完整句子。"""
    if not text:
        return "", ""

    if len(text) <= max_length:
        return text, ""

    sentences = re.findall(r".*?(?:[。！？!?；;]+|$)", text)
    sentences = [sentence for sentence in sentences if sentence]
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_length:
            break
        current += sentence
        if len(current) >= max_length:
            break
    if not current:
        current = sentences[0]
    return current, text[len(current):].strip()


async def generate_tts_audio_bytes(
    text: str,
    speaker: Optional[str] = None,
    speed: Optional[float] = None,
    pitch: Optional[float] = None,
) -> Optional[bytes]:
    """
    🚀 呼叫 Modal Serverless GPU 產生語音
    回傳音檔的二進位資料 (bytes)，準備交給 Firebase Storage 存檔
    """
    if not isinstance(text, str) or not text.strip():
        return None

    modal_url = os.environ.get("TTS_MODAL_URL", "").strip()
    if not modal_url:
        print("🚨 [TTS Error] 缺少 TTS_MODAL_URL 環境變數")
        return None

    try:
        speech_text = prepare_text_for_speech(text)
        if not speech_text:
            return None
        speaker = (speaker or os.environ.get("TTS_SPEAKER", "default")).strip()
        speed = speed if speed is not None else float(os.environ.get("TTS_SPEED", "1.0"))
        pitch = pitch if pitch is not None else float(os.environ.get("TTS_PITCH", "0.0"))
        if (
            not re.fullmatch(r"[\w.-]{1,64}", speaker)
            or not 0.5 <= speed <= 2.0
            or not -12 <= pitch <= 12
        ):
            print("🚨 [TTS Error] speaker、speed 或 pitch 設定無效")
            return None
        payload = {
            "text": speech_text,
            "speaker": speaker,
            "speed": speed,
            "pitch": pitch,
        }
        client = get_http_client()
        print("🚀 正在向 Modal 產生語音")
        for attempt in range(MAX_RETRIES + 1):
            response = await client.post(modal_url, json=payload)
            if response.status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
                break
            await asyncio.sleep(0.5 * (2 ** attempt))

        if response.status_code != 200:
            print(f"🚨 [TTS Error] Modal HTTP {response.status_code}")
            return None

        try:
            json_res = response.json()
        except ValueError:
            print("🚨 [TTS Error] Modal 回傳非 JSON")
            return None

        audio_bytes = decode_audio_response(json_res)
        if audio_bytes is None:
            print("🚨 [TTS Error] Modal 音檔格式或大小無效")
            return None

        print(f"✅ 語音生成成功，大小 {len(audio_bytes)} bytes")
        return audio_bytes

    except httpx.HTTPError as exc:
        print(f"🚨 [TTS Error] Modal 連線失敗: {type(exc).__name__}")
        return None
    except Exception as exc:
        print(f"🚨 [TTS Error] 未預期錯誤: {type(exc).__name__}")
        return None


def decode_audio_response(payload: object) -> Optional[bytes]:
    """驗證 Modal JSON、Base64 與解碼後音檔大小。"""
    if not isinstance(payload, dict):
        return None

    audio_base64 = payload.get("audio_data")
    if not isinstance(audio_base64, str) or not audio_base64:
        return None

    max_base64_length = ((MAX_AUDIO_BYTES + 2) // 3) * 4
    if len(audio_base64) > max_base64_length:
        return None

    try:
        audio_bytes = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError):
        return None

    if not MIN_AUDIO_BYTES <= len(audio_bytes) <= MAX_AUDIO_BYTES:
        return None
    return audio_bytes


def get_audio_duration_ms(audio_bytes: bytes) -> Optional[int]:
    """依音檔實際資訊計算 LINE 所需毫秒數。"""
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(io.BytesIO(audio_bytes))
        length = getattr(getattr(audio, "info", None), "length", 0)
        if length <= 0:
            return None
        return max(1, round(length * 1000))
    except Exception:
        return None


async def get_or_create_tts_audio(text: str) -> Optional[Tuple[str, int]]:
    """從 GCS 重用 SHA-256 快取；未命中才呼叫 GPU 並上傳。"""
    normalized_text = prepare_text_for_speech(text)
    bucket_name = os.environ.get("TTS_AUDIO_BUCKET", "").strip()
    if not normalized_text or not bucket_name:
        print("🚨 [TTS Error] 文字為空或缺少 TTS_AUDIO_BUCKET")
        return None

    speaker = os.environ.get("TTS_SPEAKER", "default").strip()
    speed = os.environ.get("TTS_SPEED", "1.0").strip()
    pitch = os.environ.get("TTS_PITCH", "0.0").strip()
    profile = f"{speaker}-{speed}-{pitch}"
    safe_profile = re.sub(r"[^\w.-]", "_", profile)
    object_name = f"tts/{safe_profile}/{get_tts_cache_key(normalized_text)}.mp3"

    try:
        from google.cloud import storage

        def find_cached() -> Optional[Tuple[str, int]]:
            blob = storage.Client().bucket(bucket_name).blob(object_name)
            if not blob.exists():
                return None
            blob.reload()
            duration_ms = int((blob.metadata or {}).get("duration_ms", 0))
            return (get_tts_public_url(object_name), duration_ms) if duration_ms > 0 else None

        cached = await asyncio.to_thread(find_cached)
        if cached:
            print("✅ 命中語音快取")
            return cached

        audio_bytes = await generate_tts_audio_bytes(normalized_text)
        if not audio_bytes:
            return None

        duration_ms = get_audio_duration_ms(audio_bytes)
        if duration_ms is None:
            print("🚨 [TTS Error] 無法讀取音檔長度")
            return None

        def upload() -> str:
            blob = storage.Client().bucket(bucket_name).blob(object_name)
            blob.metadata = {"duration_ms": str(duration_ms)}
            blob.cache_control = "public, max-age=604800"
            blob.upload_from_string(audio_bytes, content_type="audio/mpeg")
            return get_tts_public_url(object_name)

        audio_url = await asyncio.to_thread(upload)
        print("✅ 語音已寫入 GCS 快取")
        return audio_url, duration_ms
    except Exception as exc:
        print(f"🚨 [TTS Error] GCS 快取失敗: {type(exc).__name__}")
        return None
