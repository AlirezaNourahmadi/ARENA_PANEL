import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from ..config import get_settings
from ..database import get_db
from ..models import AccessKey, Admin, ConnectionSession, Node, User
from ..public_url import public_base_url
from ..schemas import UserCreate, UserUpdate
from ..security import require_csrf, sign_subscription
from ..services.accounts import create_access_key, serialize_user
from ..services.audit import audit
from ..services.profiles import (
    cisco_credentials,
    cisco_profile_xml,
    hiddify_deep_link,
    proxy_uri,
    wireguard_profile,
)
from ..xray import xray_runtime


router = APIRouter(prefix="/api/users", tags=["users"])


def _get_user(db: Session, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
    return user


def _serialize(db: Session, user: User, request: Request) -> dict:
    settings = get_settings()
    data = serialize_user(
        user,
        public_base_url(request),
        sign_subscription(user.id, user.subscription_version),
    )
    active_cutoff = datetime.now(timezone.utc).timestamp() - settings.session_stale_seconds
    active_sessions = list(
        db.scalars(
            select(ConnectionSession).where(
                ConnectionSession.user_id == user.id,
                ConnectionSession.ended_at.is_(None),
            )
        )
    )
    data["active_ips"] = len(
        {
            item.source_ip
            for item in active_sessions
            if item.last_seen_at.replace(tzinfo=item.last_seen_at.tzinfo or timezone.utc).timestamp()
            >= active_cutoff
        }
    )
    return data


@router.get("")
def list_users(
    request: Request,
    _: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> list[dict]:
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return [_serialize(db, user, request) for user in users]


@router.post("", status_code=201)
async def create_user(
    payload: UserCreate,
    request: Request,
    admin: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    user = User(
        name=payload.name.strip(),
        note=payload.note.strip(),
        quota_bytes=int(payload.quota_gb * 1024**3),
        validity_days=payload.validity_days,
        max_ips=payload.max_ips,
        speed_limit_bps=int(payload.speed_mbps * 1_000_000 / 8),
    )
    db.add(user)
    db.flush()
    nodes_query = select(Node).where(Node.enabled.is_(True))
    if payload.node_ids:
        nodes_query = nodes_query.where(Node.id.in_(payload.node_ids))
    nodes = db.scalars(nodes_query).all()
    for node in nodes:
        create_access_key(db, user, node)
    audit(
        db,
        "user.created",
        actor=admin.username,
        entity_type="user",
        entity_id=user.id,
        detail={"name": user.name, "nodes": len(nodes)},
    )
    db.commit()
    await xray_runtime.reconcile(db)
    return _serialize(db, user, request)


@router.get("/{user_id}")
def user_detail(
    user_id: str,
    request: Request,
    _: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    user = _get_user(db, user_id)
    data = _serialize(db, user, request)
    keys = db.scalars(
        select(AccessKey)
        .where(AccessKey.user_id == user.id)
        .options(joinedload(AccessKey.node))
    ).all()
    data["keys"] = [
        {
            "id": key.id,
            "node_id": key.node_id,
            "node_name": key.node.name,
            "protocol": key.node.protocol,
            "enabled": key.enabled,
        }
        for key in keys
    ]
    return data


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    admin: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    user = _get_user(db, user_id)
    values = payload.model_dump(exclude_unset=True)
    if "quota_gb" in values:
        user.quota_bytes = int(values.pop("quota_gb") * 1024**3)
    if "speed_mbps" in values:
        user.speed_limit_bps = int(values.pop("speed_mbps") * 1_000_000 / 8)
    for key, value in values.items():
        setattr(user, key, value.strip() if isinstance(value, str) else value)
    audit(
        db,
        "user.updated",
        actor=admin.username,
        entity_type="user",
        entity_id=user.id,
        detail={"fields": sorted(payload.model_fields_set)},
    )
    db.commit()
    await xray_runtime.reconcile(db)
    return _serialize(db, user, request)


@router.post("/{user_id}/reset-usage")
async def reset_usage(
    user_id: str,
    request: Request,
    admin: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    user = _get_user(db, user_id)
    user.used_up_bytes = 0
    user.used_down_bytes = 0
    audit(db, "user.usage_reset", actor=admin.username, entity_type="user", entity_id=user.id)
    db.commit()
    await xray_runtime.reconcile(db)
    return _serialize(db, user, request)


@router.post("/{user_id}/rotate-subscription")
def rotate_subscription(
    user_id: str,
    request: Request,
    admin: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    user = _get_user(db, user_id)
    user.subscription_version += 1
    audit(db, "user.subscription_rotated", actor=admin.username, entity_type="user", entity_id=user.id)
    db.commit()
    return _serialize(db, user, request)


@router.post("/{user_id}/nodes/{node_id}")
async def attach_node(
    user_id: str,
    node_id: str,
    admin: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    user = _get_user(db, user_id)
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="نود پیدا نشد")
    existing = db.scalar(
        select(AccessKey).where(AccessKey.user_id == user_id, AccessKey.node_id == node_id)
    )
    if existing:
        existing.enabled = True
    else:
        create_access_key(db, user, node)
    audit(db, "user.node_attached", actor=admin.username, entity_type="user", entity_id=user.id, detail={"node_id": node.id})
    db.commit()
    await xray_runtime.reconcile(db)
    return {"ok": True}


@router.delete("/{user_id}/nodes/{node_id}")
async def detach_node(
    user_id: str,
    node_id: str,
    admin: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    _get_user(db, user_id)
    result = db.execute(
        delete(AccessKey).where(AccessKey.user_id == user_id, AccessKey.node_id == node_id)
    )
    audit(db, "user.node_detached", actor=admin.username, entity_type="user", entity_id=user_id, detail={"node_id": node_id})
    db.commit()
    await xray_runtime.reconcile(db)
    return {"deleted": result.rowcount}


@router.get("/{user_id}/formats")
def user_formats(
    user_id: str,
    request: Request,
    _: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    user = _get_user(db, user_id)
    base_url = public_base_url(request)
    token = sign_subscription(user.id, user.subscription_version)
    subscription_url = f"{base_url}/sub/{token}"
    keys = db.scalars(
        select(AccessKey)
        .where(AccessKey.user_id == user.id)
        .options(joinedload(AccessKey.node))
    ).all()
    direct = [
        uri for key in keys if (uri := proxy_uri(user, key.node, key, base_url))
    ]
    downloads = [
        {
            "node_id": key.node_id,
            "node_name": key.node.name,
            "protocol": key.node.protocol,
            "url": f"{base_url}/api/users/{user.id}/profiles/{key.node_id}",
        }
        for key in keys
        if key.node.protocol in {"wireguard", "cisco"}
    ]
    return {
        "subscription_url": subscription_url,
        "hiddify_url": hiddify_deep_link(subscription_url, user.name),
        "direct_links": direct,
        "downloads": downloads,
    }


@router.get("/{user_id}/profiles/{node_id}")
def download_profile(
    user_id: str,
    node_id: str,
    _: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    from fastapi.responses import JSONResponse, Response

    user = _get_user(db, user_id)
    key = db.scalar(
        select(AccessKey)
        .where(AccessKey.user_id == user_id, AccessKey.node_id == node_id)
        .options(joinedload(AccessKey.node))
    )
    if not key:
        raise HTTPException(status_code=404, detail="پروفایل پیدا نشد")
    if key.node.protocol == "wireguard":
        return Response(
            wireguard_profile(user, key.node, key),
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="arena-{user.id[:8]}.conf"'},
        )
    if key.node.protocol == "cisco":
        return JSONResponse(
            {
                "credentials": cisco_credentials(key.node, key),
                "profile_xml": cisco_profile_xml(user, key.node, key),
            }
        )
    raise HTTPException(status_code=400, detail="این نود فایل جداگانه ندارد")


@router.delete("/{user_id}")
async def delete_user(
    user_id: str, admin: Admin = Depends(require_csrf), db: Session = Depends(get_db)
) -> dict:
    user = _get_user(db, user_id)
    audit(db, "user.deleted", actor=admin.username, entity_type="user", entity_id=user.id, detail={"name": user.name})
    db.delete(user)
    db.commit()
    await xray_runtime.reconcile(db)
    return {"ok": True}
