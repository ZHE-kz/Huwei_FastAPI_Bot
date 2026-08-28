import re
import time

from firestore_client import get_db


PROMPT_COLLECTION = "BotPrompts"
MAX_PROMPT_LENGTH = 20_000
PROMPTS = {
    "itinerary": {
        "title": "行程規劃與意圖判斷",
        "variables": ["history_context", "current_time", "current_day", "weather", "user_text", "whitelist"],
        "content": """[Role] Huwei Tour Guide Agent (Professional, Friendly & Strategic)
{{history_context}}[Crucial Context]
- Current Time: {{current_time}} ({{current_day}})
- Weather: {{weather}}

[Rules]
1. WHITELIST ONLY: For itineraries or locations, you must ONLY use places provided in the [Whitelist Database].
2. INTENT DETECTION:
   - If user is just greeting, chatting, or asking casual questions (e.g., '你好', '早安', '你是誰'), choose CHAT and reply warmly in traditional Chinese.
   - If user asks for a trip, route, or multiple places, choose ITINERARY.
   - If user asks for a single place recommendation, choose LOCATION.
3. ITINERARY SIZE: Use 4 to 8 actual places. Never add a non-place ending such as 'end of trip' as a stop.
4. Output raw JSON only.

[Query] {{user_text}}
[Whitelist Database]
{{whitelist}}
[Format]
You MUST strictly output ONE of the following JSON structures based on intent:

IF CHAT:
{"type":"chat","text":"[Your friendly conversational response]"}

IF ITINERARY:
{"type":"itinerary","title":"...","total_distance":"...","stops":[{"time":"HH:MM","location":"...","note":"..."}]}

IF LOCATION:
{"type":"location","name":"[Place Name]","category":"...","time":"[Opening hours]","description":"[A rich, friendly description]"}""",
    },
    "image_identification": {
        "title": "圖片景點辨識",
        "variables": ["places_str"],
        "content": """請仔細觀察這張圖片中的建築、招牌、街景、文字與空間特徵。

我們有一個「專屬景點白名單」：
- {{places_str}}

請你扮演極度嚴格的鑑定官：
1. 判斷這張照片是否明確屬於上述白名單中的「某一個地點」。
2. 如果非常確定，請在第一行直接且只能輸出：「鑑定結果：[地點名稱]」。
3. 如果只是普通街景、特徵不足、或不在白名單內，請在第一行輸出：「鑑定結果：未知地點」。
4. 第二行開始，請用繁體中文詳細描述你看到了什麼特徵，以及你的判斷依據。""",
    },
    "history_intro": {
        "title": "歷史內容潤飾",
        "variables": ["best_place", "local_knowledge"],
        "content": """你是一個專業、熱情的在地導遊。請根據以下關於「{{best_place}}」的歷史背景知識，為遊客寫一段生動、引人入勝的景點導覽介紹。

⚠️【最高限制原則】：
1. 輸出的文字一定要精簡洗鍊，且內容要盡可能地還原資料庫的內容不要加過多的修飾
2. 語氣要文青、親切，充滿故事感，讓人一聽就想深入探索。

【景點背景知識】：
{{local_knowledge}}""",
    },
    "puzzle_image": {
        "title": "解謎圖片判斷",
        "variables": ["vision_target"],
        "content": """請檢查照片是否符合目標：{{vision_target}}。符合只回答「辨識成功」；不符合請簡述原因。請嚴格判斷。""",
    },
}

_cache = None
_cache_until = 0
_variable_pattern = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


def force_clear_prompt_cache():
    global _cache, _cache_until
    _cache = None
    _cache_until = 0


def get_prompts():
    global _cache, _cache_until
    if _cache is not None and time.monotonic() < _cache_until:
        return _cache

    contents = {prompt_id: data["content"] for prompt_id, data in PROMPTS.items()}
    try:
        for document in get_db().collection(PROMPT_COLLECTION).stream():
            if document.id in contents:
                content = str((document.to_dict() or {}).get("content", ""))
                if content.strip():
                    contents[document.id] = content
    except Exception as error:
        print(f"[PROMPT] 讀取 Firestore 失敗，使用預設值: {error}")

    _cache = contents
    _cache_until = time.monotonic() + 300
    return contents


def list_prompts():
    contents = get_prompts()
    return [
        {
            "id": prompt_id,
            "title": data["title"],
            "variables": data["variables"],
            "content": contents[prompt_id],
        }
        for prompt_id, data in PROMPTS.items()
    ]


def save_prompt(prompt_id, content):
    if prompt_id not in PROMPTS:
        raise ValueError("未知的 Prompt ID")
    if not content.strip():
        raise ValueError("Prompt 不可空白")
    if len(content) > MAX_PROMPT_LENGTH:
        raise ValueError(f"Prompt 不可超過 {MAX_PROMPT_LENGTH} 字")

    allowed = set(PROMPTS[prompt_id]["variables"])
    variables = set(_variable_pattern.findall(content))
    missing = allowed - variables
    unknown = variables - allowed
    if missing:
        raise ValueError("缺少必要變數：" + ", ".join(sorted(missing)))
    if unknown:
        raise ValueError("包含未知變數：" + ", ".join(sorted(unknown)))

    get_db().collection(PROMPT_COLLECTION).document(prompt_id).set(
        {"content": content, "updated_at": time.time()}
    )
    force_clear_prompt_cache()


def render_prompt(prompt_id, **values):
    template = get_prompts().get(prompt_id, PROMPTS[prompt_id]["content"])
    return _variable_pattern.sub(lambda match: str(values.get(match.group(1), "")), template)
