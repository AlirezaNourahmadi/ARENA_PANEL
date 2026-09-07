import base64
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import AccessKey, User
from ..public_url import public_base_url
from ..security import verify_subscription
from ..services.accounts import user_allowed, user_expiry
from ..services.profiles import subscription_document


router = APIRouter(tags=["subscriptions"])


@router.get("/sub/{token}")
def subscription(
    token: str,
    request: Request,
    format: str = Query(default="base64", pattern="^(base64|raw)$"),
    db: Session = Depends(get_db),
) -> Response:
    verified = verify_subscription(token)
    if not verified:
        raise HTTPException(status_code=404, detail="سابسکریپشن معتبر نیست")
    user_id, version = verified
    user = db.scalar(
        select(User).where(User.id == user_id, User.subscription_version == version)
    )
    if not user:
        raise HTTPException(status_code=404, detail="سابسکریپشن معتبر نیست")
    keys = list(
        db.scalars(
            select(AccessKey)
            .where(AccessKey.user_id == user.id)
            .options(joinedload(AccessKey.node))
        )
    )
    allowed, _ = user_allowed(user)
    document = subscription_document(
        user, keys if allowed else [], public_base_url(request)
    )
    body = document if format == "raw" else base64.b64encode(document.encode()).decode()
    expiry = user_expiry(user)
    expiry_epoch = int(expiry.timestamp()) if expiry else 0
    profile_title = base64.b64encode(f"ARENA - {user.name}".encode()).decode()
    headers = {
        "Profile-Title": f"base64:{profile_title}",
        "Profile-Update-Interval": "6",
        "Subscription-Userinfo": (
            f"upload={user.used_up_bytes}; download={user.used_down_bytes}; "
            f"total={user.quota_bytes}; expire={expiry_epoch}"
        ),
        "Content-Disposition": f'attachment; filename="arena-{user.id[:8]}.txt"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return PlainTextResponse(body, headers=headers)
