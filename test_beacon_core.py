import sys
import types
import unittest
from datetime import datetime, timedelta, timezone

firestore_client = types.ModuleType("firestore_client")
firestore_client.get_db = lambda: None
sys.modules["firestore_client"] = firestore_client

from beacon_core import (
    build_beacon_message,
    cooldown_document_id,
    is_within_cooldown,
    normalize_beacon_config,
    parse_beacon_event,
)


class BeaconCoreTests(unittest.TestCase):
    def test_parses_valid_beacon_event(self):
        event = {"type": "beacon", "beacon": {"hwid": "0123456789", "type": "enter"}}

        self.assertEqual(parse_beacon_event(event), ("0123456789", "enter"))

    def test_rejects_invalid_or_non_beacon_event(self):
        self.assertIsNone(parse_beacon_event({"type": "message"}))
        self.assertIsNone(
            parse_beacon_event({"type": "beacon", "beacon": {"hwid": "../x", "type": "enter"}})
        )
        self.assertIsNone(
            parse_beacon_event({"type": "beacon", "beacon": {"hwid": "abc", "type": "other"}})
        )

    def test_normalizes_config_and_builds_default_messages(self):
        config = normalize_beacon_config(
            {"enabled": True, "place_name": " 虎尾驛 ", "cooldown_seconds": "600"}
        )

        self.assertTrue(config["enabled"])
        self.assertEqual(config["cooldown_seconds"], 600)
        self.assertEqual(build_beacon_message(config, "enter"), "你已抵達「虎尾驛」！")
        self.assertEqual(build_beacon_message(config, "leave"), "你已離開「虎尾驛」。")

    def test_custom_message_and_cooldown_key(self):
        config = normalize_beacon_config(
            {
                "enabled": True,
                "message": "歡迎抵達！",
                "leave_message": "期待再見！",
            }
        )

        self.assertEqual(build_beacon_message(config, "banner"), "歡迎抵達！")
        self.assertEqual(build_beacon_message(config, "leave"), "期待再見！")
        first = cooldown_document_id("second", "U1", "abc", "enter")
        self.assertEqual(first, cooldown_document_id("second", "U1", "abc", "enter"))
        self.assertNotEqual(first, cooldown_document_id("default", "U1", "abc", "enter"))

    def test_duplicate_notification_is_blocked_during_cooldown(self):
        now = datetime.now(timezone.utc)

        self.assertTrue(is_within_cooldown(now - timedelta(seconds=10), now, 300))
        self.assertFalse(is_within_cooldown(now - timedelta(seconds=301), now, 300))
        self.assertFalse(is_within_cooldown(None, now, 300))


if __name__ == "__main__":
    unittest.main()
