import unittest

from archive_search import build_archive_url, format_archive_context, search_articles


ARTICLES = [
    {
        "title": "虎尾糖廠",
        "category": "history",
        "summary": "記錄糖業發展",
        "content": "虎尾糖廠與五分車的歷史。",
        "slug": "sugar-factory",
    },
    {
        "title": "布袋戲偶",
        "category": "merchant",
        "summary": "傳統工藝館藏",
        "content": "介紹戲偶製作技法。",
        "slug": "puppet",
    },
    {
        "title": "植物標本",
        "category": "nature-museum",
        "summary": "校園自然館藏",
        "content": "保存植物研究資料。",
        "slug": "plant",
    },
]


class ArchiveSearchTests(unittest.TestCase):
    def test_searches_across_all_categories(self):
        self.assertEqual(search_articles(ARTICLES, "戲偶怎麼製作")[0]["slug"], "puppet")
        self.assertEqual(search_articles(ARTICLES, "植物研究")[0]["slug"], "plant")

    def test_title_match_ranks_first(self):
        self.assertEqual(search_articles(ARTICLES, "虎尾糖廠的歷史")[0]["slug"], "sugar-factory")

    def test_category_alias_boosts_requested_collection(self):
        self.assertEqual(search_articles(ARTICLES, "商家館藏有哪些")[0]["slug"], "puppet")
        self.assertEqual(search_articles(ARTICLES, "自然博物館館藏")[0]["slug"], "plant")

    def test_context_contains_clean_content_and_source(self):
        context = format_archive_context([{**ARTICLES[0], "content": "<p>糖業歷史</p>"}])
        self.assertIn("Content: 糖業歷史", context)
        self.assertIn(build_archive_url(ARTICLES[0]), context)


if __name__ == "__main__":
    unittest.main()
