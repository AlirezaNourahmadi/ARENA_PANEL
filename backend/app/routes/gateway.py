from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import AccessKey, ConnectionSession, Node, User
from ..schemas import GatewayAuthorize, GatewayClose, GatewayHeartbeat
from ..services.accounts import user_allowed
from ..services.audit import audit


router = APIRouter(prefix="/api/internal/gateway", tags=["gateway"])


def gateway_auth(
    secret: str | None = Header(default=None, alias="X-Arena-Gateway"),
) -> None:
    import hmac

    expected = get_settings().gateway_secret
    if not secret or not hmac.compare_digest(secret, expected):
        raise HTTPException(status_code=401, detail="gateway authentication failed")


def _finish_stale_sessions(db: Session, now: datetime) -> None:
    cutoff = now - timedelta(seconds=get_settings().session_stale_seconds)
    db.execute(
        update(ConnectionSession)
        .where(ConnectionSession.ended_at.is_(None), ConnectionSession.last_seen_at < cutoff)
        .values(ended_at=now, status="stale", close_reason="heartbeat_timeout")
    )


def _apply_traffic(user: User, session: ConnectionSession, up: int, down: int) -> None:
    session.uplink_bytes += up
    session.downlink_bytes += down
    user.used_up_bytes += up
    user.used_down_bytes += down
    session.last_seen_at = datetime.now(timezone.utc)


@router.post("/authorize", dependencies=[Depends(gateway_auth)])
def authorize(payload: GatewayAuthorize, db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    _finish_stale_sessions(db, now)
    user = db.scalar(select(User).where(User.id == payload.user_id).with_for_update())
    node = db.scalar(select(Node).where(Node.id == payload.node_id))
    key = db.scalar(
        select(AccessKey).where(
            AccessKey.user_id == payload.user_id,
            AccessKey.node_id == payload.node_id,
            AccessKey.enabled.is_(True),
        )
    )
    if not user or not node or not node.enabled or not key:
        audit(db, "gateway.denied", entity_type="user", entity_id=payload.user_id, detail={"reason": "route_not_found", "ip": payload.source_ip})
        db.commit()
        raise HTTPException(status_code=403, detail="route_not_found")
    allowed, reason = user_allowed(user, now)
    if not allowed:
        audit(db, "gateway.denied", entity_type="user", entity_id=user.id, detail={"reason": reason, "ip": payload.source_ip})
        db.commit()
        raise HTTPException(status_code=403, detail=reason)

    active = list(
        db.scalars(
            select(ConnectionSession).where(
                ConnectionSession.user_id == user.id,
                ConnectionSession.ended_at.is_(None),
            )
        )
    )
    distinct_ips = {item.source_ip for item in active}
    if payload.source_ip not in distinct_ips and len(distinct_ips) >= user.max_ips:
        audit(db, "gateway.denied", entity_type="user", entity_id=user.id, detail={"reason": "ip_limit", "ip": payload.source_ip, "active_ips": len(distinct_ips)})
        db.commit()
        raise HTTPException(status_code=429, detail="ip_limit")

    if user.starts_at is None:
        user.starts_at = now
        if user.validity_days:
            user.expires_at = now + timedelta(days=user.validity_days)

    connection = ConnectionSession(
        user_id=user.id,
        node_id=node.id,
        source_ip=payload.source_ip,
        user_agent=payload.user_agent[:512],
        gateway_instance=payload.gateway_instance[:120],
    )
    db.add(connection)
    db.flush()
    audit(db, "gateway.connected", entity_type="user", entity_id=user.id, detail={"session_id": connection.id, "node_id": node.id, "ip": payload.source_ip})
    db.commit()
    port = 11000 if node.protocol == "vless" else 11001
    return {
        "session_id": connection.id,
        "upstream_url": f"ws://{get_settings().xray_internal_host}:{port}/internal/{node.protocol}",
        "speed_limit_bps": user.speed_limit_bps,
        "heartbeat_seconds": 15,
    }


@router.post("/heartbeat", dependencies=[Depends(gateway_auth)])
def heartbeat(payload: GatewayHeartbeat, db: Session = Depends(get_db)) -> dict:
    session = db.scalar(
        select(ConnectionSession)
        .where(ConnectionSession.id == payload.session_id, ConnectionSession.ended_at.is_(None))
        .with_for_update()
    )
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    user = db.scalar(select(User).where(User.id == session.user_id).with_for_update())
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    _apply_traffic(user, session, payload.uplink_delta, payload.downlink_delta)
    allowed, reason = user_allowed(user)
    if not allowed:
        session.status = "blocked"
        session.close_reason = reason
    db.commit()
    return {"terminate": not allowed, "reason": reason, "speed_limit_bps": user.speed_limit_bps}


@router.post("/close", dependencies=[Depends(gateway_auth)])
def close(payload: GatewayClose, db: Session = Depends(get_db)) -> dict:
    session = db.scalar(
        select(ConnectionSession).where(ConnectionSession.id == payload.session_id).with_for_update()
    )
    if not session:
        return {"ok": True}
    if session.ended_at is None:
        user = db.scalar(select(User).where(User.id == session.user_id).with_for_update())
        if user:
            _apply_traffic(user, session, payload.uplink_delta, payload.downlink_delta)
        session.ended_at = datetime.now(timezone.utc)
        session.status = "closed"
        session.close_reason = payload.reason
        audit(db, "gateway.disconnected", entity_type="user", entity_id=session.user_id, detail={"session_id": session.id, "reason": payload.reason, "uplink": session.uplink_bytes, "downlink": session.downlink_bytes})
        db.commit()
    return {"ok": True}
