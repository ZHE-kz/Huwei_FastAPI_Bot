# LIFF 個人中心部署

1. 在可管理的新 Provider 建立 LINE Login Channel 與 LIFF App；不需原 Bot Provider 管理權。Scopes 開啟 `openid`、`profile`，Endpoint 設為 `https://YOUR_DOMAIN/profile/`。
2. 設定 `LIFF_ID`、`LINE_LOGIN_CHANNEL_ID`、`PROFILE_PUBLIC_BASE_URL=https://YOUR_DOMAIN`；將 `LINE_LOGIN_CHANNEL_SECRET`、至少 32 字元的 `LIFF_SESSION_SECRET` 放入 Secret Manager。
3. 第二 Bot 帳號沿用 `LINE_ACCOUNT_IDS=second` 與既有 Messaging API 憑證。同一 LIFF 可用 `/profile/?account=second`；需要獨立 LIFF 時再設定帳號前綴變數。
4. 選用 `RICH_MENU_ZH_TW`、`RICH_MENU_EN_US`、`RICH_MENU_JA_JP`；第二帳號前綴改為 `LINE_ACCOUNT_SECOND_`。未設定不會改動既有 Rich Menu。
5. 建置映像後部署至 Cloud Run 專案 `gen-lang-client-0850797474`；確認 `/health` 與 `/profile/` 均為 200。向 Bot 傳送「綁定帳號」，開啟 HTTPS 網址完成測試。
6. 建議為 `AccountLinkTokens.expires_at` 啟用 Firestore TTL；即使尚未啟用，過期 Token 仍無法使用。

本機可設 `LIFF_COOKIE_SECURE=false`。後端執行 `uvicorn main:app --reload`；前端執行 `cd liff-app && npm install && npm run dev`。
