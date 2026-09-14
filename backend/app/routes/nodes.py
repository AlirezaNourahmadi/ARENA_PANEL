import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Admin, Node
from ..schemas import NodeCreate, NodeUpdate
from ..security import require_csrf
from ..services.accounts import serialize_node
from ..services.audit import audit
from ..xray import xray_runtime


router = APIRouter(prefix="/api/nodes", tags=["nodes"])


def _validate_node(payload: NodeCreate) -> None:
    if payload.kind == "xray" and payload.protocol not in {"vless", "vmess"}:
        raise HTTPException(status_code=422, detail="نود Xray باید VLESS یا VMess باشد")
    if payload.kind == "xray" and payload.transport not in {"websocket", "tcp"}:
        raise HTTPException(status_code=422, detail="ترابرد Xray باید WebSocket یا TCP باشد")
    if payload.kind == "xray" and payload.transport == "tcp":
        if payload.protocol != "vless" or payload.security != "reality":
            raise HTTPException(status_code=422, detail="TCP مستقیم فقط برای VLESS REALITY پشتیبانی می‌شود")
        public_key = str(payload.metadata.get("public_key", ""))
        short_id = str(payload.metadata.get("short_id", ""))
        if not payload.sni or not public_key or not short_id:
            raise HTTPException(status_code=422, detail="REALITY به SNI، public key و short ID نیاز دارد")
    if payload.kind == "xray" and payload.transport == "websocket" and payload.security == "reality":
        raise HTTPException(status_code=422, detail="امنیت REALITY فقط با TCP قابل استفاده است")
    if payload.kind == "wireguard" and payload.protocol != "wireguard":
        raise HTTPException(status_code=422, detail="نوع و پروتکل WireGuard هم‌خوان نیست")
    if payload.kind == "cisco" and payload.protocol != "cisco":
        raise HTTPException(status_code=422, detail="نوع و پروتکل Cisco هم‌خوان نیست")


def _get_node(db: Session, node_id: str) -> Node:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="نود پیدا نشد")
    return node


@router.get("")
def list_nodes(
    _: Admin = Depends(require_csrf), db: Session = Depends(get_db)
) -> list[dict]:
    return [serialize_node(node) for node in db.scalars(select(Node).order_by(Node.created_at))]


@router.post("", status_code=201)
async def create_node(
    payload: NodeCreate,
    admin: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    _validate_node(payload)
    if db.scalar(select(Node).where(Node.slug == payload.slug)):
        raise HTTPException(status_code=409, detail="این شناسه نود قبلاً استفاده شده است")
    node = Node(
        name=payload.name.strip(),
        slug=payload.slug,
        kind=payload.kind,
        protocol=payload.protocol,
        transport=payload.transport,
        host=payload.host.strip(),
        port=payload.port,
        security=payload.security,
        sni=payload.sni.strip(),
        websocket_host=payload.websocket_host.strip(),
        path=payload.path,
        fingerprint=payload.fingerprint,
        alpn=",".join(payload.alpn),
        enabled=payload.enabled,
        metadata_json=json.dumps(payload.metadata, separators=(",", ":")),
    )
    db.add(node)
    db.flush()
    audit(db, "node.created", actor=admin.username, entity_type="node", entity_id=node.id, detail={"protocol": node.protocol})
    db.commit()
    await xray_runtime.reconcile(db)
    return serialize_node(node)


@router.patch("/{node_id}")
async def update_node(
    node_id: str,
    payload: NodeUpdate,
    admin: Admin = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    node = _get_node(db, node_id)
    values = payload.model_dump(exclude_unset=True)
    if "alpn" in values:
        node.alpn = ",".join(values.pop("alpn"))
    if "metadata" in values:
        node.metadata_json = json.dumps(values.pop("metadata"), separators=(",", ":"))
    if "path" in values and values["path"]:
        values["path"] = "/" + values["path"].strip("/")
    for key, value in values.items():
        setattr(node, key, value.strip() if isinstance(value, str) else value)
    if node.kind == "xray" and node.transport == "tcp" and node.security != "reality":
        raise HTTPException(status_code=422, detail="نود TCP باید از REALITY استفاده کند")
    audit(db, "node.updated", actor=admin.username, entity_type="node", entity_id=node.id, detail={"fields": sorted(payload.model_fields_set)})
    db.commit()
    await xray_runtime.reconcile(db)
    return serialize_node(node)


@router.delete("/{node_id}")
async def disable_node(
    node_id: str, admin: Admin = Depends(require_csrf), db: Session = Depends(get_db)
) -> dict:
    node = _get_node(db, node_id)
    node.enabled = False
    audit(db, "node.disabled", actor=admin.username, entity_type="node", entity_id=node.id)
    db.commit()
    await xray_runtime.reconcile(db)
    return {"ok": True}
