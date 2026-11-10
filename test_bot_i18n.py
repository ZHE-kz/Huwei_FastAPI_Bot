import unittest

from bot_i18n import gemini_language_instruction, text


class BotI18nTests(unittest.TestCase):
    def test_language_and_fallback(self):
        self.assertIn("Huwei", text("en-US", "welcome"))
        self.assertEqual(text("unknown", "unknown_place"), text("zh-TW", "unknown_place"))

    def test_prompt_formats_historical_names(self):
        translated = gemini_language_instruction("ja-JP")
        self.assertIn("official Latin-script romanization first", translated)
        self.assertIn("Huwei Tangchang (虎尾糖廠)", translated)
        self.assertIn("exactly as stored", gemini_language_instruction("zh-TW"))


if __name__ == "__main__":
    unittest.main()
