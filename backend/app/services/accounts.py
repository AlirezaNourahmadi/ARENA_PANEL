import base64
import ipaddress
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AccessKey, Node, User
from ..security import decrypt_payload, encrypt_payload


def aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def user_expiry(user: User) -> datetime | None:
    if user.expires_at:
        return aware(user.expires_at)
    if user.starts_at and user.validity_days:
        return aware(user.starts_at) + timedelta(days=user.validity_days)
    return None


def days_remaining(user: User, now: datetime | None = None) -> int | None:
    expiry = user_expiry(user)
    if expiry is None:
        return user.validity_days if user.starts_at is None and user.validity_days else None
    seconds = (expiry - (now or datetime.now(timezone.utc))).total_seconds()
    return max(0, int((seconds + 86399) // 86400))


def user_allowed(user: User, now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    if not user.active:
        return False, "user_disabled"
    expiry = user_expiry(user)
    if expiry and expiry <= now:
        return False, "expired"
    if user.quota_bytes and user.used_bytes >= user.quota_bytes:
        return False, "quota_exceeded"
    return True, "allowed"


def _wireguard_payload(db: Session, node: Node) -> dict:
    metadata = json.loads(node.metadata_json or "{}")
    network = ipaddress.ip_network(metadata.get("client_cidr", "10.66.0.0/24"), strict=False)
    used_addresses: set[str] = set()
    for key in db.scalars(select(AccessKey).where(AccessKey.node_id == node.id)):
        payload = decrypt_payload(key.secret_payload)
        if payload.get("address"):
            used_addresses.add(payload["address"].split("/")[0])
    address = None
    for candidate in list(network.hosts())[1:]:
        if str(candidate) not in used_addresses:
            address = f"{candidate}/{network.prefixlen}"
            break
    if not address:
        raise ValueError("WireGuard address pool is exhausted")

    private_key = X25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {
        "private_key": base64.b64encode(private_raw).decode(),
        "public_key": base64.b64encode(public_raw).decode(),
        "address": address,
    }


def create_access_key(db: Session, user: User, node: Node) -> AccessKey:
    if node.protocol in {"vless", "vmess"}:
        credential = str(uuid.uuid4())
        payload: dict = {}
    elif node.protocol == "wireguard":
        payload = _wireguard_payload(db, node)
        credential = payload["public_key"]
    elif node.protocol == "cisco":
        username = f"arena-{user.id.split('-')[0]}"
        payload = {"username": username, "password": secrets.token_urlsafe(18)}
        credential = username
    else:
        raise ValueError(f"Unsupported protocol: {node.protocol}")
    key = AccessKey(
        user_id=user.id,
        node_id=node.id,
        credential=credential,
        secret_payload=encrypt_payload(payload) if payload else "",
    )
    db.add(key)
    return key


def serialize_user(user: User, public_url: str, subscription_token: str) -> dict:
    remaining = days_remaining(user)
    allowed, reason = user_allowed(user)
    return {
        "id": user.id,
        "name": user.name,
        "note": user.note,
        "active": user.active,
        "allowed": allowed,
        "status_reason": reason,
        "quota_bytes": user.quota_bytes,
        "used_up_bytes": user.used_up_bytes,
        "used_down_bytes": user.used_down_bytes,
        "used_bytes": user.used_bytes,
        "validity_days": user.validity_days,
        "days_remaining": remaining,
        "starts_at": user.starts_at,
        "expires_at": user_expiry(user),
        "max_ips": user.max_ips,
        "speed_limit_bps": user.speed_limit_bps,
        "subscription_url": f"{public_url}/sub/{subscription_token}",
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def serialize_node(node: Node) -> dict:
    return {
        "id": node.id,
        "name": node.name,
        "slug": node.slug,
        "kind": node.kind,
        "protocol": node.protocol,
        "transport": node.transport,
        "host": node.host,
        "port": node.port,
        "security": node.security,
        "sni": node.sni,
        "websocket_host": node.websocket_host,
        "path": node.path,
        "fingerprint": node.fingerprint,
        "alpn": [item for item in node.alpn.split(",") if item],
        "enabled": node.enabled,
        "metadata": json.loads(node.metadata_json or "{}"),
        "created_at": node.created_at,
        "updated_at": node.updated_at,
    }
