SUPPORTED_LANGUAGES = {"zh-TW", "en-US", "ja-JP"}

MESSAGES = {
    "zh-TW": {
        "welcome": "汪汪！你好呀！我是你的虎尾專屬導遊。今天想去哪裡走走呢？",
        "tts_error": "🔊 語音生成發生了一點小狀況，請再試一次！",
        "unknown_place": "目前無法確認這個地點，或該景點尚未收錄於數位典藏。",
        "sugar_factory_easter_egg": (
            "\n\n─── ⚠️ 系統異常：收到一則加密通訊 ───\n\n"
            "「滋...滋... 你好，我是壁虎。既然你來到了糖廠，看來你就是我要找的人。\n"
            "昨晚，虎尾糖廠珍貴的『黃金蔗糖配方』被偷走了！\n"
            "現場只留下了一串奇怪的腳印，一直延伸到旁邊的舊鐵橋...\n"
            "你願意幫我找回配方嗎？如果願意，請對我輸入：『壁虎我來幫忙』！」"
        ),
    },
    "en-US": {
        "welcome": "Hello! I’m your Huwei guide. Where would you like to explore today?",
        "tts_error": "🔊 Voice generation is temporarily unavailable. Please try again.",
        "unknown_place": "I can’t confirm this location, or it has not been added to the archive yet.",
        "sugar_factory_easter_egg": (
            "\n\n─── ⚠️ System anomaly: encrypted transmission received ───\n\n"
            "‘Static... Hello, I’m Gecko. Since you reached Huwei Tangchang (虎尾糖廠), you must be the person I need.\n"
            "Its precious Golden Sugarcane Formula was stolen last night!\n"
            "Only strange footprints remain, leading toward the old iron bridge...\n"
            "Will you help recover it? If yes, send: 壁虎我來幫忙’"
        ),
    },
    "ja-JP": {
        "welcome": "こんにちは！虎尾の専属ガイドです。今日はどこを巡りたいですか？",
        "tts_error": "🔊 音声を生成できませんでした。もう一度お試しください。",
        "unknown_place": "この場所を確認できないか、まだデジタルアーカイブに登録されていません。",
        "sugar_factory_easter_egg": (
            "\n\n─── ⚠️ システム異常：暗号通信を受信 ───\n\n"
            "「ザザッ……こんにちは、ヤモリです。Huwei Tangchang（虎尾糖廠）まで来たあなたが、探していた人ですね。\n"
            "昨夜、貴重な『黄金サトウキビのレシピ』が盗まれました！\n"
            "現場には奇妙な足跡だけが残り、古い鉄橋へ続いています……\n"
            "取り戻すのを手伝ってくれますか？よければ『壁虎我來幫忙』と送ってください。」"
        ),
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


def gemini_history_instruction(language: str) -> str:
    language = normalize_language(language)
    if language == "en-US":
        return (
            "[MANDATORY OUTPUT LANGUAGE]\n"
            "Write every sentence of the visitor-facing introduction in English. "
            "Translate all archive prose into English. Chinese text may appear only as the original "
            "proper noun in parentheses after its official English or Latin-script romanization. "
            "Always use the order Huwei (虎尾), never 虎尾 (Huwei). "
            "Do not invent names or facts."
        )
    if language == "ja-JP":
        return (
            "[MANDATORY OUTPUT LANGUAGE]\n"
            "来訪者向けの紹介文は、すべて日本語で書いてください。典藏本文も日本語にしてください。"
            "中国語の原文は、固有名詞の公式ローマ字表記の直後に括弧でのみ表示してください。"
            "必ず Huwei（虎尾）の順にし、虎尾（Huwei）の順にはしないでください。"
            "名称や事実を創作しないでください。"
        )
    return (
        "[必要輸出語言]\n請以繁體中文撰寫完整導覽介紹，並保持典藏中的歷史名稱與專有名詞原文。"
    )
