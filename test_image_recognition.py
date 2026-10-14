import sys
import types
import unittest

firestore_client = types.ModuleType("firestore_client")
firestore_client.get_db = lambda: None
sys.modules["firestore_client"] = firestore_client

from itinerary_processor import (
    _build_recognition_context,
    _build_reference_image_urls,
    _image_mime_type,
)


class RecognitionContextTests(unittest.TestCase):
    def test_enabled_article_builds_features_and_alias_mapping(self):
        articles = [
            {
                "title": "虎尾郡役所（雲林布袋戲館）",
                "recognition": {
                    "enabled": True,
                    "aliases": ["虎尾郡役所", "雲林布袋戲館"],
                    "sign_texts": ["雲林布袋戲館"],
                    "visual_features": ["紅磚外牆", "黑瓦斜屋頂"],
                },
            },
            {"title": "停用景點", "recognition": {"enabled": False}},
            {"title": "格式錯誤", "recognition": {"enabled": True, "aliases": None}},
        ]

        knowledge, aliases, lines = _build_recognition_context(articles)

        self.assertEqual(set(knowledge), {"虎尾郡役所（雲林布袋戲館）", "格式錯誤"})
        self.assertEqual(aliases["虎尾郡役所"], "虎尾郡役所（雲林布袋戲館）")
        self.assertIn("紅磚外牆", lines[0])
        self.assertNotIn("停用景點", "\n".join(lines))

    def test_reference_images_are_limited_to_archive_origin(self):
        knowledge = {
            "合同廳舍": {
                "recognition": {
                    "reference_images": [
                        "/uploads/reference.jpg",
                        "https://attacker.example/image.jpg",
                    ]
                }
            }
        }

        self.assertEqual(
            _build_reference_image_urls(knowledge),
            [("合同廳舍", "https://nfu-digital-archive.zheforge.com/uploads/reference.jpg")],
        )
        self.assertEqual(_image_mime_type(b"\x89PNG\r\n\x1a\nrest"), "image/png")


if __name__ == "__main__":
    unittest.main()
