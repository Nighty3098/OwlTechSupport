"""Middleware that ensures a user row exists and binds the translator."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import User
from ..services.i18n import DEFAULT_LANGUAGE, Translator
from ..services.repo import sync_developer_username

logger = logging.getLogger(__name__)


class UserContextMiddleware(BaseMiddleware):
    """Injects ``db_user`` and ``t`` (locale shortcut) into handler data."""

    def __init__(self, translator: Translator) -> None:
        self._i18n = translator

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        session: AsyncSession = data["session"]
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        db_user = await get_or_create_user(session, tg_user.id, tg_user.username)
        data["db_user"] = db_user
        data["i18n"] = self._i18n
        data["t"] = self._i18n.bound(db_user.language or DEFAULT_LANGUAGE)
        return await handler(event, data)


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None,
) -> User:
    user = (await session.scalars(select(User).where(User.user_id == user_id))).first()
    if user is None:
        user = User(user_id=user_id, username=username)
        session.add(user)
        await session.flush()
        logger.info("new user created user=%d (@%s)", user_id, username or "?")
    elif user.username != username:
        old = user.username
        user.username = username
        await session.flush()
        logger.info(
            "username changed user=%d old=@%s new=@%s",
            user_id, old or "?", username or "?",
        )
    if username:
        # Keep the developers table on fresh Telegram usernames.
        await sync_developer_username(session, user_id, username)
    return user
