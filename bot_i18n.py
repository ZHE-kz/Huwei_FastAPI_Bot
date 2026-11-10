SUPPORTED_LANGUAGES = {"zh-TW", "en-US", "ja-JP"}

MESSAGES = {
    "zh-TW": {
        "welcome": "汪汪！你好呀！我是你的虎尾專屬導遊。今天想去哪裡走走呢？",
        "tts_error": "🔊 語音生成發生了一點小狀況，請再試一次！",
        "unknown_place": "目前無法確認這個地點，或該景點尚未收錄於數位典藏。",
    },
    "en-US": {
        "welcome": "Hello! I’m your Huwei guide. Where would you like to explore today?",
        "tts_error": "🔊 Voice generation is temporarily unavailable. Please try again.",
        "unknown_place": "I can’t confirm this location, or it has not been added to the archive yet.",
    },
    "ja-JP": {
        "welcome": "こんにちは！虎尾の専属ガイドです。今日はどこを巡りたいですか？",
        "tts_error": "🔊 音声を生成できませんでした。もう一度お試しください。",
        "unknown_place": "この場所を確認できないか、まだデジタルアーカイブに登録されていません。",
    },
}


def normalize_language(language: str) -> str:
    return language if language in SUPPORTED_LANGUAGES else "zh-TW"


def text(language: str, key: str) -> str:
    language = normalize_language(language)
    return MESSAGES.get(language, {}).get(key) or MESSAGES["zh-TW"].get(key, key)


def gemini_language_instruction(language: str) -> str:
    language = normalize_language(language)
    labels = {"zh-TW": "繁體中文", "en-US": "English", "ja-JP": "日本語"}
    instruction = f"Reply in {labels[language]}."
    if language == "zh-TW":
        return instruction + " Preserve historical names and proper nouns exactly as stored in the archive."
    return (
        instruction
        + " For every historical name and proper noun, show its official Latin-script romanization first, "
        "then the original archive name in parentheses, for example: Huwei Tangchang (虎尾糖廠). "
        "Use the archive's official romanization when available; otherwise use romanization without tone marks. "
        "Do not alter the original text or invent names."
    )
