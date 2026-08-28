# Huwei FastAPI Bot

LINE Webhook 的 FastAPI 服務，整合 Gemini、中央氣象署、Firestore 與 Google Drive。專案已包含 Codex 指引與專案級 ponytail skill；clone 後直接用 Codex 開啟資料夾即可接續開發。

## 在新電腦開始

需求：Git、Python 3.12、Codex。

```bash
git clone https://github.com/ZHE-kz/Huwei_FastAPI_Bot.git
cd Huwei_FastAPI_Bot
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS / Linux：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

填入 `.env`。本機如需 Firestore / Drive，將服務帳戶 JSON 放在 `credentials/service-account.json`，或使用 `gcloud auth application-default login`。密鑰與憑證目錄已被 Git 忽略。

啟動並檢查：

```bash
python -m uvicorn main:app --reload --port 8000
curl http://127.0.0.1:8000/health
```

成功回應：`{"status":"ok"}`。

## 用 Codex 接續開發

1. 在 Codex 選擇 clone 後的專案資料夾。
2. Codex 會讀取根目錄 `AGENTS.md`，並從 `.agents/skills` 載入專案級 ponytail。
3. 開始前先執行 `git pull --ff-only`；完成後檢查 `git diff`，再由你決定是否 commit / push。

任何電腦都只同步 Git 追蹤的檔案；`.env`、Google 憑證、尚未 commit 的修改不會自動帶過去。

## 主要檔案

- `main.py`：FastAPI 入口、LINE webhook、健康檢查。
- `config.py`：環境變數載入。
- `itinerary_processor.py`：行程與圖片處理流程。
- `puzzle_core.py`、`admin_tools.py`：解謎流程與管理 API。
- `firestore_client.py`、`drive_service.py`：Google Cloud 資料與檔案服務。
- `DEPLOY.md`：GitHub Actions、Cloud Run、Cloudflare 部署說明。

部署細節請看 [DEPLOY.md](DEPLOY.md)。
