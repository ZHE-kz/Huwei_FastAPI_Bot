# Huwei FastAPI Bot 專案交接文件

更新日期：2026-10-28
交接基準分支：`codex/voice-phase1`
交接基準提交：`8eb74a3`

## 1. 專案目的

此服務是虎尾數位典藏的 LINE Bot 後端。主要功能包括：

- 一般對話、景點推薦與行程規劃。
- 依典藏文章與參考照片辨識景點。
- 辨識成功後回覆典藏介紹、影片與語音。
- LINE 解謎遊戲與管理後台。
- LINE Beacon 地點通知。
- 多個 LINE 官方帳號共用同一套後端。
- GitHub Pull Request 檢查與 Cloud Run 自動部署。

## 2. 目前版本狀態

- GitHub：`https://github.com/ZHE-kz/Huwei_FastAPI_Bot`
- 遠端正式分支：`origin/main`，目前停在 `abf31d7`。
- 本交接分支比 `origin/main` 多 5 個提交，尚未合併：
  - `c508a2a`：TTS 音質、快取與穩定性。
  - `4a5b242`：圖片辨識後傳送典藏影片。
  - `51fc5fc`：多 LINE 帳號。
  - `89bfbc7`：Beacon webhook 模擬器。
  - `8eb74a3`：Beacon 管理與事件分流。
- 正式 Cloud Run 曾以此分支內容手動部署，但 GitHub `main` 尚未包含上述 5 個提交。
- 接手後第一優先：建立或更新 PR，測試後合併至 `main`，避免下次自動部署退回舊版。

## 3. 正式環境

- Google Cloud 專案：`gen-lang-client-0850797474`
- Cloud Run 區域：`asia-east1`
- Cloud Run 服務：`huwei-fastapi-bot`
- Runtime service account：`huwei-bot-runtime@gen-lang-client-0850797474.iam.gserviceaccount.com`
- Build service account：`huwei-bot-builder@gen-lang-client-0850797474.iam.gserviceaccount.com`
- 公開入口：`https://linebot.zheforge.com`
- 主 LINE Webhook：`https://linebot.zheforge.com/`
- 第二帳號 Webhook：`https://linebot.zheforge.com/line/second`
- 管理後台：`https://linebot.zheforge.com/admin/puzzles`
- 數位典藏辨識資料：`https://nfu-digital-archive.zheforge.com/api/articles?category=history`

Cloudflare Worker 只做代理，將 `linebot.zheforge.com/*` 原路徑轉送至 `ORIGIN_URL`。

## 4. 系統流程

### LINE Webhook

1. LINE 對 `/` 或 `/line/{account_id}` 傳送事件。
2. `main.py` 以對應 Channel Secret 驗證 `X-Line-Signature`。
3. Webhook 立即建立背景工作並回傳成功。
4. `background_task_router()` 依序分流：
   - Beacon 事件。
   - 解謎流程。
   - 圖片辨識。
   - 一般對話、景點或行程規劃。

### 圖片辨識

1. 從 LINE 下載使用者照片。
2. 從典藏 API 讀取 `recognition.enabled=true` 的文章。
3. 下載同網域 `reference_images`。
4. SHA-256 完全相同時直接命中地點。
5. 未完全命中時，交由 Gemini 比對白名單與參考照片。
6. 使用典藏文章內容生成導覽文字。
7. 若文章同時有合法 `video_url` 與 `video_preview_url`，附加 LINE 影片訊息。

典藏文章辨識欄位：

```json
{
  "recognition": {
    "enabled": true,
    "aliases": [],
    "sign_texts": [],
    "visual_features": [],
    "reference_images": [],
    "video_url": "",
    "video_preview_url": ""
  }
}
```

影片與預覽圖必須是典藏站同網域 HTTPS URL。兩者缺一時不傳影片。

### 語音

1. 使用者點「播放語音」。
2. 清除 Markdown、URL、Emoji，轉換日期、數字與常見英文縮寫。
3. 依完整句子取朗讀內容。
4. 以文字與語音設定產生 SHA-256 快取路徑。
5. GCS 命中時直接重用；否則呼叫 Modal。
6. 驗證 JSON、Base64、音檔大小及實際長度後上傳 GCS。
7. LINE 使用 `/tts/{profile}/{cache_key}.mp3` 取得私有 bucket 音檔。

Modal 請求格式：

```json
{
  "text": "朗讀內容",
  "speaker": "default",
  "speed": 1.0,
  "pitch": 0.0
}
```

