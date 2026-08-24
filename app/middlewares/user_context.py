"""Middleware that ensures a user row exists and binds the translator."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import User
from ..services.i18n import DEFAULT_LANGUAGE, Translator


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
        data["t"] = self._i18n.bound(db_user.language)
        return await handler(event, data)


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None,
) -> User:
    user = (await session.scalars(select(User).where(User.user_id == user_id))).first()
    if user is None:
        user = User(user_id=user_id, username=username, language=DEFAULT_LANGUAGE)
        session.add(user)
        await session.flush()
    elif user.username != username:
        user.username = username
        await session.flush()
    return user
