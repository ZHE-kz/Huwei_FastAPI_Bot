import traceback
from datetime import datetime, timedelta
from typing import Optional
import httpx

CWA_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091"

# 預設天氣快取 (確保系統剛啟動或連線失敗時不會崩潰)
_weather_cache = {"data": "暫無天氣資料，請攜帶雨具備用", "expire_time": datetime.min}

async def fetch_weather_async(client: Optional[httpx.AsyncClient], cwa_api_key: Optional[str]) -> str:
    global _weather_cache
    now = datetime.now()

    # 如果快取未過期，直接回傳記憶體中的資料
    if now < _weather_cache["expire_time"]:
        print("⚡ [快取] 直接讀取記憶體中的天氣資料")
        return _weather_cache["data"]

    if not cwa_api_key or cwa_api_key == "XXX":
        return "無法連線至氣象署 (缺少 API KEY)"

    params = {
        "Authorization": cwa_api_key,
        "format": "JSON",
        "locationName": "虎尾鎮", # 指定抓取虎尾的天氣
    }

    try:
        # 🌟 使用系統 CA 驗證憑證的 AsyncClient！
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(CWA_URL, params=params, timeout=5.0)
            if resp.status_code != 200:
                return _weather_cache["data"]  # 發生錯誤時回傳舊快取

            data = resp.json()
            locations = data.get("records", {}).get("Locations", [{}])[0].get("Location", [])
            if not locations:
                return _weather_cache["data"]

            elements = {el.get("ElementName"): el for el in locations[0].get("WeatherElement", [])}

            def get_val(el_name: str, keys: list[str]) -> str:
                el = elements.get(el_name)
                if not el or not el.get("Time"):
                    return ""
                val_obj = el["Time"][0].get("ElementValue", [{}])[0]
                for key in keys:
                    value = val_obj.get(key)
                    if value:
                        return str(value).strip()
                return ""

            weather = get_val("天氣現象", ["Weather", "value"])
            rain_prob = get_val("12小時降雨機率", ["ProbabilityOfPrecipitation", "value"]) or get_val("3小時降雨機率", ["ProbabilityOfPrecipitation", "value"])
            max_temp = get_val("最高溫度", ["MaxTemperature", "Temperature", "value"])
            min_temp = get_val("最低溫度", ["MinTemperature", "Temperature", "value"])

            parts = []
            if weather:
                parts.append(weather)
            if min_temp or max_temp:
                parts.append(f"{min_temp or '?'}-{max_temp or '?'}°C")
            if rain_prob:
                parts.append(f"降雨機率 {rain_prob}%")

            result = " | ".join(parts) if parts else "多雲時晴"

            # 寫入快取，保留 1 小時
            _weather_cache["data"] = result
            _weather_cache["expire_time"] = now + timedelta(hours=1)
            print("☁️ [更新] 成功從氣象署抓取最新天氣")

            return result

    except Exception as e:
        print(f"天氣 API 連線異常: {e}")
        return _weather_cache["data"]  # 發生意外錯誤時回傳舊快取

def force_clear_weather_cache():
    """強制清空天氣快取"""
    global _weather_cache
    _weather_cache["expire_time"] = datetime.min
    print("🗑️ [清空] 天氣快取已強制清除")