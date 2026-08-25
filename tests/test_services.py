"""Tests for member reference parsing and ticket rendering."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram.types import Chat, Message, MessageEntity
from aiogram.types import User as TgUser
from app.db.models import Feature, TicketStatus
from app.services.members import MemberRef, extract_member_ref, resolve_member
from app.services.tickets import build_ticket_text


def make_message(**kwargs) -> Message:
    return Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"), **kwargs)


class TestExtractMemberRef:
    def test_from_username(self):
        ref = extract_member_ref(make_message(text="@some_dev"))
        assert ref == MemberRef(username="some_dev", user_id=None)

    def test_plain_username_without_at(self):
        ref = extract_member_ref(make_message(text="some_dev"))
        assert ref.username == "some_dev"

    def test_from_numeric_id(self):
        ref = extract_member_ref(make_message(text="123456789"))
        assert ref.user_id == 123456789

    def test_garbage_returns_none(self):
        assert extract_member_ref(make_message(text="hello world foo")) is None

    def test_empty_returns_none(self):
        assert extract_member_ref(make_message()) is None

    def test_from_forward(self):
        sender = TgUser(id=777, is_bot=False, first_name="F", username="fwd_user")
        msg = make_message(forward_from=sender)
        ref = extract_member_ref(msg)
        assert (ref.user_id, ref.username) == (777, "fwd_user")

    def test_from_text_mention_entity(self):
        mentioned = TgUser(id=555, is_bot=False, first_name="M", username="mentioned")
        msg = make_message(
            text="look at this guy",
            entities=[MessageEntity(type="text_mention", offset=0, length=4, user=mentioned)],
        )
        ref = extract_member_ref(msg)
        assert ref.user_id == 555

    def test_forward_origin_user(self):
        from aiogram.types import MessageOriginUser

        sender = TgUser(id=888, is_bot=False, first_name="O", username="origin_user")
        msg = make_message(
            forward_origin=MessageOriginUser(
                type="user", date=datetime.now(tz=UTC), sender_user=sender
            )
        )
        ref = extract_member_ref(msg)
        assert (ref.user_id, ref.username) == (888, "origin_user")

    def test_forward_origin_hidden_marks_ref(self):
        from aiogram.types import MessageOriginHiddenUser

        msg = make_message(
            forward_origin=MessageOriginHiddenUser(
                type="hidden_user",
                date=datetime.now(tz=UTC),
                sender_user_name="Secret Person",
            )
        )
        ref = extract_member_ref(msg)
        assert ref is not None
        assert ref.hidden
        assert ref.user_id is None and ref.username is None

    def test_forward_text_is_not_treated_as_username(self):
        from aiogram.types import MessageOriginHiddenUser

        msg = make_message(
            text="Hi",
            forward_origin=MessageOriginHiddenUser(
                type="hidden_user",
                date=datetime.now(tz=UTC),
                sender_user_name="Secret Person",
            ),
        )
        ref = extract_member_ref(msg)
        assert ref is not None and ref.hidden


class FakeBot:
    """get_chat stub: resolves only known usernames."""

    known = {"resolvable"}

    async def get_chat(self, username: str):
        class R:
            id = 321

        if username.lstrip("@") in self.known:
            return R()
        raise RuntimeError("chat not found")


@pytest.mark.asyncio()
async def test_resolve_member_fills_id():
    ref = await resolve_member(FakeBot(), MemberRef(username="resolvable"))
    assert ref.user_id == 321


@pytest.mark.asyncio()
async def test_resolve_member_keeps_none_on_failure():
    ref = await resolve_member(FakeBot(), MemberRef(username="ghost"))
    assert ref.user_id is None


def make_ticket(**kwargs) -> Feature:
    defaults: dict = {
        "id": 7,
        "content": "<b>dark</b> mode & <script>",
        "attachments": [{"file_id": "x", "kind": "photo"}],
        "reporter_user_id": 100,
        "reporter_username": "reporter",
        "reported_at": datetime(2026, 8, 25, 12, 0),
        "updated_at": datetime(2026, 8, 26, 9, 30),
        "completed_at": None,
        "completed_by_user_id": None,
        "completed_by_username": None,
        "status": TicketStatus.IN_DEV,
    }
    defaults.update(kwargs)
    return Feature(**defaults)


class TestTicketRendering:
    def _t(self):
        from app.services.i18n import i18n

        return i18n.bound("en")

    def test_card_contains_all_fields(self):
        text = build_ticket_text("feature", make_ticket(), self._t())
        assert "#7" in text
        assert "@reporter" in text and "100" in text
        assert "In Dev" in text
        assert "25.08.2026 12:00 UTC" in text
        assert "26.08.2026 09:30 UTC" in text
        assert "Attachments: 1" in text
        assert "&lt;script&gt;" in text  # html escaped

    def test_completed_block_appears_only_when_completed(self):
        t = self._t()
        pending = build_ticket_text("bug", make_ticket(), t)
        assert "Completed by" not in pending

        done = make_ticket(
            status=TicketStatus.COMPLETED,
            completed_at=datetime(2026, 8, 27, 1, 2),
            completed_by_user_id=200,
            completed_by_username="dev",
        )
        text = build_ticket_text("bug", done, t)
        assert "@dev" in text
        assert "27.08.2026 01:02 UTC" in text

    def test_started_by_shown_with_and_without_username(self):
        t = self._t()
        plain = build_ticket_text("bug", make_ticket(), t)
        assert "Started by" not in plain

        taken = make_ticket(
            updated_at=datetime(2026, 8, 26, 9, 30),
            started_by_user_id=200,
            started_by_username="dev",
        )
        text = build_ticket_text("bug", taken, t)
        assert "Started by: @dev" in text

        anonymous = make_ticket(
            updated_at=datetime(2026, 8, 26, 9, 30),
            started_by_user_id=200,
            started_by_username=None,
        )
        text = build_ticket_text("bug", anonymous, t)
        assert "Started by: 200" in text


class TestTicketSummary:
    def _t(self):
        from app.services.i18n import i18n

        return i18n.bound("en")

    def test_not_started_entry(self):
        from app.services.tickets import format_ticket_summary

        ticket = make_ticket(
            status=TicketStatus.NOT_STARTED,
            updated_at=None,
            started_by_user_id=None,
            started_by_username=None,
        )
        text = format_ticket_summary("bug", ticket, self._t())
        assert "#7" in text and "Not started" in text
        assert "Reporter: @reporter" in text
        assert "Created: 25.08.2026 12:00 UTC" in text
        assert "Attachments: 1" in text
        assert "&lt;b&gt;dark&lt;/b&gt; mode &amp; &lt;script&gt;" in text
        assert "Started by" not in text and "Completed" not in text

    def test_in_dev_entry_shows_stage(self):
        from app.services.tickets import format_ticket_summary

        ticket = make_ticket(
            status=TicketStatus.IN_DEV,
            updated_at=datetime(2026, 8, 26, 9, 30),
            started_by_user_id=200,
            started_by_username="dev",
        )
        text = format_ticket_summary("bug", ticket, self._t())
        assert "In Dev" in text
        assert "Taken at: 26.08.2026 09:30 UTC" in text
        assert "Started by: @dev" in text
        assert "Completed" not in text

    def test_completed_entry_hides_stage(self):
        from app.services.tickets import format_ticket_summary

        ticket = make_ticket(
            status=TicketStatus.COMPLETED,
            updated_at=datetime(2026, 8, 26, 9, 30),
            started_by_user_id=200,
            started_by_username="dev",
            completed_at=datetime(2026, 8, 27, 1, 2),
            completed_by_user_id=300,
            completed_by_username=None,
        )
        text = format_ticket_summary("bug", ticket, self._t())
        assert "Completed" in text
        assert "27.08.2026 01:02 UTC · Completed by: 300" in text
        # The work stage must disappear once the ticket is closed.
        assert "Taken at" not in text
        assert "Started by" not in text

    def test_long_content_is_trimmed(self):
        from app.services.tickets import PREVIEW_LIMIT, format_ticket_summary

        ticket = make_ticket(content="x" * (PREVIEW_LIMIT + 50))
        text = format_ticket_summary("bug", ticket, self._t())
        body_line = [line for line in text.splitlines() if line.startswith("x")][0]
        assert len(body_line) == PREVIEW_LIMIT + 1  # trimmed + ellipsis
        assert body_line.endswith("…")

    def test_no_content_no_quote_block(self):
        text = build_ticket_text("bug", make_ticket(content=""), self._t())
        assert "💬" not in text
