# LIFF 個人中心

開發：`npm install && npm run dev`。Vite 會將 `/api` 代理至 `127.0.0.1:8000`。

正式環境由 Docker 建置至 `liff-app/dist`，FastAPI 掛載於 `/profile`。LIFF Endpoint URL 設為 `https://YOUR_DOMAIN/profile/`。多 Bot 帳號可使用 `?account=second`。

LIFF App 必須啟用 `openid` 與 `profile` scope。前端只傳 `liff.getIDToken()`；伺服器驗證後使用 HttpOnly Cookie 建立短期 Session。
