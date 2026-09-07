from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ARENA_",
        extra="ignore",
    )

    env: str = "development"
    public_url: str = "auto"
    database_url: str = "sqlite:///./arena.db"
    database_connect_retries: int = Field(default=30, ge=1, le=120)
    database_retry_seconds: float = Field(default=2, ge=0.1, le=30)
    app_secret: str = "development-only-change-this-secret"
    gateway_secret: str = "development-only-gateway-secret"
    admin_username: str = "admin"
    admin_password: str = "change-me-now"
    cookie_secure: bool = False
    session_hours: int = 12

    xray_binary: str = "/usr/local/bin/xray"
    xray_enabled: bool = True
    xray_config_dir: Path = Path("/tmp/arena-xray")
    xray_listen_host: str = "0.0.0.0"
    xray_api_host: str = "127.0.0.1"
    xray_api_port: int = 10085
    xray_internal_host: str = "arena"
    xray_public_host: str = "localhost"
    xray_public_port: int = 8080
    gateway_public_path: str = "/edge"
    trust_proxy_headers: bool = True
    session_stale_seconds: int = 45

    @field_validator("public_url")
    @classmethod
    def strip_public_url(cls, value: str) -> str:
        value = value.strip()
        return value if value.lower() == "auto" else value.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("gateway_public_path")
    @classmethod
    def normalize_gateway_path(cls, value: str) -> str:
        return "/" + value.strip("/")

    def validate_production_secrets(self) -> None:
        if self.env == "production":
            placeholders = ("development-only", "replace-", "change-me")
            weak = (
                len(self.app_secret) < 32
                or len(self.gateway_secret) < 32
                or len(self.admin_password) < 12
                or any(marker in self.app_secret for marker in placeholders)
                or any(marker in self.gateway_secret for marker in placeholders)
                or any(marker in self.admin_password for marker in placeholders)
                or not self.database_url.startswith("postgresql")
            )
            if weak:
                raise RuntimeError(
                    "Production requires PostgreSQL and explicitly configured credentials"
                )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production_secrets()
    return settings
