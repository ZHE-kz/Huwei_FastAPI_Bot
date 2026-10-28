import unittest

from config import get_line_account_credentials


class LineAccountConfigTests(unittest.TestCase):
    def test_reads_allowed_account_credentials(self):
        environ = {
            "LINE_ACCOUNT_IDS": "second,museum-bot",
            "LINE_ACCOUNT_SECOND_CHANNEL_SECRET": "secret",
            "LINE_ACCOUNT_SECOND_ACCESS_TOKEN": "token",
        }

        self.assertEqual(
            get_line_account_credentials("second", environ),
            ("secret", "token"),
        )

    def test_rejects_unknown_invalid_or_incomplete_account(self):
        environ = {
            "LINE_ACCOUNT_IDS": "second",
            "LINE_ACCOUNT_SECOND_CHANNEL_SECRET": "secret",
        }

        self.assertIsNone(get_line_account_credentials("unknown", environ))
        self.assertIsNone(get_line_account_credentials("../second", environ))
        self.assertIsNone(get_line_account_credentials("second", environ))


if __name__ == "__main__":
    unittest.main()
