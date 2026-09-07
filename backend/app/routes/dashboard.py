from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Admin, AuditEvent, ConnectionSession, Node, User
from ..security import require_csrf


router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(
    _: Admin = Depends(require_csrf), db: Session = Depends(get_db)
) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=get_settings().session_stale_seconds)
    users = list(db.scalars(select(User)))
    active_sessions = list(
        db.scalars(
            select(ConnectionSession).where(
                ConnectionSession.ended_at.is_(None),
                ConnectionSession.last_seen_at >= cutoff,
            )
        )
    )
    traffic_total = sum(user.used_bytes for user in users)
    return {
        "users_total": len(users),
        "users_enabled": sum(1 for user in users if user.active),
        "active_sessions": len(active_sessions),
        "active_ips": len({item.source_ip for item in active_sessions}),
        "traffic_total": traffic_total,
        "nodes_enabled": db.scalar(select(func.count()).select_from(Node).where(Node.enabled.is_(True))) or 0,
        "recent_sessions": [
            {
                "id": item.id,
                "user_id": item.user_id,
                "node_id": item.node_id,
                "source_ip": item.source_ip,
                "status": item.status,
                "uplink_bytes": item.uplink_bytes,
                "downlink_bytes": item.downlink_bytes,
                "started_at": item.started_at,
                "last_seen_at": item.last_seen_at,
            }
            for item in db.scalars(
                select(ConnectionSession).order_by(ConnectionSession.started_at.desc()).limit(10)
            )
        ],
    }


@router.get("/logs")
def logs(
    limit: int = 100,
    user_id: str | None = None,
    _: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    limit = min(max(limit, 1), 500)
    sessions_query = select(ConnectionSession).order_by(ConnectionSession.started_at.desc()).limit(limit)
    if user_id:
        sessions_query = sessions_query.where(ConnectionSession.user_id == user_id)
    sessions = db.scalars(sessions_query).all()
    audits_query = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if user_id:
        audits_query = audits_query.where(AuditEvent.entity_id == user_id)
    audits = db.scalars(audits_query).all()
    return {
        "sessions": [
            {
                "id": item.id,
                "user_id": item.user_id,
                "node_id": item.node_id,
                "source_ip": item.source_ip,
                "user_agent": item.user_agent,
                "status": item.status,
                "close_reason": item.close_reason,
                "uplink_bytes": item.uplink_bytes,
                "downlink_bytes": item.downlink_bytes,
                "started_at": item.started_at,
                "last_seen_at": item.last_seen_at,
                "ended_at": item.ended_at,
            }
            for item in sessions
        ],
        "audit": [
            {
                "id": item.id,
                "actor": item.actor,
                "action": item.action,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "detail": item.detail_json,
                "created_at": item.created_at,
            }
            for item in audits
        ],
    }
