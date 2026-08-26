"""Async SQLAlchemy engine for the app-pic Postgres (identity + local mirror of
data-proxy's `rls.access_policy`).

Connection goes through the Cloud SQL Python Connector instead of a plain
host:port URL. The connector authenticates via IAM (Workload Identity
Federation in-cluster; local `gcloud`/ADC credentials for local dev) and opens
an authenticated mTLS tunnel directly to the instance — no Cloud SQL Auth Proxy
sidecar, no public-IP allowlisting needed. See plan.md section 7 for details.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from google.cloud.sql.connector import Connector, IPTypes, create_async_connector
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import env

_connector: Connector | None = None
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_init_lock = asyncio.Lock()


async def _get_connector() -> Connector:
    global _connector
    if _connector is None:
        async with _init_lock:
            if _connector is None:
                _connector = await create_async_connector(ip_type=IPTypes.PUBLIC)
    return _connector


async def _getconn():
    connector = await _get_connector()
    return await connector.connect_async(
        env.APP_PIC_PG_INSTANCE_CONNECTION_NAME,
        "asyncpg",
        user=env.APP_PIC_PG_USER,
        password=env.APP_PIC_PG_PW,
        db=env.APP_PIC_PG_DB,
    )


def get_engine() -> AsyncEngine:
    """Lazily create the (singleton) async engine.

    The connector itself is created lazily inside the first connection attempt
    (via `_getconn`), so this is safe to call before an event loop is running.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            "postgresql+asyncpg://",
            async_creator=_getconn,
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
    """Dispose the engine and close the connector. Call on app shutdown."""
    global _engine, _connector, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None
    if _connector is not None:
        await _connector.close_async()
        _connector = None
