from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=2000)
    quota_gb: float = Field(default=50, ge=0, le=1_000_000)
    validity_days: int = Field(default=30, ge=0, le=3650)
    max_ips: int = Field(default=1, ge=1, le=100)
    speed_mbps: float = Field(default=0, ge=0, le=100_000)
    node_ids: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    active: bool | None = None
    quota_gb: float | None = Field(default=None, ge=0, le=1_000_000)
    validity_days: int | None = Field(default=None, ge=0, le=3650)
    expires_at: datetime | None = None
    max_ips: int | None = Field(default=None, ge=1, le=100)
    speed_mbps: float | None = Field(default=None, ge=0, le=100_000)


class NodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    kind: Literal["xray", "wireguard", "cisco"] = "xray"
    protocol: Literal["vless", "vmess", "wireguard", "cisco"] = "vless"
    transport: Literal["websocket", "tcp", "external"] = "websocket"
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=443, ge=1, le=65535)
    security: Literal["tls", "reality", "none"] = "tls"
    sni: str = Field(default="", max_length=255)
    websocket_host: str = Field(default="", max_length=255)
    path: str = Field(default="/edge", max_length=255)
    fingerprint: Literal[
        "chrome", "firefox", "safari", "ios", "android", "edge", "random", "randomized"
    ] = "chrome"
    alpn: list[Literal["http/1.1", "h2", "h3"]] = Field(default_factory=lambda: ["http/1.1"])
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        return "/" + value.strip("/")


class NodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    security: Literal["tls", "reality", "none"] | None = None
    sni: str | None = Field(default=None, max_length=255)
    websocket_host: str | None = Field(default=None, max_length=255)
    path: str | None = Field(default=None, max_length=255)
    fingerprint: Literal[
        "chrome", "firefox", "safari", "ios", "android", "edge", "random", "randomized"
    ] | None = None
    alpn: list[Literal["http/1.1", "h2", "h3"]] | None = None
    metadata: dict[str, Any] | None = None


class GatewayAuthorize(BaseModel):
    user_id: str
    node_id: str
    source_ip: str
    user_agent: str = ""
    gateway_instance: str = ""


class GatewayHeartbeat(BaseModel):
    session_id: str
    uplink_delta: int = Field(default=0, ge=0)
    downlink_delta: int = Field(default=0, ge=0)


class GatewayClose(GatewayHeartbeat):
    reason: str = Field(default="client_closed", max_length=255)


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor: str
    action: str
    entity_type: str
    entity_id: str
    detail_json: str
    created_at: datetime
