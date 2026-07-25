import sys
import os
import uvicorn
import traceback

# 🌟 強制將執行檔/腳本所在的目錄加入 Python 搜尋路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

if __name__ == "__main__":
    try:
        print(f"🚀 正在啟動虎尾 LINE Bot FastAPI 伺服器... (工作目錄: {current_dir})")
        # 啟動 FastAPI 伺服器
        uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
    except Exception as e:
        print("發生未預期錯誤:")
        print(traceback.format_exc())
    
    input("\n程式已停止，請按 Enter 鍵結束視窗...")