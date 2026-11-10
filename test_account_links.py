import hashlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.modules.setdefault("firestore_client", types.SimpleNamespace(get_db=lambda: None))

import account_links
from liff_auth import LiffIdentity


class _Snapshot:
    def __init__(self, value):
        self.value = value
        self.exists = value is not None

    def to_dict(self):
        return self.value


class _Document:
    def __init__(self):
        self.value = None

    def create(self, value):
        if self.value is not None:
            raise RuntimeError("exists")
        self.value = value

    def get(self, transaction=None):
        return _Snapshot(self.value)


class _Collection:
    def __init__(self):
        self.documents = {}

    def document(self, key):
        return self.documents.setdefault(key, _Document())


class _Transaction:
    def __init__(self):
        self.operations = []

    def set(self, ref, value):
        self.operations.append(("set", ref, value))

    def delete(self, ref):
        self.operations.append(("delete", ref, None))

    def commit(self):
        for action, ref, value in self.operations:
            ref.value = value if action == "set" else None


class _DB:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, _Collection())

    def transaction(self):
        return _Transaction()


def _transactional(function):
    def run(transaction, *args):
        result = function(transaction, *args)
        transaction.commit()
        return result

    return run


class AccountLinkTests(unittest.TestCase):
    def test_token_is_hashed_consumed_once_and_links_cross_provider_ids(self):
        database = _DB()
        now = datetime.now(timezone.utc)
        raw_token = "a" * 43
        identity = LiffIdentity("default", "login-provider-user")
        with patch.object(account_links, "get_db", return_value=database), patch.object(
            account_links.firestore, "transactional", _transactional
        ), patch.object(
            account_links.secrets, "token_urlsafe", return_value=raw_token
        ):
            token = account_links.create_link_token("default", "bot-provider-user", now)
            token_docs = database.collection(account_links.TOKEN_COLLECTION).documents
            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            self.assertIn(token_hash, token_docs)
            self.assertNotIn(raw_token, repr(token_docs[token_hash].value))
            account_links.consume_link_token(token, identity, now + timedelta(seconds=1))
            self.assertEqual(
                account_links.get_login_identity("default", "bot-provider-user"), identity
            )
            with self.assertRaises(account_links.LinkError):
                account_links.consume_link_token(token, identity, now + timedelta(seconds=2))

    def test_expired_token_and_duplicate_login_are_rejected(self):
        database = _DB()
        now = datetime.now(timezone.utc)
        with patch.object(account_links, "get_db", return_value=database), patch.object(
            account_links.firestore, "transactional", _transactional
        ):
            with patch.object(account_links.secrets, "token_urlsafe", return_value="b" * 43):
                expired = account_links.create_link_token("default", "bot-1", now)
            with self.assertRaises(account_links.LinkExpired):
                account_links.consume_link_token(expired, LiffIdentity("default", "login-1"), now + timedelta(minutes=6))

            with patch.object(account_links.secrets, "token_urlsafe", return_value="c" * 43):
                first = account_links.create_link_token("default", "bot-1", now)
            identity = LiffIdentity("default", "login-1")
            account_links.consume_link_token(first, identity, now + timedelta(seconds=1))
            with patch.object(account_links.secrets, "token_urlsafe", return_value="d" * 43):
                second = account_links.create_link_token("default", "bot-2", now)
            with self.assertRaises(account_links.LinkConflict):
                account_links.consume_link_token(second, identity, now + timedelta(seconds=2))

    def test_linking_the_same_accounts_again_is_idempotent(self):
        database = _DB()
        now = datetime.now(timezone.utc)
        identity = LiffIdentity("default", "login-1")
        with patch.object(account_links, "get_db", return_value=database), patch.object(
            account_links.firestore, "transactional", _transactional
        ):
            with patch.object(account_links.secrets, "token_urlsafe", return_value="e" * 43):
                first = account_links.create_link_token("default", "bot-1", now)
            account_links.consume_link_token(first, identity, now + timedelta(seconds=1))

            with patch.object(account_links.secrets, "token_urlsafe", return_value="f" * 43):
                second = account_links.create_link_token("default", "bot-1", now)
            account_links.consume_link_token(second, identity, now + timedelta(seconds=2))

            self.assertEqual(
                account_links.get_login_identity("default", "bot-1"), identity
            )

    def test_orphaned_login_index_is_repaired(self):
        database = _DB()
        now = datetime.now(timezone.utc)
        identity = LiffIdentity("second", "login-1")
        login_ref = database.collection(account_links.LINK_COLLECTION).document(
            account_links._login_document_id(identity)
        )
        login_ref.value = {
            "account_id": "second",
            "bot_user_id": "old-bot",
            "login_user_id": "login-1",
            "role": "login",
        }
        with patch.object(account_links, "get_db", return_value=database), patch.object(
            account_links.firestore, "transactional", _transactional
        ), patch.object(account_links.secrets, "token_urlsafe", return_value="g" * 43):
            token = account_links.create_link_token("second", "new-bot", now)
            account_links.consume_link_token(token, identity, now + timedelta(seconds=1))
            self.assertEqual(
                account_links.get_login_identity("second", "new-bot"), identity
            )


if __name__ == "__main__":
    unittest.main()
