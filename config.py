import os
import re
from dotenv import load_dotenv

# 自動載入本地端的 .env 檔案 (如果在雲端運行，這行不會影響系統)
load_dotenv()

# 機密金鑰統一從環境變數讀取 (絕對不要寫死在這裡)
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
CWA_API_KEY = os.environ.get("CWA_API_KEY", "")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
PUZZLE_ADMIN_SECRET = os.environ.get("PUZZLE_ADMIN_SECRET", "")
LIFF_SESSION_SECRET = os.environ.get("LIFF_SESSION_SECRET", "")
LINE_LOGIN_CHANNEL_SECRET = os.environ.get("LINE_LOGIN_CHANNEL_SECRET", "")
PROFILE_PUBLIC_BASE_URL = os.environ.get("PROFILE_PUBLIC_BASE_URL", "").rstrip("/")
LIFF_COOKIE_SECURE = os.environ.get("LIFF_COOKIE_SECURE", "true").lower() != "false"


def get_line_account_credentials(account_id: str, environ=None):
    """讀取額外 LINE 帳號憑證；憑證值只存在環境變數。"""
    source = os.environ if environ is None else environ
    if not re.fullmatch(r"[a-z0-9-]{1,32}", account_id):
        return None
    allowed_ids = {
        value.strip()
        for value in source.get("LINE_ACCOUNT_IDS", "").split(",")
        if value.strip()
    }
    if account_id not in allowed_ids:
        return None
    env_key = account_id.upper().replace("-", "_")
    channel_secret = source.get(f"LINE_ACCOUNT_{env_key}_CHANNEL_SECRET", "").strip()
    access_token = source.get(f"LINE_ACCOUNT_{env_key}_ACCESS_TOKEN", "").strip()
    if not channel_secret or not access_token:
        return None
    return channel_secret, access_token


def _account_env_key(account_id: str) -> str:
    return account_id.upper().replace("-", "_")


def get_line_login_channel_id(account_id: str, environ=None):
    source = os.environ if environ is None else environ
    if account_id == "default":
        return source.get("LINE_LOGIN_CHANNEL_ID", "").strip() or None
    if get_line_account_credentials(account_id, source) is None:
        return None
    return source.get(
        f"LINE_ACCOUNT_{_account_env_key(account_id)}_LOGIN_CHANNEL_ID", ""
    ).strip() or source.get("LINE_LOGIN_CHANNEL_ID", "").strip() or None


def get_liff_id(account_id: str, environ=None):
    source = os.environ if environ is None else environ
    if account_id == "default":
        return source.get("LIFF_ID", "").strip() or None
    if get_line_account_credentials(account_id, source) is None:
        return None
    return (
        source.get(f"LINE_ACCOUNT_{_account_env_key(account_id)}_LIFF_ID", "").strip()
        or source.get("LIFF_ID", "").strip()
        or None
    )


def get_rich_menu_id(account_id: str, language: str, environ=None):
    source = os.environ if environ is None else environ
    language_key = language.upper().replace("-", "_")
    prefix = "" if account_id == "default" else f"LINE_ACCOUNT_{_account_env_key(account_id)}_"
    return source.get(f"{prefix}RICH_MENU_{language_key}", "").strip() or None

# Flex Message 卡片與 UI 預設設定
PRIMARY_COLOR = "#1DB446"
MAP_DEFAULT_ZOOM = 16
MAP_SIZE = "1040x1040"
MAP_SCALE = 2

# 行程評分門檻 (超過此分數即有機會自動收錄進資料庫)[cite: 11]
PROMOTE_TO_DB_THRESHOLD = 4.5
