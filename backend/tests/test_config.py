import pytest

from backend.app.config import Settings


def test_production_rejects_placeholder_credentials():
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://arena:secret@db/arena",
        app_secret="replace-with-at-least-32-random-characters",
        gateway_secret="replace-with-another-long-random-value",
        admin_password="replace-this-password",
    )
    with pytest.raises(RuntimeError):
        settings.validate_production_secrets()


def test_production_accepts_explicit_credentials():
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://arena:secret@db/arena",
        app_secret="a-real-application-secret-with-entropy-2026",
        gateway_secret="a-separate-gateway-secret-with-entropy-2026",
        admin_password="a-long-admin-password-2026",
    )
    settings.validate_production_secrets()


def test_reality_rejects_missing_key_material():
    settings = Settings(xray_reality_enabled=True)
    with pytest.raises(RuntimeError, match="REALITY requires"):
        settings.validate_production_secrets()


def test_reality_accepts_complete_key_material():
    settings = Settings(
        xray_reality_enabled=True,
        xray_reality_private_key="private-key",
        xray_reality_public_key="public-key",
        xray_reality_short_id="0123456789abcdef",
    )
    settings.validate_production_secrets()
