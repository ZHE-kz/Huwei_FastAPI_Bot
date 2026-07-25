import urllib.parse
from typing import Dict, Any, List
from maps import build_itinerary_google_map_url
from config import PRIMARY_COLOR

# 🌟 新增：圖片專屬快取口袋 (Cloud Run 溫啟動時完美發揮作用)
_image_url_cache = {}

def get_itinerary_image_url_sync(db, place_name: str) -> str | None:
    global _image_url_cache
    
    # ⚡ 如果口袋裡有，光速 0 延遲回傳！
    if place_name in _image_url_cache:
        return _image_url_cache[place_name]

    try:
        doc_ref = db.collection("ItineraryDB").document(place_name)
        doc = doc_ref.get()
        if doc.exists:
            img_url = doc.to_dict().get("imageUrl")
            _image_url_cache[place_name] = img_url  # 記入口袋
            return img_url
    except Exception as e:
        print(f"抓取圖片失敗: {e}")
        
    _image_url_cache[place_name] = None # 找不到也記起來，避免下次重複找
    return None

# ==========================================
# 🌟 專屬單點推薦卡片產生器 (資料庫滿血版)
# ==========================================
def create_simple_location_flex(parsed_json: Dict[str, Any], weather: str, db_data: Dict[str, Any] = None) -> Dict[str, Any]:
    primary_color = PRIMARY_COLOR
    
    # 強制轉型與預設值防呆
    name = str(parsed_json.get("name") or "推薦景點")
    category = str(parsed_json.get("category") or "熱門打卡")
    time_str = str(parsed_json.get("time") or "依店家公告為主")
    desc = str(parsed_json.get("description") or "這是一個非常值得一去的好地方！")
    img_url = None

    if db_data:
        name = str(db_data.get("placeName") or name)
        category = str(db_data.get("category") or category)
        time_str = str(db_data.get("openingHours") or time_str)
        desc = str(db_data.get("feature") or desc)
        img_url = db_data.get("imageUrl")

    map_url = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote_plus(name)

    bubble = {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": f"🌤️ 今日天氣：{weather}", "size": "xs", "color": primary_color, "weight": "bold"},
                {"type": "text", "text": name, "weight": "bold", "size": "xl", "margin": "md", "wrap": True},
                {"type": "text", "text": f"🏷️ 類別：{category} | 🕒 {time_str}", "size": "xs", "color": "#888888", "margin": "sm", "wrap": True},
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": desc, "wrap": True, "size": "sm", "margin": "md", "color": "#333333"}
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "button", "style": "primary", "color": primary_color, "action": {"type": "uri", "label": "📍 開啟地圖導航", "uri": map_url}}
            ]
        }
    }

    if img_url:
        bubble["hero"] = {"type": "image", "url": img_url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"}

    return bubble

# ==========================================
# 🌟 原本的行程卡片產生器 (防破圖優化)
# ==========================================
def create_itinerary_flex(db, json_data: Dict[str, Any], itinerary_id: str, weather_summary: str) -> Dict[str, Any]:
    primary_color = PRIMARY_COLOR
    stops_data: List[dict] = json_data.get("stops") or []
    map_url = build_itinerary_google_map_url(stops_data)

    stops_elements: List[dict] = []
    for index, stop in enumerate(stops_data):
        is_first = index == 0
        is_last = index == len(stops_data) - 1
        location_name = stop.get("location") or "未命名景點"
        time_str = stop.get("time") or "--:--"

        text_contents = [{"type": "text", "text": location_name, "size": "md", "weight": "bold", "color": primary_color if is_first else "#333333", "wrap": True}]
        if stop.get("note"):
            text_contents.append({"type": "text", "text": stop.get("note"), "size": "xs", "color": "#888888", "wrap": True, "margin": "sm"})
        
        # ⚡ 這裡現在會享受光速快取的加持！
        img_url = get_itinerary_image_url_sync(db, location_name)
        
        right_area_contents = [{"type": "box", "layout": "vertical", "flex": 5, "contents": text_contents}]
        if img_url:
            right_area_contents.append({
                "type": "box", "layout": "vertical", "flex": 2, "paddingStart": "sm",
                "contents": [{"type": "image", "url": img_url, "size": "sm", "aspectRatio": "1:1", "aspectMode": "cover", "backgroundColor": "#EEEEEE"}]
            })

        stops_elements.append({
            "type": "box", "layout": "horizontal", "margin": "none",
            "contents": [
                {"type": "box", "layout": "vertical", "flex": 2, "paddingTop": "2px", "contents": [{"type": "text", "text": time_str, "size": "sm", "color": primary_color if is_first else "#888888", "weight": "bold", "align": "end"}]},
                {"type": "box", "layout": "vertical", "flex": 1, "maxWidth": "28px", "alignItems": "center", "contents": [
                     {"type": "box", "layout": "vertical", "width": "2px", "height": "10px", "backgroundColor": "#FFFFFF" if is_first else primary_color, "contents": []},
                     {"type": "box", "layout": "vertical", "width": "12px", "height": "12px", "cornerRadius": "6px", "backgroundColor": primary_color, "contents": []},
                     {"type": "box", "layout": "vertical", "width": "2px", "flex": 1, "backgroundColor": "#FFFFFF" if is_last else primary_color, "contents": []},
                 ]},
                {"type": "box", "layout": "horizontal", "flex": 7, "paddingBottom": "none" if is_last else "xl", "contents": right_area_contents},
            ]
        })

    body_contents = [
        {"type": "text", "text": "虎尾智慧行程推薦", "size": "sm", "color": primary_color, "weight": "bold"},
        {"type": "text", "text": json_data.get("title") or "虎尾推薦行程", "weight": "bold", "size": "xxl", "margin": "md", "wrap": True},
    ]
    if weather_summary:
        body_contents.append({
            "type": "box", "layout": "vertical", "margin": "md", "paddingAll": "sm", "backgroundColor": "#F3F8F5", "cornerRadius": "md",
            "contents": [
                {"type": "text", "text": "今日天氣", "size": "xs", "color": primary_color, "weight": "bold"},
                {"type": "text", "text": weather_summary, "size": "xs", "color": "#555555", "margin": "xs", "wrap": True},
            ]
        })

    body_contents.extend([
        {"type": "text", "text": "總距離：約 " + str(json_data.get("total_distance") or "依地圖導航為主"), "size": "xs", "color": "#AAAAAA", "margin": "sm"},
        {"type": "separator", "margin": "xl"},
        {"type": "box", "layout": "vertical", "margin": "lg", "contents": stops_elements},
    ])

    return {
        "type": "bubble",
        "size": "mega",
        "body": {"type": "box", "layout": "vertical", "paddingAll": "lg", "contents": body_contents},
        "footer": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                     {"type": "button", "style": "secondary", "flex": 1, "action": {"type": "postback", "label": "很棒", "data": f"action=rate_itinerary_new&id={itinerary_id}&score=5", "displayText": "這個行程很棒"}},
                     {"type": "button", "style": "secondary", "flex": 1, "action": {"type": "postback", "label": "普通", "data": f"action=rate_itinerary_new&id={itinerary_id}&score=3", "displayText": "這個行程普通"}}
                ]},
                {"type": "button", "style": "primary", "color": primary_color, "action": {"type": "uri", "label": "開啟 Google Maps", "uri": map_url}}
            ]
        }
    }