"""Filter that allows only superadmins and registered developers."""

from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..services.repo import is_developer


class IsDeveloper(BaseFilter):
    async def __call__(
        self,
        event: Message | CallbackQuery,
        session: AsyncSession,
        config: Config,
        **_: Any,
    ) -> bool:
        user = event.from_user
        if user is None:
            return False
        return await is_developer(session, config.superadmin_ids, user.id)
