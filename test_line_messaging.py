import unittest

from line_messaging import LINE_TEXT_LIMIT, fit_line_reply_payload, split_line_text


class LineMessagingTests(unittest.TestCase):
    def test_splits_long_text_on_sentence_boundary(self):
        chunks = split_line_text(("虎尾糖廠。" * 1000))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(chunk) <= LINE_TEXT_LIMIT for chunk in chunks))

    def test_reply_never_exceeds_line_limits_and_keeps_video(self):
        payload = {
            "replyToken": "reply-token",
            "messages": [
                {"type": "text", "text": "內容。" * 10000, "quickReply": {"items": []}},
                {"type": "video", "originalContentUrl": "https://example.com/video.mp4"},
            ],
        }
        fitted = fit_line_reply_payload(payload)
        self.assertLessEqual(len(fitted["messages"]), 5)
        self.assertTrue(any(message["type"] == "video" for message in fitted["messages"]))
        self.assertTrue(
            all(len(message["text"]) <= LINE_TEXT_LIMIT for message in fitted["messages"] if message["type"] == "text")
        )


if __name__ == "__main__":
    unittest.main()
