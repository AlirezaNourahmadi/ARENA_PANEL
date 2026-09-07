from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Admin, AdminSession
from ..schemas import LoginRequest
from ..security import (
    COOKIE_NAME,
    current_admin,
    new_session,
    require_csrf,
    token_hash,
    verify_password,
)
from ..services.audit import audit


router = APIRouter(prefix="/api/auth", tags=["auth"])
CSRF_COOKIE = "arena_csrf"


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    admin = db.scalar(select(Admin).where(Admin.username == payload.username))
    if not admin or not verify_password(admin.password_hash, payload.password):
        audit(db, "auth.login_failed", actor=payload.username)
        db.commit()
        raise HTTPException(status_code=401, detail="نام کاربری یا رمز عبور نادرست است")
    token, csrf, session = new_session(db, admin)
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    audit(db, "auth.login", actor=admin.username, entity_type="admin", entity_id=admin.id)
    db.commit()
    return {"admin": {"id": admin.id, "username": admin.username}, "expires_at": session.expires_at}


@router.get("/session")
def session(admin: Admin = Depends(current_admin)) -> dict:
    return {"admin": {"id": admin.id, "username": admin.username}}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    admin: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        db.execute(delete(AdminSession).where(AdminSession.token_hash == token_hash(cookie)))
    audit(db, "auth.logout", actor=admin.username, entity_type="admin", entity_id=admin.id)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.delete("/expired-sessions")
def delete_expired_sessions(
    admin: Admin = Depends(require_csrf), db: Session = Depends(get_db)
) -> dict:
    result = db.execute(
        delete(AdminSession).where(AdminSession.expires_at <= datetime.now(timezone.utc))
    )
    db.commit()
    return {"deleted": result.rowcount, "actor": admin.username}
