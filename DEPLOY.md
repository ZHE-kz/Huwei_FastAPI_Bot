# GitHub → Cloud Run → Cloudflare

正式 Webhook URL：`https://linebot.zheforge.com/`

## Google Cloud

在 Cloud Run 服務 `huwei-fastapi-bot` 設定以下 Secret Manager 環境變數：

- `LINE_ACCESS_TOKEN`
- `LINE_CHANNEL_SECRET`
- `GEMINI_API_KEY`
- `CWA_API_KEY`
- `GOOGLE_DRIVE_FOLDER_ID`
- 其他 `.env` 中實際使用的設定

Cloud Run 使用服務帳戶的 Application Default Credentials 存取 Firestore 與 Drive，不要上傳 `huwei agent.json`。請將 Drive 目標資料夾分享給 Cloud Run 執行身分，並授予 Secret Manager Secret Accessor。

## GitHub

Repository secrets：

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`

推送到 `main` 後，GitHub Actions 會部署 Cloud Run。Cloudflare Worker 僅需以 Wrangler OAuth 部署一次，因為 Cloud Run 服務網址不會隨 revision 改變。

## Cloudflare

`zheforge.com` 必須位於目前登入的 Cloudflare 帳號。執行 `wrangler login` 後部署一次 Worker。

## LINE Developers

Webhook URL 設為 `https://linebot.zheforge.com/`，啟用 Webhook 後執行 Verify。服務會驗證 `X-Line-Signature`。
