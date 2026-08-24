"""Shared fixtures."""

from __future__ import annotations

import pytest
from app.config import ChatTarget, Config, DbConfig
from app.db.base import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture()
def db_config() -> DbConfig:
    return DbConfig(
        host="localhost", port=5432, user="owl", password="secret", name="owl_support"
    )


@pytest.fixture()
def config(db_config: DbConfig) -> Config:
    return Config(
        bot_token="123456:test-token",
        superadmin_ids=(42,),
        support_chat=ChatTarget(chat_id=-1003800802201, topic_id=37),
        db=db_config,
        proxy_url=None,
    )


@pytest.fixture()
async def sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest.fixture()
async def session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncSession:
    async with sessionmaker() as s:
        yield s
