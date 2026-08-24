"""Async engine / session factory setup."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import Config
from .base import Base


def create_engine(config: Config) -> AsyncEngine:
    return create_async_engine(config.db.url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_models(engine: AsyncEngine) -> None:
    """Create tables (lightweight alternative to migrations for this project)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
