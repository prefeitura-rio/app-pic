"""Async SQLAlchemy engine for the app-pic Postgres (identity + local mirror of
data-proxy's `rls.access_policy`).

Connection is a plain host:port Postgres connection through the cluster's
shared `cloudsql-proxy` Service (already IAM/WIF-authenticated on the infra
side) — no Cloud SQL Python Connector, no per-pod Workload Identity binding
needed. Locally (outside the cluster), point `APP_PIC_PG_HOST`/
`APP_PIC_PG_PORT` at a `kubectl port-forward` of that same Service. See
plan.md section 7 for details.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import env

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Lazily create the (singleton) async engine."""
    global _engine
    if _engine is None:
        url = URL.create(
            "postgresql+asyncpg",
            username=env.APP_PIC_PG_USER,
            password=env.APP_PIC_PG_PW,
            host=env.APP_PIC_PG_HOST,
            port=env.APP_PIC_PG_PORT,
            database=env.APP_PIC_PG_DB,
        )
        _engine = create_async_engine(
            url,
            pool_pre_ping=True,
            # Environment isolation (staging vs prod) is done via Postgres
            # schema, not table name — models declare no schema (`schema=None`),
            # and this maps that to the schema for the active environment at
            # execution time. See plan.md section 7.
            execution_options={"schema_translate_map": {None: env.APP_PIC_PG_SCHEMA}},
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def close_engine() -> None:
    """Dispose the engine. Call on app shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None
