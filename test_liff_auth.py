import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

import liff_auth
from liff_auth import LiffIdentity


class LiffAuthTests(unittest.TestCase):
    def test_signed_session_round_trip_and_tamper_rejection(self):
        identity = LiffIdentity("second", "private-user")
        with patch.object(liff_auth, "LIFF_SESSION_SECRET", "test-only-secret"):
            token = liff_auth.create_session(identity, now=100)
            self.assertEqual(liff_auth.verify_session(token, now=101), identity)
            with self.assertRaises(HTTPException):
                liff_auth.verify_session(token + "x", now=101)

    def test_line_identity_comes_from_verified_token(self):
        result = liff_auth.validate_line_identity(
            {
                "iss": "https://access.line.me",
                "aud": "login-channel",
                "sub": "verified-line-user",
                "nonce": "line-managed-nonce",
            },
            "login-channel",
        )
        self.assertEqual(result["sub"], "verified-line-user")

    def test_wrong_login_channel_is_rejected(self):
        with self.assertRaises(HTTPException):
            liff_auth.validate_line_identity(
                {
                    "iss": "https://access.line.me",
                    "aud": "other-channel",
                    "sub": "verified-line-user",
                    "nonce": "line-managed-nonce",
                },
                "login-channel",
            )

    def test_login_challenge_binds_cookie_and_account(self):
        with patch.object(liff_auth, "LIFF_SESSION_SECRET", "test-only-secret"):
            id_token = "t" * 100
            state = liff_auth.create_login_challenge("default", id_token, now=100)
            liff_auth.verify_login_challenge(
                state, state, "default", id_token, now=101
            )
            with self.assertRaises(HTTPException):
                liff_auth.verify_login_challenge(
                    state, state, "second", id_token, now=101
                )
            with self.assertRaises(HTTPException):
                liff_auth.verify_login_challenge(
                    state, state, "default", "x" * 100, now=101
                )

    def test_missing_issuer_or_nonce_is_rejected(self):
        with self.assertRaises(HTTPException):
            liff_auth.validate_line_identity(
                {"aud": "login-channel", "sub": "user"},
                "login-channel",
            )

    def test_private_mutation_requires_matching_csrf(self):
        request = Request({"type": "http", "method": "PATCH", "headers": []})
        with patch.object(liff_auth, "LIFF_SESSION_SECRET", "test-only-secret"):
            session = liff_auth.create_session(LiffIdentity("default", "user"))
            with self.assertRaises(HTTPException):
                liff_auth.require_liff_identity(request, session, "cookie", "other")
            identity = liff_auth.require_liff_identity(
                request, session, "csrf", "csrf"
            )
        self.assertEqual(identity.user_id, "user")

    def test_session_cannot_be_reused_for_another_bot_account(self):
        identity = LiffIdentity("default", "user")
        liff_auth.require_identity_account(identity, "default")
        with self.assertRaises(HTTPException) as context:
            liff_auth.require_identity_account(identity, "second")
        self.assertEqual(context.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
