# GitHub → Cloud Run → Cloudflare

正式 Webhook URL：`https://linebot.zheforge.com/`

## Google Cloud

在 Cloud Run 服務 `huwei-fastapi-bot` 設定以下 Secret Manager 環境變數：

- `LINE_ACCESS_TOKEN`
- `LINE_CHANNEL_SECRET`
- `GEMINI_API_KEY`
- `CWA_API_KEY`
- `GOOGLE_DRIVE_FOLDER_ID`
- `ADMIN_TOKEN`
- 其他 `.env` 中實際使用的設定

Cloud Run 使用服務帳戶的 Application Default Credentials 存取 Firestore 與 Drive，不要上傳 `huwei agent.json`。請將 Drive 目標資料夾分享給 Cloud Run 執行身分，並授予 Secret Manager Secret Accessor。

另設定一般環境變數：

- `TTS_MODAL_URL`：Modal 語音生成 HTTPS 端點。
- `TTS_AUDIO_BUCKET`：專用於短期語音快取的 GCS bucket 名稱。
- `TTS_SPEAKER`：Modal 支援的音色 ID，預設 `default`。
- `TTS_SPEED`：語速，允許 `0.5`～`2.0`，預設 `1.0`。
- `TTS_PITCH`：音高，允許 `-12`～`12`，預設 `0.0`。

Cloud Run 執行身分需有該 bucket 的 `roles/storage.objectAdmin`。Bucket 保持私有，LINE 透過 Cloud Run `/tts/...` 路由播放音檔。建立後套用 `gcs-tts-lifecycle.json`，讓物件在 7 天後自動刪除：

```powershell
gcloud storage buckets update gs://YOUR_TTS_BUCKET --lifecycle-file=gcs-tts-lifecycle.json
```

部署前可用固定的 15 段虎尾典藏語料產生音檔，人工比對音色、速度、音高與斷句：

```powershell
python tts_quality_check.py
```

輸出放在 `tts-quality-output/`，不會納入 Git。

## GitHub

Repository secrets：

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`

推送到 `main` 後，GitHub Actions 會部署 Cloud Run。Cloudflare Worker 僅需以 Wrangler OAuth 部署一次，因為 Cloud Run 服務網址不會隨 revision 改變。

## Cloudflare

`zheforge.com` 必須位於目前登入的 Cloudflare 帳號。執行 `wrangler login` 後部署一次 Worker。

## LINE Developers

Webhook URL 設為 `https://linebot.zheforge.com/`，啟用 Webhook 後執行 Verify。服務會驗證 `X-Line-Signature`。

## 解謎管理後台

網址：`https://linebot.zheforge.com/admin/puzzles`

帳號：`admin`；密碼讀取本機 `.env` 的 `ADMIN_TOKEN`，題目儲存在 Firestore `PuzzleConfig`。

### 試算表匯入

後台支援 `.csv`、`.xlsx`，必要欄位為 `stage_id`、`puzzle_answer`。可先下載 CSV 範本；同 ID 關卡會覆寫，其他既有關卡不刪除。
