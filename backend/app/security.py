import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import Admin, AdminSession


COOKIE_NAME = "arena_session"
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except Exception:
        return False


def token_hash(token: str) -> str:
    secret = get_settings().app_secret.encode()
    return hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()


def new_session(db: Session, admin: Admin) -> tuple[str, str, AdminSession]:
    settings = get_settings()
    token = secrets.token_urlsafe(36)
    csrf = secrets.token_urlsafe(24)
    session = AdminSession(
        admin_id=admin.id,
        token_hash=token_hash(token),
        csrf_hash=token_hash(csrf),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_hours),
    )
    db.add(session)
    db.commit()
    return token, csrf, session


def current_admin(
    request: Request,
    db: Session = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> Admin:
    if not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="نشست معتبر نیست")
    now = datetime.now(timezone.utc)
    record = db.scalar(
        select(AdminSession).where(
            AdminSession.token_hash == token_hash(session_cookie),
            AdminSession.expires_at > now,
        )
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="نشست منقضی شده است")
    record.last_seen_at = now
    request.state.admin_session = record
    return record.admin


def require_csrf(
    request: Request,
    admin: Admin = Depends(current_admin),
    csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Admin:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        record: AdminSession = request.state.admin_session
        if not csrf or not hmac.compare_digest(record.csrf_hash, token_hash(csrf)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF نامعتبر است")
    return admin


def sign_subscription(user_id: str, version: int) -> str:
    payload = f"{user_id}.{version}"
    signature = hmac.new(
        get_settings().app_secret.encode(), payload.encode(), hashlib.sha256
    ).digest()[:18]
    encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{payload}.{encoded}"


def verify_subscription(token: str) -> tuple[str, int] | None:
    try:
        user_id, version_raw, supplied = token.rsplit(".", 2)
        version = int(version_raw)
    except (ValueError, TypeError):
        return None
    expected = sign_subscription(user_id, version).rsplit(".", 1)[1]
    if not hmac.compare_digest(expected, supplied):
        return None
    return user_id, version


def _fernet() -> Fernet:
    key = hashlib.sha256(get_settings().app_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_payload(value: dict) -> str:
    return _fernet().encrypt(json.dumps(value, separators=(",", ":")).encode()).decode()


def decrypt_payload(value: str) -> dict:
    if not value:
        return {}
    try:
        return json.loads(_fernet().decrypt(value.encode()).decode())
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return {}
