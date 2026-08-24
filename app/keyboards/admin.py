"""Inline keyboards for admins / developers."""

from __future__ import annotations

from collections.abc import Callable

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..db.models import TicketStatus
from .callbacks import StatusPickCB, StatusSetCB, TeamCB, TicketsListCB


def admin_menu_kb(t: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_tickets"), callback_data=TicketsListCB())
    builder.button(text=t("btn_team"), callback_data=TeamCB(action="menu"))
    builder.adjust(2)
    return builder.as_markup()


def team_menu_kb(t: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_team_list"), callback_data=TeamCB(action="list"))
    builder.button(text=t("btn_team_add"), callback_data=TeamCB(action="add"))
    builder.button(text=t("btn_team_remove"), callback_data=TeamCB(action="remove"))
    builder.adjust(1)
    return builder.as_markup()


STATUS_KEYS: dict[TicketStatus, str] = {
    TicketStatus.NOT_STARTED: "status_not_started",
    TicketStatus.IN_DEV: "status_in_dev",
    TicketStatus.COMPLETED: "status_completed",
}


def status_kb(kind: str, ticket_id: int, t: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for status_value in TicketStatus:
        builder.button(
            text=t(STATUS_KEYS[status_value]),
            callback_data=StatusSetCB(
                kind=kind,
                ticket_id=ticket_id,
                status=status_value.value,
            ),
        )
    builder.adjust(1)
    return builder.as_markup()


def pick_ticket_kb(rows: list[tuple[str, str, int]], t: Callable[..., str]) -> InlineKeyboardMarkup:
    """Rows of ``(label, kind, ticket_id)`` for the latest tickets list."""
    builder = InlineKeyboardBuilder()
    for label, kind, ticket_id in rows:
        builder.button(
            text=f"{label} {t('change_status')}",
            callback_data=StatusPickCB(kind=kind, ticket_id=ticket_id),
        )
    builder.adjust(1)
    return builder.as_markup()
