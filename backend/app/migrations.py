from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .config import get_settings
from .database import engine


LEGACY_SCHEMA_REVISION = "61b94d732ada"


def migrate_database() -> None:
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
