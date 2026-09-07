import os
from pathlib import Path


TEST_DB = Path("/tmp/arena-phase1-tests.db")
TEST_DB.unlink(missing_ok=True)
os.environ.update(
    {
        "ARENA_ENV": "test",
        "ARENA_DATABASE_URL": f"sqlite:///{TEST_DB}",
        "ARENA_APP_SECRET": "test-app-secret-that-is-long-enough-123456",
        "ARENA_GATEWAY_SECRET": "test-gateway-secret-123456789",
        "ARENA_ADMIN_USERNAME": "admin",
        "ARENA_ADMIN_PASSWORD": "arena-test-password",
        "ARENA_XRAY_ENABLED": "false",
        "ARENA_PUBLIC_URL": "http://testserver",
        "ARENA_XRAY_PUBLIC_HOST": "proxy.test",
        "ARENA_XRAY_PUBLIC_PORT": "443",
    }
)
