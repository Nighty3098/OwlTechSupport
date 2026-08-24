"""Ticket management for developers: list and status changes."""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import TicketStatus, User
from ...filters.developer import IsDeveloper
from ...keyboards.admin import STATUS_KEYS, pick_ticket_kb, status_kb
from ...keyboards.callbacks import StatusPickCB, StatusSetCB, TicketsListCB
from ...services.repo import apply_status, get_ticket, recent_tickets
from ...services.tickets import build_ticket_text, change_status_markup

router = Router(name="admin_tickets")
router.callback_query.filter(IsDeveloper())

TICKETS_LIMIT = 10


@router.callback_query(TicketsListCB.filter())
async def tickets_list(
    callback: CallbackQuery,
    session: AsyncSession,
    t: Callable[..., str],
) -> None:
    tickets = await recent_tickets(session, limit=TICKETS_LIMIT)
    if not tickets:
        await callback.message.answer(t("tickets_empty"))
        await callback.answer()
        return

    lines = [t("tickets_header")]
    rows: list[tuple[str, str, int]] = []
    for kind, ticket in tickets:
        emoji = "🐞" if kind == "bug" else "💡"
        status_label = t(STATUS_KEYS[ticket.status])
        preview = (ticket.content or "").replace("\n", " ")[:60]
        lines.append(f"{emoji} #{ticket.id} · {status_label}\n{preview}")
        rows.append((f"{emoji} #{ticket.id}", kind, ticket.id))

    await callback.message.answer("\n\n".join(lines), reply_markup=pick_ticket_kb(rows, t))
    await callback.answer()


@router.callback_query(StatusPickCB.filter())
async def status_pick(
    callback: CallbackQuery,
    callback_data: StatusPickCB,
    t: Callable[..., str],
) -> None:
    """Ask the developer for the new status: Not started | In Dev | Completed."""
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
        await callback.answer(t("member_not_found"), show_alert=True)
        return

    status = TicketStatus(callback_data.status)
    completing = status is TicketStatus.COMPLETED
    await apply_status(
        session,
        ticket,
        status,
        completed_by_user_id=db_user.user_id if completing else None,
        completed_by_username=db_user.username if completing else None,
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
