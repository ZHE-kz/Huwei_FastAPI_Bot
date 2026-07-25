@echo off
chcp 65001 >nul
echo ==========================================
echo    🚀 正在一鍵啟動 虎尾 AI 導遊 Bot...
echo ==========================================

:: 1. 檢查並啟動虛擬環境 (支援 venv 或 .venv)
if exist venv\Scripts\activate.bat (
    echo [1/3] 正在啟用 venv 虛擬環境...
    call venv\Scripts\activate
) else if exist .venv\Scripts\activate.bat (
    echo [1/3] 正在啟用 .venv 虛擬環境...
    call .venv\Scripts\activate
) else (
    echo 🚨 找不到虛擬環境資料夾，將直接使用全域 Python...
)

:: 2. 開啟新視窗執行 FastAPI 伺服器
echo [2/3] 正在背景啟動 FastAPI (Port 8000)...
start "FastAPI Server" cmd /k "python -m uvicorn main:app --reload --port 8000"

:: 3. 等待 2 秒讓 FastAPI 準備好，然後啟動 Cloudflare 隧道
timeout /t 2 /nobreak >nul
echo [3/3] 正在啟動 Cloudflare 專屬網域隧道 (linebot.zheforge.com)...
start "Cloudflare Tunnel" cmd /k "cloudflared tunnel run --url http://localhost:8000 my-bot"

echo ==========================================
echo    🎉 所有服務已成功展開！
echo    🔗 您的專屬網域：https://linebot.zheforge.com
echo ==========================================
pause