import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sessions: Mapped[list["AdminSession"]] = relationship(
        back_populates="admin", cascade="all, delete-orphan"
    )


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    admin: Mapped[Admin] = relationship(back_populates="sessions")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    quota_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    used_up_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    used_down_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    validity_days: Mapped[int] = mapped_column(Integer, default=30)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    max_ips: Mapped[int] = mapped_column(Integer, default=1)
    speed_limit_bps: Mapped[int] = mapped_column(BigInteger, default=0)
    subscription_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    keys: Mapped[list["AccessKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["ConnectionSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def used_bytes(self) -> int:
        return self.used_up_bytes + self.used_down_bytes


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(24), default="xray")
    protocol: Mapped[str] = mapped_column(String(24), default="vless")
    transport: Mapped[str] = mapped_column(String(24), default="websocket")
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=443)
    security: Mapped[str] = mapped_column(String(24), default="tls")
    sni: Mapped[str] = mapped_column(String(255), default="")
    websocket_host: Mapped[str] = mapped_column(String(255), default="")
    path: Mapped[str] = mapped_column(String(255), default="/edge")
    fingerprint: Mapped[str] = mapped_column(String(32), default="chrome")
    alpn: Mapped[str] = mapped_column(String(120), default="http/1.1")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    internal_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    keys: Mapped[list["AccessKey"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )


class AccessKey(Base):
    __tablename__ = "access_keys"
    __table_args__ = (Index("ix_access_keys_user_node", "user_id", "node_id", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    credential: Mapped[str] = mapped_column(String(255), index=True)
    secret_payload: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="keys")
    node: Mapped[Node] = relationship(back_populates="keys")


class ConnectionSession(Base):
    __tablename__ = "connection_sessions"
    __table_args__ = (
        Index("ix_sessions_user_active", "user_id", "ended_at", "last_seen_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    source_ip: Mapped[str] = mapped_column(String(64), index=True)
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    gateway_instance: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    close_reason: Mapped[str] = mapped_column(String(255), default="")
    uplink_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    downlink_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), default="")
    entity_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
