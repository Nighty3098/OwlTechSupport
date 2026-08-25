"""Denial responses for admin callbacks clicked by non-developers."""

from __future__ import annotations

import logging
from collections.abc import Callable

from aiogram import Router
from aiogram.types import CallbackQuery

from ...keyboards.callbacks import StatusPickCB, StatusSetCB, TeamCB, TicketsListCB

logger = logging.getLogger(__name__)


def get_router() -> Router:
    # Included AFTER the developer-only routers, so developers never reach it.
    router = Router(name="dev_callbacks_denied")

    @router.callback_query(TicketsListCB.filter())
    @router.callback_query(StatusPickCB.filter())
    @router.callback_query(StatusSetCB.filter())
    @router.callback_query(TeamCB.filter())
    async def deny(
        callback: CallbackQuery,
        t: Callable[..., str],
    ) -> None:
        user = callback.from_user
        logger.warning(
            "access_denied user=%d (@%s) data=%s",
            user.id if user else 0,
            (user.username if user else None) or "?",
            callback.data or "?",
        )
        await callback.answer(t("access_denied"), show_alert=True)

    return router
