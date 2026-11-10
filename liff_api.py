import asyncio
import re
import secrets
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from account_links import (
    LinkConflict,
    LinkError,
    LinkExpired,
    consume_link_token,
    get_bot_identity,
    unlink_login,
)
from config import LIFF_COOKIE_SECURE, get_liff_id
from liff_auth import (
    LiffIdentity,
    SESSION_SECONDS,
    create_login_challenge,
    create_session,
    require_identity_account,
    require_liff_identity,
    verify_login_challenge,
    verify_line_id_token,
)
from user_profiles import (
    add_favorite,
    bind_rich_menu,
    clear_history,
    clear_favorites,
    clear_preferences,
    clear_puzzle_state,
    delete_profile,
    delete_favorite,
    get_profile,
    get_puzzle_state,
    list_favorites,
    list_history,
    save_preferences,
)


router = APIRouter(prefix="/api")


class LineAuthRequest(BaseModel):
    id_token: str = Field(min_length=100, max_length=8192)
    account_id: str = Field(default="default", pattern=r"^[a-z0-9-]{1,32}$")
    state: str = Field(min_length=40, max_length=1024)


class LineChallengeRequest(BaseModel):
    account_id: str = Field(default="default", pattern=r"^[a-z0-9-]{1,32}$")
    id_token: str = Field(min_length=100, max_length=8192)


class LinkRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class VoicePreferences(BaseModel):
    speaker: str = Field(default="default", pattern=r"^[\w.-]{1,64}$")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: float = Field(default=0.0, ge=-12, le=12)


class PreferencesRequest(BaseModel):
    language: Literal["zh-TW", "en-US", "ja-JP"] = "zh-TW"
    interests: list[str] = Field(default_factory=list, max_length=10)
    content_depth: Literal["quick", "story", "deep", "field"] = "story"
    preferred_duration: Literal["30m", "1h", "half_day", "full_day"] = "1h"
    transportation: Literal["walking", "bicycle", "transit", "driving"] = "walking"
    walking_preference: Literal["low", "medium", "high"] = "medium"
    stay_minutes: int = Field(default=60, ge=15, le=480)
    voice: VoicePreferences = Field(default_factory=VoicePreferences)


class FavoriteRequest(BaseModel):
    place_id: str = Field(min_length=1, max_length=120)
    title: str = Field(default="", max_length=120)

    @classmethod
    def validate_place_id(cls, value: str) -> str:
        return value.strip()


@router.get("/auth/line/config")
@router.get("/liff/config")
async def liff_config(account_id: str = "default"):
    if not re.fullmatch(r"[a-z0-9-]{1,32}", account_id):
        raise HTTPException(400, "Invalid account")
    liff_id = get_liff_id(account_id)
    if not liff_id:
        raise HTTPException(404, "LIFF account is not configured")
    return {"liff_id": liff_id, "account_id": account_id}


@router.post("/auth/line/challenge")
async def line_auth_challenge(body: LineChallengeRequest, response: Response):
    if not get_liff_id(body.account_id):
        raise HTTPException(404, "LIFF account is not configured")
    state = create_login_challenge(body.account_id, body.id_token)
    response.set_cookie(
        "liff_login_state",
        state,
        max_age=300,
        httponly=True,
        secure=LIFF_COOKIE_SECURE,
        samesite="lax",
        path="/api/auth/line",
    )
    return {"state": state}


@router.post("/auth/line")
async def authenticate_line(
    body: LineAuthRequest,
    response: Response,
    liff_login_state: str = Cookie(default=""),
):
    verify_login_challenge(
        body.state, liff_login_state, body.account_id, body.id_token
    )
    verified = await verify_line_id_token(body.id_token, body.account_id)
    identity = LiffIdentity(body.account_id, str(verified["sub"]))
    profile = await asyncio.to_thread(get_profile, identity)
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        "liff_session",
        create_session(identity),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=LIFF_COOKIE_SECURE,
        samesite="lax",
        path="/api",
    )
    response.set_cookie(
        "liff_csrf",
        csrf_token,
        max_age=SESSION_SECONDS,
        httponly=False,
        secure=LIFF_COOKIE_SECURE,
        samesite="lax",
        path="/api",
    )
    response.delete_cookie("liff_login_state", path="/api/auth/line")
    return {
        "expires_in": SESSION_SECONDS,
        "csrf_token": csrf_token,
        "profile": profile,
        "display_name": str(verified.get("name", ""))[:100],
        "picture_url": str(verified.get("picture", ""))[:2048],
    }


@router.get("/auth/line/csrf")
async def refresh_csrf(
    response: Response,
    account_id: str = "default",
    identity: LiffIdentity = Depends(require_liff_identity),
):
    if not re.fullmatch(r"[a-z0-9-]{1,32}", account_id):
        raise HTTPException(400, "Invalid account")
    require_identity_account(identity, account_id)
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        "liff_csrf",
        csrf_token,
        max_age=SESSION_SECONDS,
        httponly=False,
        secure=LIFF_COOKIE_SECURE,
        samesite="lax",
        path="/api",
    )
    return {"csrf_token": csrf_token}


