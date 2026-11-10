import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("firestore_client", types.SimpleNamespace(get_db=lambda: None))

from liff_auth import LiffIdentity, owner_key
import user_profiles


class _Document:
    def __init__(self):
        self.value = None

    def set(self, value, merge=False):
        self.value = value


class _Collection:
    def __init__(self):
        self.documents = {}

    def document(self, key):
        return self.documents.setdefault(key, _Document())


class _DB:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, _Collection())


class UserProfileTests(unittest.TestCase):
    def test_account_data_isolation_and_legacy_puzzle_key(self):
        first = LiffIdentity("default", "same-user")
        second = LiffIdentity("second", "same-user")
        self.assertNotEqual(user_profiles.profile_document_id(first), user_profiles.profile_document_id(second))
        self.assertEqual(user_profiles.puzzle_state_document_id(first), "same-user")
        self.assertEqual(user_profiles.puzzle_state_document_id(second), owner_key("second", "same-user"))

    def test_preferences_are_normalized_and_saved_without_raw_user_id(self):
        database = _DB()
        identity = LiffIdentity("second", "sensitive-user")
        with patch.object(user_profiles, "get_db", return_value=database):
            saved = user_profiles.save_preferences(
                identity,
                {
                    "language": "invalid",
                    "content_depth": "invalid",
                    "preferred_duration": "invalid",
                    "stay_minutes": 999,
                    "voice": {"speed": 9},
                },
            )
        self.assertEqual(saved["language"], "zh-TW")
        self.assertEqual(saved["content_depth"], "story")
        self.assertEqual(saved["preferred_duration"], "1h")
        self.assertEqual(saved["stay_minutes"], 480)
        stored = database.collection("UserProfiles").document(user_profiles.profile_document_id(identity)).value
        self.assertNotIn("user_id", stored)
        self.assertEqual(stored["account_id"], "second")


if __name__ == "__main__":
    unittest.main()
