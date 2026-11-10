import unittest

from liff_security import protect_profile_headers


class LiffSecurityHeadersTests(unittest.TestCase):
    def test_private_api_disables_caching_and_adds_security_headers(self):
        headers = {}
        protect_profile_headers("/api/me", headers)

        self.assertEqual(headers["Cache-Control"], "private, no-store")
        self.assertEqual(headers["Pragma"], "no-cache")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")

    def test_unrelated_routes_are_unchanged(self):
        headers = {}
        protect_profile_headers("/health", headers)
        self.assertEqual(headers, {})


if __name__ == "__main__":
    unittest.main()