@router.post("/auth/line/logout", status_code=204)
async def logout_line(
    response: Response,
    _identity: LiffIdentity = Depends(require_liff_identity),
):
    response.delete_cookie("liff_session", path="/api")
    response.delete_cookie("liff_csrf", path="/api")


@router.get("/me")
async def me(identity: LiffIdentity = Depends(require_liff_identity)):
    profile, bot_identity = await asyncio.gather(
        asyncio.to_thread(get_profile, identity),
        asyncio.to_thread(get_bot_identity, identity),
    )
    return {**profile, "linked": bot_identity is not None}


@router.get("/me/preferences")
async def preferences(identity: LiffIdentity = Depends(require_liff_identity)):
    return (await asyncio.to_thread(get_profile, identity))["preferences"]


@router.patch("/me/preferences")
async def update_preferences(
    body: PreferencesRequest,
    identity: LiffIdentity = Depends(require_liff_identity),
):
    saved = await asyncio.to_thread(save_preferences, identity, body.model_dump())
    bot_identity = await asyncio.to_thread(get_bot_identity, identity)
    if bot_identity:
        await bind_rich_menu(bot_identity, saved["language"])
    return saved


@router.delete("/me/preferences", status_code=204)
async def delete_preferences(identity: LiffIdentity = Depends(require_liff_identity)):
    await asyncio.to_thread(clear_preferences, identity)
    return Response(status_code=204)


@router.get("/me/favorites")
async def favorites(identity: LiffIdentity = Depends(require_liff_identity)):
    return await asyncio.to_thread(list_favorites, identity)


@router.post("/me/favorites", status_code=201)
async def create_favorite(
    body: FavoriteRequest,
    identity: LiffIdentity = Depends(require_liff_identity),
):
    place_id = body.place_id.strip()
    if not place_id:
        raise HTTPException(400, "place_id is required")
    return await asyncio.to_thread(
        add_favorite, identity, place_id, body.title.strip()
    )


@router.delete("/me/favorites/{place_id}", status_code=204)
async def remove_favorite(
    place_id: str,
    identity: LiffIdentity = Depends(require_liff_identity),
):
    if not 1 <= len(place_id) <= 120:
        raise HTTPException(400, "Invalid place_id")
    await asyncio.to_thread(delete_favorite, identity, place_id)
    return Response(status_code=204)


@router.get("/me/history")
async def history(identity: LiffIdentity = Depends(require_liff_identity)):
    bot_identity = await asyncio.to_thread(get_bot_identity, identity)
    return await asyncio.to_thread(list_history, bot_identity) if bot_identity else []


@router.delete("/me/history")
async def delete_history(identity: LiffIdentity = Depends(require_liff_identity)):
    bot_identity = await asyncio.to_thread(get_bot_identity, identity)
    deleted = await asyncio.to_thread(clear_history, bot_identity) if bot_identity else 0
    return {"deleted": deleted}


@router.get("/me/puzzles")
async def puzzles(identity: LiffIdentity = Depends(require_liff_identity)):
    bot_identity = await asyncio.to_thread(get_bot_identity, identity)
    return await asyncio.to_thread(get_puzzle_state, bot_identity) if bot_identity else {}


@router.delete("/me/puzzles", status_code=204)
async def delete_puzzles(identity: LiffIdentity = Depends(require_liff_identity)):
    bot_identity = await asyncio.to_thread(get_bot_identity, identity)
    if bot_identity:
        await asyncio.to_thread(clear_puzzle_state, bot_identity)
    return Response(status_code=204)


@router.get("/account-link/status")
async def link_status(identity: LiffIdentity = Depends(require_liff_identity)):
    linked = await asyncio.to_thread(get_bot_identity, identity)
    return {"linked": linked is not None}


@router.post("/account-link/complete")
async def complete_link(
    body: LinkRequest,
    identity: LiffIdentity = Depends(require_liff_identity),
):
    try:
        await asyncio.to_thread(consume_link_token, body.token, identity)
    except LinkExpired:
        raise HTTPException(410, "Link token expired")
    except LinkConflict as error:
        raise HTTPException(409, str(error))
    except LinkError:
        raise HTTPException(400, "Invalid link token")
    return {"linked": True}


@router.delete("/account-link", status_code=204)
@router.delete("/account-link/unlink", status_code=204)
async def remove_link(identity: LiffIdentity = Depends(require_liff_identity)):
    await asyncio.to_thread(unlink_login, identity)
    return Response(status_code=204)


@router.delete("/me", status_code=204)
async def clear_personal_data(identity: LiffIdentity = Depends(require_liff_identity)):
    bot_identity = await asyncio.to_thread(get_bot_identity, identity)
    await asyncio.to_thread(clear_favorites, identity)
    await asyncio.to_thread(delete_profile, identity)
    if bot_identity:
        await asyncio.to_thread(clear_history, bot_identity)
        await asyncio.to_thread(clear_puzzle_state, bot_identity)
    return Response(status_code=204)
