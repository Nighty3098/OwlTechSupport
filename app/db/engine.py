"""Async engine / session factory setup."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import DbConfig
from .base import Base


def create_engine(db_config: DbConfig) -> AsyncEngine:
    return create_async_engine(db_config.url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_models(engine: AsyncEngine) -> None:
    """Create tables and apply lightweight migrations (no alembic here)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "postgresql":
            # create_all does not alter existing tables.
            for table in ("bugs", "features"):
                await conn.execute(
                    text(
                        f"alter table {table} "
                        f"add column if not exists started_by_username varchar(64)"
                    )
                )
                await conn.execute(
                    text(
                        f"alter table {table} "
                        f"add column if not exists started_by_user_id bigint"
                    )
                )
                constraint = f"fk_{table}_started_by_dev"
                await conn.execute(
                    text(
                        "do $$ begin "
                        "if not exists (select 1 from pg_constraint "
                        f"where conname = '{constraint}') then "
                        f"alter table {table} add constraint {constraint} "
                        "foreign key (started_by_user_id) "
                        "references developers(user_id); "
                        "end if; end $$;"
                    )
                )
