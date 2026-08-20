import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection

from alembic import context

# Import models so they register on Base.metadata for autogenerate.
from src.config import env
from src.pic.infrastructure.db import models  # noqa: F401
from src.pic.infrastructure.db.base import Base
from src.pic.infrastructure.db.engine import get_engine

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# staging and prod share the same Postgres database (see plan.md section 7),
# so a single `alembic_version` table can't track both independently — using
# it as-is would make Alembic think a migration already ran for prod just
# because it ran for staging (or vice-versa). Instead each environment gets
# its own version-tracking table, named after its table suffix (the same
# suffix used in users_staging/policy_staging vs users_prod/policy_prod), so
# migrations are still driven by which .env / deploy config is active — same
# as everything else in this app.
_env_suffix = env.APP_PIC_USERS_TABLE.removeprefix("users_")
version_table = f"alembic_version_{_env_suffix}"

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=version_table,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=version_table,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using the app's own engine (Cloud SQL Python Connector),
    instead of building one from `sqlalchemy.url` in alembic.ini — the
    connection to app-pic's Postgres doesn't use a plain host:port URL.
    """

    connectable = get_engine()

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
