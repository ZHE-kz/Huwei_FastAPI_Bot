import urllib.parse
from typing import Dict, List

def build_itinerary_google_map_url(stops: List[Dict]) -> str:
    """產生 Google Maps 多點導航 URL (Directions URL)"""
    
    # 拆解網址避免被編輯器干擾[cite: 10]
    p1 = "https://www"
    p2 = ".google.com"
    base_maps = p1 + p2 + "/maps"
    base_search = p1 + p2 + "/maps/search/?api=1&query="
    base_dir = p1 + p2 + "/maps/dir/?api=1"

    if not stops:
        return base_maps

    valid_stops = []
    for stop in stops:
        if not stop:
            continue

        lat = stop.get("lat")
        lng = stop.get("lng")

        if lat is not None and lng is not None:
            valid_stops.append(f"{lat},{lng}")
        else:
            name = (stop.get("location") or "").strip()[:20]
            if name:
                # 🌟 加上地域限制，確保不會導航到外縣市或國外
                safe_name = name if "虎尾" in name else f"虎尾 {name}"
                valid_stops.append(safe_name)

    if len(valid_stops) == 0:
        return base_maps

    if len(valid_stops) == 1:
        query = urllib.parse.quote_plus(valid_stops[0])
        return base_search + query

    origin = urllib.parse.quote_plus(valid_stops[0])
    destination = urllib.parse.quote_plus(valid_stops[-1])

    waypoints_str = ""
    if len(valid_stops) > 2:
        middle_stops = valid_stops[1:-1]
        waypoints_str = "&waypoints=" + urllib.parse.quote_plus("|".join(middle_stops))

    # 組合最終導航網址，預設為開車模式[cite: 10]
    return (
        base_dir
        + "&origin="
        + origin
        + "&destination="
        + destination
        + waypoints_str
        + "&travelmode=driving"
    )