"""``/start``, language selection and main menus."""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..db.models import User
from ..keyboards.callbacks import LangCB
from ..keyboards.user import language_kb, user_menu_kb
from ..services.repo import count_new_tickets, is_developer, set_language


def get_router() -> Router:
    router = Router(name="start")

    @router.message(CommandStart())
    async def cmd_start(
        message: Message,
        db_user: User,
        t: Callable[..., str],
        session: AsyncSession,
        config: Config,
    ) -> None:
        if db_user.language is None:
            await message.answer(t("choose_language"), reply_markup=language_kb())
            return
        await send_main_menu(message, session, config, db_user.user_id, t)

    @router.callback_query(LangCB.filter())
    async def choose_language(
        callback: CallbackQuery,
        callback_data: LangCB,
        db_user: User,
        session: AsyncSession,
        config: Config,
        i18n,
    ) -> None:
        await set_language(session, db_user.user_id, callback_data.code)
        db_user.language = callback_data.code
        if isinstance(callback.message, Message):
            # Clear the greeting message together with its buttons.
            with contextlib.suppress(Exception):
                await callback.message.delete()
        t = i18n.bound(callback_data.code)
        user_id = callback.from_user.id if callback.from_user else db_user.user_id
        if callback.message is not None:
            await send_main_menu(callback.message, session, config, user_id, t)
        await callback.answer()

    return router


async def send_main_menu(
    message: Message,
    session: AsyncSession,
    config: Config,
    user_id: int,
    t: Callable[..., str],
) -> None:
    """Welcome text + menu depending on the role (developer or regular user)."""
    if await is_developer(session, config.superadmin_ids, user_id):
        new_tickets = await count_new_tickets(session)
        await message.answer(t("admin_welcome", count=new_tickets))
        return
    await message.answer(t("main_menu_user"), reply_markup=user_menu_kb(t))
