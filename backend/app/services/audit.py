import json

from sqlalchemy.orm import Session

from ..models import AuditEvent


def audit(
    db: Session,
    action: str,
    *,
    actor: str = "system",
    entity_type: str = "",
    entity_id: str = "",
    detail: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail_json=json.dumps(detail or {}, ensure_ascii=False, separators=(",", ":")),
        )
    )
