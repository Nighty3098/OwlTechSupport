"""Ticket management for developers: list and status changes."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import TicketStatus, User
from ...filters.developer import IsDeveloper
from ...keyboards.admin import STATUS_KEYS, pick_ticket_kb, status_kb
from ...keyboards.callbacks import StatusPickCB, StatusSetCB, TicketsListCB
from ...services.repo import apply_status, get_ticket, recent_tickets
from ...services.tickets import (
    build_ticket_text,
    change_status_markup,
    emoji_for_kind,
    format_ticket_summary,
)

logger = logging.getLogger(__name__)

TICKETS_LIMIT = 10


def get_router() -> Router:
    router = Router(name="admin_tickets")
    router.callback_query.filter(IsDeveloper())

    @router.callback_query(TicketsListCB.filter())
    async def tickets_list(
        callback: CallbackQuery,
        session: AsyncSession,
        t: Callable[..., str],
    ) -> None:
        user = callback.from_user
        tickets = await recent_tickets(session, limit=TICKETS_LIMIT)
        logger.info(
            "tickets_list user=%d (@%s) count=%d",
            user.id if user else 0,
            (user.username if user else None) or "?",
            len(tickets),
        )
        if not tickets:
            await callback.message.answer(t("tickets_empty"))
            await callback.answer()
            return

        lines = [t("tickets_header")]
        rows: list[tuple[str, str, int]] = []
        for kind, ticket in tickets:
            lines.append(format_ticket_summary(kind, ticket, t))
            rows.append(
                (f"{emoji_for_kind(kind)} #{ticket.id}", kind, ticket.id)
            )

        await callback.message.answer(
            "\n\n".join(lines), reply_markup=pick_ticket_kb(rows, t)
        )
        await callback.answer()

    @router.callback_query(StatusPickCB.filter())
    async def status_pick(
        callback: CallbackQuery,
        callback_data: StatusPickCB,
        t: Callable[..., str],
    ) -> None:
        """Ask the developer for the new status: Not started | In Dev | Completed."""
        user = callback.from_user
        logger.info(
            "status_pick user=%d (@%s) ticket=%s:%d",
            user.id if user else 0,
            (user.username if user else None) or "?",
            callback_data.kind,
            callback_data.ticket_id,
        )
        await callback.message.answer(
            t("choose_status", id=callback_data.ticket_id),
            reply_markup=status_kb(callback_data.kind, callback_data.ticket_id, t),
        )
        await callback.answer()

    @router.callback_query(StatusSetCB.filter())
    async def status_set(
        callback: CallbackQuery,
        callback_data: StatusSetCB,
        session: AsyncSession,
        db_user: User,
        i18n,
        t: Callable[..., str],
    ) -> None:
        ticket = await get_ticket(session, callback_data.kind, callback_data.ticket_id)
        if ticket is None:
            logger.warning(
                "status_set_ticket_not_found user=%d (@%s) ticket=%s:%d",
                db_user.user_id,
                db_user.username or "?",
                callback_data.kind,
                callback_data.ticket_id,
            )
            await callback.answer(t("member_not_found"), show_alert=True)
            return

        old_status = ticket.status.value
        status = TicketStatus(callback_data.status)
        completing = status is TicketStatus.COMPLETED
        taking = status is TicketStatus.IN_DEV
        await apply_status(
            session,
            ticket,
            status,
            completed_by_user_id=db_user.user_id if completing else None,
            completed_by_username=db_user.username if completing else None,
            started_by_user_id=db_user.user_id if taking else None,
            started_by_username=db_user.username if taking else None,
        )

        logger.info(
            "status_changed dev=%d (@%s) ticket=%s:%d old=%s new=%s",
            db_user.user_id,
            db_user.username or "?",
            callback_data.kind,
            callback_data.ticket_id,
            old_status,
            callback_data.status,
        )

        new_status_label = t(STATUS_KEYS[status])
        await callback.answer(t("status_updated", id=ticket.id, status=new_status_label))

        # Refresh the card so everyone in the chat sees the current state.
        with contextlib.suppress(Exception):
            await callback.message.edit_text(
                build_ticket_text(callback_data.kind, ticket, i18n.bound("en")),
                reply_markup=change_status_markup(
                    callback_data.kind, ticket.id, i18n.bound("en")
                ),
            )

    return router
