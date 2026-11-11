import unittest

from itinerary_processor import _archive_article_url


class ArchiveReplyTests(unittest.TestCase):
    def test_archive_url_uses_encoded_slug(self):
        self.assertEqual(
            _archive_article_url({"slug": "article test/一"}),
            "https://nfu-digital-archive.zheforge.com/collection?slug=article%20test%2F%E4%B8%80",
        )

    def test_archive_url_requires_slug(self):
        self.assertEqual(_archive_article_url({}), "")


if __name__ == "__main__":
    unittest.main()
