"""FSM states used across handlers."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class TicketForm(StatesGroup):
    """Collecting bug/feature content and attachments from a user."""

    collecting = State()


class MemberInput(StatesGroup):
    """Waiting for username / user id / forwarded message from an admin."""

    waiting = State()
