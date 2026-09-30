# 貢獻指南

感謝你協助改善 Huwei FastAPI Bot。任何人都可以 Fork 此專案並提出 Pull Request；正式程式碼與部署仍由維護者審核。

## 開始開發

1. Fork 此儲存庫，從 `main` 建立功能分支。
2. 建立 Python 3.12 虛擬環境並安裝依賴：

   ```bash
   python -m venv .venv
   python -m pip install -r requirements.txt
   ```

3. 複製 `.env.example` 為 `.env`，只填入自己的測試憑證。
4. 進行最小且聚焦的修改，不變更無關檔案。

## 提交前檢查

```bash
python -m compileall .
```

若修改 FastAPI 入口或路由，再啟動服務並檢查：

```bash
python -m uvicorn main:app --port 8000
curl http://127.0.0.1:8000/health
```

預期回應：`{"status":"ok"}`。

## Pull Request 規則

- 說明修改內容、原因及測試結果。
- 每個 Pull Request 只處理一個明確目的。
- 不提交 `.env`、API key、token、Google 服務帳戶或使用者資料。
- 保留 LINE Webhook 簽章驗證、輸入驗證及可讀錯誤處理。
- Pull Request 必須通過自動檢查並完成維護者審核後才能合併。

## 部署

外部貢獻者不需要也不應取得正式環境密鑰。合併至 `main` 後的正式部署由專案維護者及 GitHub Actions 負責。