Modal 回應需包含 `audio_data` Base64 MP3。`429`、`502`、`503` 最多重試兩次。

### 解謎

- 預設開始指令：`壁虎我來幫忙`
- 結束指令：`結束解謎`
- 題庫來源：公開 Google 試算表，再由 Firestore `PuzzleConfig` 覆蓋。
- 支援文字答案與 Gemini 圖片任務。
- 後台支援 CSV/XLSX 匯入、單關編輯及全域設定。

### Beacon

- 支援 `enter`、`leave`、`banner`。
- 以 `hwid` 讀取 Firestore `LineBeacons`。
- 可設定地點、通用訊息、事件專用訊息及冷卻秒數。
- 冷卻鍵包含帳號、使用者、`hwid`、事件類型，避免重複通知。

## 5. HTTP 路由

- `GET /health`：健康檢查，成功為 `{"status":"ok"}`。
- `POST /`：主 LINE 帳號 Webhook。
- `POST /line/{account_id}`：額外 LINE 帳號 Webhook。
- `GET /tts/{profile}/{cache_key}.mp3`：代理讀取 GCS 語音。
- `GET /maps/route/{itinerary_id}`：轉址 Google Maps 行程。
- `/admin/puzzles`：解謎、Beacon、Prompt、更新日誌管理後台。
- `/admin/puzzles/api*`：後台資料 API，需有效簽章 Cookie。

## 6. 主要程式

- `main.py`：FastAPI 入口、簽章驗證、事件分流與公開路由。
- `config.py`：環境變數及多 LINE 帳號憑證解析。
- `itinerary_processor.py`：一般訊息、行程、圖片辨識、典藏影片。
- `voice_service.py`：文字清理、Modal TTS、重試、GCS 快取。
- `puzzle_core.py`：解謎狀態機。
- `beacon_core.py`：Beacon 驗證、事件訊息與防重複通知。
- `admin_tools.py`：管理後台與 API。
- `prompt_store.py`：Prompt 預設值、Firestore 覆寫與快取。
- `firestore_client.py`：Firestore client 與集合快取。
- `flex_builder.py`：LINE Flex Message。
- `weather.py`：中央氣象署資料。
- `whitelist.py`：可推薦景點白名單。
- `.github/workflows/check.yml`：PR Python 語法檢查。
- `.github/workflows/deploy.yml`：`main` 推送後部署 Cloud Run。
- `cloudflare/`：公開網域反向代理。

## 7. Firestore 集合

- `ItineraryDB`：景點及行程資料。
- `ItineraryHistory`：使用者行程、辨識結果及評分狀態。
- `ItineraryStats`：評分統計。
- `PuzzleConfig`：關卡與 `_settings`。
- `PuzzleState`：每位使用者目前關卡。
- `LineBeacons`：Beacon `hwid` 設定。
- `LineBeaconCooldowns`：Beacon 防重複通知時間。
- `BotPrompts`：可由後台修改的 Prompt。
- `UpdateLogs`：部署與人工更新日誌。

不要匯出或提交使用者 ID、Access Token、服務帳戶 JSON。

## 8. 環境變數與 Secret

必要：

- `LINE_ACCESS_TOKEN`
- `LINE_CHANNEL_SECRET`
- `GEMINI_API_KEY`

依功能需要：

- `CWA_API_KEY`
- `PUZZLE_ADMIN_SECRET`
- `GOOGLE_DRIVE_FOLDER_ID`
- `TTS_MODAL_URL`
- `TTS_AUDIO_BUCKET`
- `PUBLIC_BASE_URL`，預設 `https://linebot.zheforge.com`
- `TTS_SPEAKER`，預設 `default`
- `TTS_SPEED`，預設 `1.0`，允許 `0.5`～`2.0`
- `TTS_PITCH`，預設 `0.0`，允許 `-12`～`12`

多帳號：

- `LINE_ACCOUNT_IDS=second,other-id`
- `LINE_ACCOUNT_SECOND_CHANNEL_SECRET`
- `LINE_ACCOUNT_SECOND_ACCESS_TOKEN`

`account_id` 只允許小寫英數與連字號，最長 32 字。Secret 必須放 Secret Manager，不可寫入 Git。

