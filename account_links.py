import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from google.api_core.exceptions import Aborted
from google.cloud import firestore

from firestore_client import get_db
from liff_auth import LiffIdentity, owner_key


LINK_COLLECTION = "AccountLinks"
TOKEN_COLLECTION = "AccountLinkTokens"
LINK_TOKEN_SECONDS = 5 * 60


class LinkError(Exception):
    pass


class LinkExpired(LinkError):
    pass


class LinkConflict(LinkError):
    pass


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _bot_document_id(account_id: str, bot_user_id: str) -> str:
    return f"bot_{owner_key(account_id, bot_user_id)}"


def _login_document_id(identity: LiffIdentity) -> str:
    return f"login_{owner_key(identity.account_id, identity.user_id)}"


def create_link_token(account_id: str, bot_user_id: str, now=None) -> str:
    now = now or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    get_db().collection(TOKEN_COLLECTION).document(_token_hash(token)).create(
        {
            "account_id": account_id,
            "bot_user_id": bot_user_id,
            "created_at": now,
            "expires_at": now + timedelta(seconds=LINK_TOKEN_SECONDS),
        }
    )
    return token


def _consume_link_token(transaction, db, token_ref, identity, now):
    token_snapshot = token_ref.get(transaction=transaction)
    if not token_snapshot.exists:
        return "invalid"
    token_data = token_snapshot.to_dict() or {}
    expires_at = token_data.get("expires_at")
    if not expires_at or expires_at <= now:
        transaction.delete(token_ref)
        return "expired"
    if token_data.get("account_id") != identity.account_id:
        return "account_conflict"

    bot_user_id = token_data.get("bot_user_id")
    if not bot_user_id:
        return "invalid"
    bot_ref = db.collection(LINK_COLLECTION).document(
        _bot_document_id(identity.account_id, bot_user_id)
    )
    login_ref = db.collection(LINK_COLLECTION).document(_login_document_id(identity))
    bot_snapshot = bot_ref.get(transaction=transaction)
    login_snapshot = login_ref.get(transaction=transaction)
    bot_data = bot_snapshot.to_dict() if bot_snapshot.exists else {}
    login_data = login_snapshot.to_dict() if login_snapshot.exists else {}
    if (
        bot_data.get("login_user_id") == identity.user_id
        and login_data.get("bot_user_id") == bot_user_id
    ):
        transaction.delete(token_ref)
        return "linked"
    if bot_snapshot.exists and login_snapshot.exists:
        transaction.delete(token_ref)
        return "already_linked"
    if bot_snapshot.exists:
        old_login_id = bot_data.get("login_user_id")
        if old_login_id:
            old_login_ref = db.collection(LINK_COLLECTION).document(
                _login_document_id(LiffIdentity(identity.account_id, old_login_id))
            )
            old_login_snapshot = old_login_ref.get(transaction=transaction)
            old_login_data = old_login_snapshot.to_dict() if old_login_snapshot.exists else {}
            if old_login_data.get("bot_user_id") == bot_user_id:
                transaction.delete(token_ref)
                return "already_linked"
    if login_snapshot.exists:
        old_bot_id = login_data.get("bot_user_id")
        if old_bot_id:
            old_bot_ref = db.collection(LINK_COLLECTION).document(
                _bot_document_id(identity.account_id, old_bot_id)
            )
            old_bot_snapshot = old_bot_ref.get(transaction=transaction)
            old_bot_data = old_bot_snapshot.to_dict() if old_bot_snapshot.exists else {}
            if old_bot_data.get("login_user_id") == identity.user_id:
                transaction.delete(token_ref)
                return "already_linked"

    link_data = {
        "account_id": identity.account_id,
        "bot_user_id": bot_user_id,
        "login_user_id": identity.user_id,
        "created_at": now,
    }
    transaction.set(bot_ref, {**link_data, "role": "bot"})
    transaction.set(login_ref, {**link_data, "role": "login"})
    transaction.delete(token_ref)
    return "linked"


def consume_link_token(token: str, identity: LiffIdentity, now=None):
    if not isinstance(token, str) or not 32 <= len(token) <= 128:
        raise LinkError("Invalid link token")
    now = now or datetime.now(timezone.utc)
    db = get_db()
    transaction = db.transaction()
    token_ref = db.collection(TOKEN_COLLECTION).document(_token_hash(token))
    try:
        result = firestore.transactional(_consume_link_token)(
            transaction, db, token_ref, identity, now
        )
    except Aborted:
        raise LinkConflict("LINE account link changed; request a new link")
    if result == "linked":
        return
    if result == "expired":
        raise LinkExpired("Link token expired")
    if result == "account_conflict":
        raise LinkConflict("Link token belongs to another account")
    if result == "already_linked":
        raise LinkConflict("LINE account is already linked")
    raise LinkError("Invalid link token")


def get_login_identity(account_id: str, bot_user_id: str):
    snapshot = get_db().collection(LINK_COLLECTION).document(
        _bot_document_id(account_id, bot_user_id)
    ).get()
    data = snapshot.to_dict() if snapshot.exists else None
    login_user_id = (data or {}).get("login_user_id")
    return LiffIdentity(account_id, login_user_id) if login_user_id else None


def get_bot_identity(identity: LiffIdentity):
    snapshot = get_db().collection(LINK_COLLECTION).document(
        _login_document_id(identity)
    ).get()
    data = snapshot.to_dict() if snapshot.exists else None
    bot_user_id = (data or {}).get("bot_user_id")
    return LiffIdentity(identity.account_id, bot_user_id) if bot_user_id else None


def _unlink_login(transaction, db, identity) -> bool:
    login_ref = db.collection(LINK_COLLECTION).document(_login_document_id(identity))
    snapshot = login_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False
    data = snapshot.to_dict() or {}
    bot_ref = db.collection(LINK_COLLECTION).document(
        _bot_document_id(identity.account_id, data.get("bot_user_id", ""))
    )
    transaction.delete(login_ref)
    transaction.delete(bot_ref)
    return True


def unlink_login(identity: LiffIdentity) -> bool:
    db = get_db()
    return firestore.transactional(_unlink_login)(db.transaction(), db, identity)


def unlink_bot(account_id: str, bot_user_id: str) -> bool:
    identity = get_login_identity(account_id, bot_user_id)
    return unlink_login(identity) if identity else False
