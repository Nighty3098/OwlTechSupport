"""Application wiring: dispatcher, middlewares, routers."""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import async_sessionmaker

from .config import Config
from .handlers import start, user
from .handlers.admin import team, tickets
from .middlewares.database import DbSessionMiddleware
from .middlewares.user_context import UserContextMiddleware
from .services.i18n import i18n


def create_dispatcher(
    config: Config,
    sessionmaker: async_sessionmaker,
) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp["config"] = config

    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    dp.update.outer_middleware(UserContextMiddleware(i18n))

    # Public handlers first, developer-only routers last.
    dp.include_router(start.router)
    dp.include_router(user.router)
    dp.include_router(team.router)
    dp.include_router(tickets.router)
    return dp
