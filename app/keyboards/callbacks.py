"""Callback data factories."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class LangCB(CallbackData, prefix="lang"):
    code: str


class UserActionCB(CallbackData, prefix="uact"):
    action: str  # bug | feature | contact | submit | cancel


class TeamCB(CallbackData, prefix="team"):
    action: str  # menu | list | add | remove


class TicketsListCB(CallbackData, prefix="tks"):
    pass


class StatusPickCB(CallbackData, prefix="stp"):
    kind: str  # bug | feature
    ticket_id: int


class StatusSetCB(CallbackData, prefix="sts"):
    kind: str  # bug | feature
    ticket_id: int
    status: str  # TicketStatus value
