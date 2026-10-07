import os
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
PUZZLE_ADMIN_BASE_URL = os.environ.get("PUZZLE_ADMIN_BASE_URL", "").rstrip("/")
PUZZLE_ADMIN_EMAILS = {
    email.strip().casefold()
    for email in os.environ.get("PUZZLE_ADMIN_EMAILS", "").split(",")
    if email.strip()
}
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

# Flex Message 卡片與 UI 預設設定
PRIMARY_COLOR = "#1DB446"
MAP_DEFAULT_ZOOM = 16
MAP_SIZE = "1040x1040"
MAP_SCALE = 2

# 行程評分門檻 (超過此分數即有機會自動收錄進資料庫)[cite: 11]
PROMOTE_TO_DB_THRESHOLD = 4.5
