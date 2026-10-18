import hashlib
import hmac
import unittest

from beacon_smoke_test import build_beacon_payload, create_signature


class BeaconSmokeTests(unittest.TestCase):
    def test_builds_line_beacon_event(self):
        payload = build_beacon_payload("0123456789", "enter", "U123")
        event = payload["events"][0]

        self.assertEqual(event["type"], "beacon")
        self.assertEqual(event["source"]["userId"], "U123")
        self.assertEqual(event["beacon"], {"hwid": "0123456789", "type": "enter"})

    def test_rejects_invalid_beacon_type(self):
        with self.assertRaises(ValueError):
            build_beacon_payload("0123456789", "invalid")

    def test_signature_matches_line_algorithm(self):
        body = b'{"events":[]}'
        expected = hmac.new(b"secret", body, hashlib.sha256).digest()

        import base64

        self.assertEqual(create_signature(body, "secret"), base64.b64encode(expected).decode())


if __name__ == "__main__":
    unittest.main()