GitHub Repository Secrets：

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`

## 9. 權限

Cloud Run runtime service account 至少需要：

- 讀寫所需 Firestore 集合。
- `roles/secretmanager.secretAccessor`。
- TTS bucket 的 `roles/storage.objectAdmin`。
- 若使用 Drive，目標資料夾需分享給 runtime service account。

GitHub deployer 需能部署 Cloud Run、使用指定 runtime/build service account，並透過 Workload Identity 登入。

## 10. 本機接手

```powershell
git clone https://github.com/ZHE-kz/Huwei_FastAPI_Bot.git
cd Huwei_FastAPI_Bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn main:app --reload --port 8000
```

`main.py` 啟動時要求主 LINE Token、Channel Secret、Gemini Key。沒有測試憑證時，可先用測試環境值，但不可提交 `.env`。

## 11. 測試

最低檢查：

```powershell
python -m compileall -q -x '(^|.*[\\/])graphify' .
python -m unittest discover -v
```

路由檢查：

```powershell
curl.exe http://127.0.0.1:8000/health
```

預期：`{"status":"ok"}`。

Beacon 離線 payload：

```powershell
python beacon_smoke_test.py --hwid YOUR_HWID
```

TTS 固定 15 段音質測試會真的呼叫 Modal：

```powershell
python tts_quality_check.py
```

執行前必須取得測試授權，輸出位於被 Git 忽略的 `tts-quality-output/`。

## 12. 部署與驗證

正式流程：功能分支提交 PR，檢查通過後合併至 `main`。GitHub Actions 自動部署。

部署後檢查：

```powershell
curl.exe https://linebot.zheforge.com/health
gcloud run services describe huwei-fastapi-bot `
  --project gen-lang-client-0850797474 `
  --region asia-east1
```

再確認：

1. 主帳號傳文字，Cloud Run 出現 `POST / 200`。
2. 第二帳號傳文字，出現 `POST /line/second 200`。
3. 上傳已收錄參考照片，回覆正確地點。
4. 有影片欄位的文章能播放影片。
5. 點擊「播放語音」，LINE 音訊可播放且 duration 正確。
6. Beacon 的 `enter`、`leave`、`banner` 與冷卻時間正確。

## 13. 已知風險與待辦

1. **未合併版本**：本分支比 `origin/main` 多 5 個提交。必須先合併，否則下次 `main` 部署會缺少新功能。
2. **冷啟動**：曾觀察到 Cloud Run 首次 Webhook 約 8 秒，造成 LINE Verify timeout。可設定 `--min-instances 1`；會增加費用。
3. **部署設定未保留常駐實例**：`.github/workflows/deploy.yml` 尚未設定 `--min-instances 1`。
4. **啟動工作偏重**：啟動時建立部署日誌並載入 Google 相關模組。若不設常駐實例，應再量測並延後非必要初始化。
5. **日誌清理**：部分舊程式仍輸出 DEBUG 訊息或外部 API 回應文字。應避免輸出 Token、使用者 ID、完整語音或敏感內容。
6. **測試範圍有限**：GitHub PR 目前只跑 `compileall`，尚未執行單元測試。

## 14. 交接清單

- [ ] 將 `codex/voice-phase1` 建立 PR 並合併至 `main`。
- [ ] 確認 GitHub Actions Check 與 Deploy 成功。
- [ ] 確認接手者可管理 GitHub Repository 與 PR。
- [ ] 確認接手者可檢視 Cloud Run、Logging、Secret Manager、Firestore、GCS。
- [ ] 不傳遞 Secret 明文；以 IAM 授權接手者。
- [ ] 確認兩個 LINE Developers Channel 的管理權限。
- [ ] 確認 Cloudflare zone 與 Worker 管理權限。
- [ ] 確認 Modal TTS 專案與端點管理權限。
- [ ] 逐項完成第 12 節的正式環境驗證。
- [ ] 決定是否接受 `min-instances=1` 的持續費用。

## 15. 故障快速判斷

- LINE 完全沒反應：先查 Cloud Run 是否有對應 `POST`。
- 沒有 `POST`：查 LINE Webhook URL 與 `Use webhook`。
- `401`：Channel Secret 不匹配。
- `200` 但沒有訊息：查背景工作日誌及 Access Token。
- Verify timeout 但 Cloud Run 最後 `200`：查冷啟動延遲。
- 圖片永遠辨識錯誤：查典藏 API 欄位、參考圖 URL、是否 `recognition.enabled=true`。
- 有影片但不能播放：查 HTTPS MP4、預覽圖、Content-Type 與 LINE 可公開存取性。
- 語音失敗：依序查 `TTS_MODAL_URL`、Modal 回應格式、GCS 權限、音檔 duration。
- Beacon 沒反應：查 LINE Beacon event、`hwid`、`LineBeacons.enabled` 與冷卻紀錄。
