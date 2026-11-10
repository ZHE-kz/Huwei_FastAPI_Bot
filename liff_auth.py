import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

import httpx
from fastapi import Cookie, Header, HTTPException, Request

from config import LIFF_SESSION_SECRET, get_line_login_channel_id


LINE_ID_TOKEN_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"
SESSION_SECONDS = 8 * 60 * 60
LOGIN_CHALLENGE_SECONDS = 5 * 60
LINE_ISSUER = "https://access.line.me"


@dataclass(frozen=True)
class LiffIdentity:
    account_id: str
    user_id: str


def owner_key(account_id: str, user_id: str) -> str:
    return hashlib.sha256(f"{account_id}\0{user_id}".encode()).hexdigest()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_session(identity: LiffIdentity, now=None) -> str:
    if not LIFF_SESSION_SECRET:
        raise RuntimeError("LIFF_SESSION_SECRET is not configured")
    issued_at = int(time.time() if now is None else now)
    payload = _encode(
        json.dumps(
            {
                "account_id": identity.account_id,
                "sub": identity.user_id,
                "iat": issued_at,
                "exp": issued_at + SESSION_SECONDS,
            },
            separators=(",", ":"),
        ).encode()
    )
    signature = _encode(
        hmac.new(LIFF_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    )
    return f"{payload}.{signature}"


def id_token_digest(id_token: str) -> str:
    return hashlib.sha256(id_token.encode()).hexdigest()


def create_login_challenge(account_id: str, id_token: str, now=None) -> str:
    if not LIFF_SESSION_SECRET:
        raise RuntimeError("LIFF_SESSION_SECRET is not configured")
    if not isinstance(id_token, str) or not 100 <= len(id_token) <= 8192:
        raise ValueError("Invalid LINE ID token")
    issued_at = int(time.time() if now is None else now)
    payload = _encode(
        json.dumps(
            {
                "account_id": account_id,
                "nonce": secrets.token_urlsafe(24),
                "id_token_hash": id_token_digest(id_token),
                "exp": issued_at + LOGIN_CHALLENGE_SECONDS,
            },
            separators=(",", ":"),
        ).encode()
    )
    signature = _encode(
        hmac.new(LIFF_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    )
    return f"{payload}.{signature}"


def verify_login_challenge(
    challenge: str, cookie_value: str, account_id: str, id_token: str, now=None
):
    if not challenge or not cookie_value or not hmac.compare_digest(challenge, cookie_value):
        raise HTTPException(403, "Invalid login state")
    if not LIFF_SESSION_SECRET:
        raise HTTPException(503, "LIFF authentication is not configured")
    try:
        payload, signature = challenge.split(".", 1)
        expected = _encode(
            hmac.new(LIFF_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        data = json.loads(_decode(payload))
        current_time = int(time.time() if now is None else now)
        if data.get("account_id") != account_id or int(data["exp"]) <= current_time:
            raise ValueError
        nonce = data.get("nonce")
        token_hash = data.get("id_token_hash")
        if (
            not isinstance(nonce, str)
            or not nonce
            or not isinstance(token_hash, str)
            or not hmac.compare_digest(token_hash, id_token_digest(id_token))
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(403, "Invalid or expired login state")


def verify_session(token: str, now=None) -> LiffIdentity:
    if not LIFF_SESSION_SECRET:
        raise HTTPException(503, "LIFF authentication is not configured")
    try:
        payload, signature = token.split(".", 1)
        expected = _encode(
            hmac.new(LIFF_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        data = json.loads(_decode(payload))
        current_time = int(time.time() if now is None else now)
        if int(data["exp"]) <= current_time:
            raise ValueError
        account_id = str(data["account_id"])
        user_id = str(data["sub"])
        if not account_id or not user_id:
            raise ValueError
        return LiffIdentity(account_id, user_id)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(401, "Invalid or expired session")


async def verify_line_id_token(id_token: str, account_id: str) -> dict:
    channel_id = get_line_login_channel_id(account_id)
    if not channel_id:
        raise HTTPException(404, "LIFF account is not configured")
    if not isinstance(id_token, str) or not 100 <= len(id_token) <= 8192:
        raise HTTPException(400, "Invalid ID token")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                LINE_ID_TOKEN_VERIFY_URL,
                data={"id_token": id_token, "client_id": channel_id},
            )
    except httpx.HTTPError:
        raise HTTPException(503, "LINE authentication is temporarily unavailable")
    if response.status_code != 200:
        raise HTTPException(401, "LINE ID token verification failed")
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(503, "LINE authentication returned an invalid response")
    return validate_line_identity(data, channel_id)


def validate_line_identity(data: dict, channel_id: str) -> dict:
    if (
        data.get("iss") != LINE_ISSUER
        or data.get("aud") != channel_id
        or not data.get("sub")
    ):
        raise HTTPException(401, "LINE ID token verification failed")
    if "nonce" in data and not isinstance(data["nonce"], str):
        raise HTTPException(401, "LINE ID token verification failed")
    return data


def require_liff_identity(
    request: Request,
    liff_session: str = Cookie(default=""),
    liff_csrf: str = Cookie(default=""),
    x_csrf_token: str = Header(default=""),
) -> LiffIdentity:
    if not liff_session:
        raise HTTPException(401, "Authentication required")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
        not liff_csrf
        or not x_csrf_token
        or not hmac.compare_digest(liff_csrf, x_csrf_token)
    ):
        raise HTTPException(403, "CSRF validation failed")
    return verify_session(liff_session)


def require_identity_account(identity: LiffIdentity, account_id: str) -> None:
    if identity.account_id != account_id:
        raise HTTPException(401, "Session account mismatch")
