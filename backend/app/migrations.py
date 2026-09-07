import logging
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from .config import get_settings
from .database import engine


LEGACY_SCHEMA_REVISION = "61b94d732ada"
logger = logging.getLogger("arena.migrations")


def _migrate_once() -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

    inspector = inspect(engine)
    has_version = inspector.has_table("alembic_version")
    has_existing_schema = inspector.has_table("users")
    if has_existing_schema and not has_version:
        command.stamp(config, LEGACY_SCHEMA_REVISION)
    command.upgrade(config, "head")


def migrate_database() -> None:
    settings = get_settings()
    for attempt in range(1, settings.database_connect_retries + 1):
        try:
            _migrate_once()
            return
        except OperationalError:
            engine.dispose()
            if attempt == settings.database_connect_retries:
                raise
            logger.warning(
                "Database is not ready; retrying migration (%s/%s)",
                attempt,
                settings.database_connect_retries,
            )
            time.sleep(settings.database_retry_seconds)
