import os
import time
from typing import Optional
import google.auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# 載入設定（從環境變數讀取雲端硬碟資料夾 ID 與憑證路徑）
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
# 如果你的專案是用環境變數檔案或預設憑證，這裡會自動初始化 Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    """初始化並回傳 Google Drive API 服務實體"""
    credentials, _ = google.auth.default(scopes=SCOPES)
    return build('drive', 'v3', credentials=credentials)


def upload_audio_bytes_to_drive(audio_bytes: bytes, file_name: Optional[str] = None) -> Optional[str]:
    """
    ☁️ 將語音檔的 Bytes 上傳至 Google Drive，設定公開檢視，並回傳 LINE 專用的直接播放網址
    """
    if not audio_bytes:
        print("🚨 [Drive Error] 傳入的語音二進位資料是空的！")
        return None

    if not GOOGLE_DRIVE_FOLDER_ID:
        print("🚨 [Drive Error] 找不到 GOOGLE_DRIVE_FOLDER_ID 環境變數！")
        return None

    try:
        service = get_drive_service()
        
        # 命名檔案
        safe_name = file_name or f"tts_{int(time.time())}.m4a"
        
        file_metadata = {
            'name': safe_name,
            'parents': [GOOGLE_DRIVE_FOLDER_ID]
        }
        
        # 將 bytes 包裝成檔案串流
        media = MediaIoBaseUpload(
            io.BytesIO(audio_bytes),
            mimetype='audio/mp4', # LINE 播放音檔的最佳相容格式
            resumable=True
        )

        print(f"☁️ 正在上傳語音檔「{safe_name}」至 Google Drive...")
        
        # 1. 執行上傳
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        file_id = file.get('id')
        print(f"✅ 上傳成功！檔案 ID: {file_id}")

        # 2. 設定公開權限（「知道連結的人均可檢視」），讓 LINE 伺服器抓得到音檔
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        service.permissions().create(
            fileId=file_id,
            body=permission
        ).execute()
        print("🔓 已成功將檔案權限設為公開檢視。")

        # 3. 轉換成 LINE 專用的直接下載 / 播放網址格式
        direct_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        print(f"🔗 取得語音公開直連網址: {direct_url}")
        
        return direct_url

    except Exception as e:
        print(f"🚨 upload_audio_bytes_to_drive 發生未預期錯誤: {e}")
        return None