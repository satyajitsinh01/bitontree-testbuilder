from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        kwargs: dict = {"echo": False}
        if settings.database_url.startswith("postgresql"):
            # PgBouncer transaction pooling: disable asyncpg statement cache (research R12)
            kwargs["connect_args"] = {"statement_cache_size": 0}
        _engine = create_async_engine(settings.database_url, **kwargs)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session


async def create_all() -> None:
    """Dev/test convenience; production applies Alembic migrations instead."""
    from . import models  # noqa: F401  (register mappings)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def reset_engine_for_tests() -> None:
    global _engine, _session_factory
    _engine = None
    _session_factory = None
    get_settings.cache_clear()
