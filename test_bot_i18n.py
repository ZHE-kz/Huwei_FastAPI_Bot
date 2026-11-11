import unittest

from bot_i18n import gemini_history_instruction, gemini_language_instruction, text
from prompt_store import PROMPTS


class BotI18nTests(unittest.TestCase):
    def test_language_and_fallback(self):
        self.assertIn("Huwei", text("en-US", "welcome"))
        self.assertEqual(text("unknown", "unknown_place"), text("zh-TW", "unknown_place"))

    def test_prompt_formats_historical_names(self):
        translated = gemini_language_instruction("ja-JP")
        self.assertIn("official Latin-script romanization first", translated)
        self.assertIn("Huwei Tangchang (虎尾糖廠)", translated)
        self.assertIn("exactly as stored", gemini_language_instruction("zh-TW"))

    def test_prompts_do_not_force_traditional_chinese(self):
        self.assertNotIn("reply warmly in traditional Chinese", PROMPTS["itinerary"]["content"])
        self.assertNotIn("請用繁體中文", PROMPTS["image_identification"]["content"])

    def test_easter_egg_uses_selected_language(self):
        self.assertIn("System anomaly", text("en-US", "sugar_factory_easter_egg"))
        self.assertIn("システム異常", text("ja-JP", "sugar_factory_easter_egg"))

    def test_history_prompt_enforces_language_and_name_order(self):
        instruction = gemini_history_instruction("en-US")
        self.assertIn("Write every sentence", instruction)
        self.assertIn("Huwei (虎尾), never 虎尾 (Huwei)", instruction)


if __name__ == "__main__":
    unittest.main()
