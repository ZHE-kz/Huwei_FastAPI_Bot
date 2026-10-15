import unittest
import sys
import types
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient

firestore_stub = types.ModuleType("firestore_client")
firestore_stub.get_db = lambda: None
sys.modules["firestore_client"] = firestore_stub
puzzle_stub = types.ModuleType("puzzle_core")
puzzle_stub.PUZZLE_COLLECTION = "PuzzleDB"
puzzle_stub.force_clear_puzzle_cache = lambda: None
puzzle_stub.load_puzzle_config = lambda: None
puzzle_stub.normalize_stage = lambda stage_id, data: {"stage_id": stage_id, **data}
sys.modules["puzzle_core"] = puzzle_stub
prompt_stub = types.ModuleType("prompt_store")
prompt_stub.list_prompts = lambda: []
prompt_stub.save_prompt = lambda *args, **kwargs: False
sys.modules["prompt_store"] = prompt_stub

import admin_tools


class AdminOAuthTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(admin_tools.router)
        self.client = TestClient(app, base_url="https://linebot.zheforge.com")
        self.config = patch.multiple(
            admin_tools,
            PUZZLE_ADMIN_SECRET="test-signing-secret",
            PUZZLE_ADMIN_BASE_URL="https://linebot.zheforge.com",
            PUZZLE_ADMIN_EMAILS={"admin@example.com"},
            GOOGLE_CLIENT_ID="google-id",
            GOOGLE_CLIENT_SECRET="google-secret",
            GITHUB_CLIENT_ID="github-id",
            GITHUB_CLIENT_SECRET="github-secret",
        )
        self.config.start()

    def tearDown(self):
        self.config.stop()

    def test_google_and_github_login(self):
        async def allowed_email(provider, code, redirect_uri):
            self.assertIn(provider, {"google", "github"})
            self.assertEqual(code, "test-code")
            self.assertTrue(redirect_uri.endswith(f"/{provider}/callback"))
            return "admin@example.com"

        with patch.object(admin_tools, "oauth_email", allowed_email):
            for provider in ("google", "github"):
                start = self.client.get(f"/admin/puzzles/login/{provider}", follow_redirects=False)
                self.assertEqual(start.status_code, 303)
                state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
                callback = self.client.get(
                    f"/admin/puzzles/oauth/{provider}/callback",
                    params={"code": "test-code", "state": state},
                    follow_redirects=False,
                )
                self.assertEqual(callback.status_code, 303)
                self.assertEqual(callback.headers["location"], "/admin/puzzles")

    def test_rejects_invalid_state(self):
        response = self.client.get(
            "/admin/puzzles/oauth/google/callback",
            params={"code": "test-code", "state": "invalid"},
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_email_outside_allowlist(self):
        async def unknown_email(provider, code, redirect_uri):
            return "other@example.com"

        with patch.object(admin_tools, "oauth_email", unknown_email):
            start = self.client.get("/admin/puzzles/login/google", follow_redirects=False)
            state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
            response = self.client.get(
                "/admin/puzzles/oauth/google/callback",
                params={"code": "test-code", "state": state},
            )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
