"""
Alembic Migration Environment

Configures Alembic for async SQLAlchemy 2.0 with PostgreSQL.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import inspect, pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from alembic.script import ScriptDirectory

# Add src to path for imports
import sys
from pathlib import Path

# Add the project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Import Base and all models to ensure they're registered
from src.db.base import Base
from src.db.models import (  # noqa: F401
    actuator,
    ai,
    auth,
    calibration_session,
    esp,
    kaiser,
    library,
    logic,
    sensor,
    system,
    user,
)

# Import settings to get database URL
from src.core.config import get_settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    """Get database URL from settings."""
    settings = get_settings()
    return settings.database.url


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with connection."""
    inspector = inspect(connection)
    user_tables = [name for name in inspector.get_table_names() if name != "alembic_version"]
    if not user_tables:
        # Legacy compatibility: this repository has no full base-schema migration
        # for very early revisions. On a truly empty database we bootstrap from the
        # current SQLAlchemy metadata and stamp head, so `alembic upgrade head`
        # becomes deterministic for first-time environments.
        target_metadata.create_all(connection)

        heads = ScriptDirectory.from_config(config).get_heads()
        if len(heads) != 1:
            raise RuntimeError(f"Expected single Alembic head, got: {heads}")

        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL)"
            )
        )
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
            {"version_num": heads[0]},
        )
        connection.commit()
        return

    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode (async)."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
        # Alembic runs DDL inside nested/sync transactions; the async connection
        # still needs an explicit commit before __aexit__, otherwise the outer
        # transaction is rolled back and migrations appear to "succeed" in logs
        # without persisting (asyncpg + run_sync).
        await connection.commit()

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
