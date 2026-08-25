"""End-to-end handler flow tests with a mocked Telegram session."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    Message,
    PhotoSize,
    Update,
)
from aiogram.types import (
    User as TgUser,
)
from app.config import Config
from app.db.models import Bug, Developer, Feature, TicketStatus, User
from app.main import create_dispatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SUPPORT_CHAT_ID = -1003800802201
TOPIC_ID = 37


class FakeSession(BaseSession):
    """Records every API call and returns minimal valid responses."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _extract(self, method: Any) -> tuple[str, dict[str, Any]]:
        data = {}
        for field in ("chat_id", "text", "message_thread_id"):
            if hasattr(method, field):
                value = getattr(method, field)
                data[field] = value
        if hasattr(method, "reply_markup"):
            data["reply_markup"] = method.reply_markup
        return type(method).__name__, data

    async def make_request(self, bot: Bot, method: Any, timeout: int | None = None):  # noqa: ANN001, ANN401
        name, data = self._extract(method)
        self.calls.append((name, data))
        if name == "SendMessage":
            return make_message(message_id=len(self.calls), chat_id=data.get("chat_id", 1))
        return True  # DeleteMessage / EditMessageText etc.

    async def close(self) -> None:  # pragma: no cover - nothing to release
        return None

    def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError


def make_message(
    message_id: int = 1,
    chat_id: int | str = 1000,
    from_user: TgUser | None = None,
    text: str | None = None,
    caption: str | None = None,
    photo: list[PhotoSize] | None = None,
    document=None,
    media_group_id: str | None = None,
) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(tz=UTC).replace(tzinfo=None),
        chat=Chat(id=chat_id, type="private"),
        from_user=from_user,
        text=text,
        caption=caption,
        photo=photo,
        document=document,
        media_group_id=media_group_id,
    )


def make_user(user_id: int = 100, username: str = "alice") -> TgUser:
    return TgUser(id=user_id, is_bot=False, first_name="Alice", username=username)


class Flow:
    """Drives updates through the dispatcher and records bot API calls."""

    def __init__(self, dp: Dispatcher, bot: Bot) -> None:
        self.dp = dp
        self.bot = bot
        self._uid = 0

    async def send_message_update(self, message: Message) -> None:
        self._uid += 1
        await self.dp.feed_update(self.bot, Update(update_id=self._uid, message=message))

    async def callback_update(self, callback: CallbackQuery) -> None:
        self._uid += 1
        await self.dp.feed_update(self.bot, Update(update_id=self._uid, callback_query=callback))

    def sent_texts(self) -> list[tuple[str, dict[str, Any]]]:
        return [call for call in self.bot.session.calls if call[0] == "SendMessage"]

    def deletions(self) -> int:
        return sum(1 for call in self.bot.session.calls if call[0] == "DeleteMessage")

    async def user_row(self, session: AsyncSession, user_id: int) -> User:
        return (await session.scalars(select(User).where(User.user_id == user_id))).one()


@pytest.fixture()
async def flow(sessionmaker: async_sessionmaker[AsyncSession], config: Config):
    dp = create_dispatcher(config, sessionmaker)
    bot = Bot(token="42:test-token", session=FakeSession())
    yield Flow(dp, bot)
    await bot.session.close()


async def test_full_user_flow(flow: Flow, sessionmaker: async_sessionmaker[AsyncSession]):
    alice = make_user()

    # 1. First /start -> language selection keyboard.
    await flow.send_message_update(make_message(text="/start", from_user=alice))
    first_texts = [data["text"] for _, data in flow.sent_texts()]
    assert any("Выбери язык" in txt or "Choose" in txt for txt in first_texts)

    # 2. Picks Russian -> greeting deleted (buttons cleaned), menu re-sent.
    greeting = make_message(from_user=alice)
    cb = CallbackQuery(
        id="cb1",
        from_user=alice,
        chat_instance="ci",
        data="lang:ru",
        message=greeting,
    )
    await flow.callback_update(cb)
    assert flow.deletions() == 1
    assert any("техподдержки" in data["text"] for _, data in flow.sent_texts())

    # 3. Opens bug report form.
    cb2 = CallbackQuery(
        id="cb2",
        from_user=alice,
        chat_instance="ci",
        data="uact:bug",
        message=make_message(from_user=alice),
    )
    await flow.callback_update(cb2)
    assert any("Опиши проблему" in data["text"] for _, data in flow.sent_texts())

    # 4. The very first message becomes the ticket right away (no submit button).
    await flow.send_message_update(make_message(text="App crashes on start", from_user=alice))

    support_sends = [
        data for _, data in flow.sent_texts() if data.get("chat_id") == SUPPORT_CHAT_ID
    ]
    assert len(support_sends) == 1
    assert "App crashes on start" in support_sends[0]["text"]
    assert support_sends[0].get("message_thread_id") == TOPIC_ID
    assert any("успешно" in data["text"] for _, data in flow.sent_texts())

    # DB side effects: ticket stored, user counter bumped.
    async with sessionmaker() as db:
        bugs = (await db.scalars(select(Bug))).all()
        assert len(bugs) == 1
        bug = bugs[0]
        assert bug.content == "App crashes on start"
        assert bug.attachments == []
        assert bug.status is TicketStatus.NOT_STARTED
        assert bug.reporter_username == "alice"

        alice_row = await flow.user_row(db, 100)
        assert alice_row.reports == 1
        assert alice_row.language == "ru"


async def test_one_shot_ticket_from_photo_with_caption(
    flow: Flow,
    sessionmaker: async_sessionmaker[AsyncSession],
):
    """A photo with a caption is enough: caption becomes the ticket text."""
    alice = make_user()
    await flow.send_message_update(make_message(text="/start", from_user=alice))
    await flow.callback_update(
        CallbackQuery(
            id="c1",
            from_user=alice,
            chat_instance="ci",
            data="lang:ru",
            message=make_message(from_user=alice),
        )
    )
    await flow.callback_update(
        CallbackQuery(
            id="c2",
            from_user=alice,
            chat_instance="ci",
            data="uact:feature",
            message=make_message(from_user=alice),
        )
    )

    await flow.send_message_update(
        make_message(
            from_user=alice,
            caption="Dark mode for the dashboard",
            photo=[PhotoSize(file_id="pic42", file_unique_id="u", width=20, height=20)],
        )
    )

    support_sends = [
        data for _, data in flow.sent_texts() if data.get("chat_id") == SUPPORT_CHAT_ID
    ]
    assert len(support_sends) == 1
    assert "Dark mode for the dashboard" in support_sends[0]["text"]

    async with sessionmaker() as db:
        features = (await db.scalars(select(Feature))).all()
        assert len(features) == 1
        assert features[0].content == "Dark mode for the dashboard"
        assert [a["file_id"] for a in features[0].attachments] == ["pic42"]
        assert [a["kind"] for a in features[0].attachments] == ["photo"]

    alice_row = await flow.user_row(db, 100)
    assert alice_row.features == 1


async def test_album_merges_into_single_ticket(
    flow: Flow,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch,
):
    """Several album items (same media_group_id) become ONE ticket."""
    import asyncio

    from aiogram.types import Document
    from app.handlers import user as user_handlers

    monkeypatch.setattr(user_handlers, "ALBUM_WAIT_SEC", 0.15)

    alice = make_user()
    await flow.send_message_update(make_message(text="/start", from_user=alice))
    await flow.callback_update(
        CallbackQuery(
            id="c1",
            from_user=alice,
            chat_instance="ci",
            data="lang:en",
            message=make_message(from_user=alice),
        )
    )
    await flow.callback_update(
        CallbackQuery(
            id="c2",
            from_user=alice,
            chat_instance="ci",
            data="uact:bug",
            message=make_message(from_user=alice),
        )
    )

    first = make_message(
        from_user=alice,
        caption="Album caption",
        document=Document(file_id="doc1", file_unique_id="u1"),
        media_group_id="grp-1",
    )
    second = make_message(
        from_user=alice,
        document=Document(file_id="doc2", file_unique_id="u2"),
        media_group_id="grp-1",
    )
    third = make_message(
        from_user=alice,
        document=Document(file_id="doc3", file_unique_id="u3"),
        media_group_id="grp-1",
    )
    # Gaps below ALBUM_WAIT_SEC emulate a slow upload of big files.
    await flow.send_message_update(first)
    await asyncio.sleep(0.08)
    await flow.send_message_update(second)
    await asyncio.sleep(0.08)
    await flow.send_message_update(third)

    # The debounce finalizer runs in the background.
    await asyncio.sleep(0.5)

    support_sends = [
        data for _, data in flow.sent_texts() if data.get("chat_id") == SUPPORT_CHAT_ID
    ]
    assert len(support_sends) == 1
    assert "Album caption" in support_sends[0]["text"]

    async with sessionmaker() as db:
        bugs = (await db.scalars(select(Bug))).all()
        assert len(bugs) == 1
        assert bugs[0].content == "Album caption"
        assert [a["file_id"] for a in bugs[0].attachments] == ["doc1", "doc2", "doc3"]


async def test_second_start_goes_straight_to_menu(flow: Flow):
    alice = make_user()
    await flow.send_message_update(make_message(text="/start", from_user=alice))
    await flow.callback_update(
        CallbackQuery(
            id="c1",
            from_user=alice,
            chat_instance="ci",
            data="lang:en",
            message=make_message(from_user=alice),
        )
    )
    calls_before = len(flow.sent_texts())
    await flow.send_message_update(make_message(text="/start", from_user=alice))
    new_texts = [data["text"] for _, data in flow.sent_texts()][calls_before:]
    assert any("support bot" in txt.lower() or "Owl" in txt for txt in new_texts)


async def test_admin_welcome_and_team_add(
    flow: Flow,
    sessionmaker: async_sessionmaker[AsyncSession],
):
    boss = make_user(user_id=42, username="boss")

    await flow.send_message_update(make_message(text="/start", from_user=boss))
    await flow.callback_update(
        CallbackQuery(
            id="c1",
            from_user=boss,
            chat_instance="ci",
            data="lang:ru",
            message=make_message(from_user=boss),
        )
    )
    # Admin sees the welcome with ticket counter and the admin menu keyboard.
    texts = [data["text"] for _, data in flow.sent_texts()]
    assert any("Добро пожаловать" in txt and "новых тикетов" in txt for txt in texts)
    welcome_calls = [
        call
        for call in flow.sent_texts()
        if "Добро пожаловать" in (call[1].get("text") or "")
    ]
    assert welcome_calls
    markup = welcome_calls[-1][1]["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    assert sum(len(row) for row in markup.inline_keyboard) == 2

    # Team menu -> add member by numeric id.
    await flow.callback_update(
        CallbackQuery(
            id="c2",
            from_user=boss,
            chat_instance="ci",
            data="team:add",
            message=make_message(chat_id=42, from_user=boss),
        )
    )
    await flow.send_message_update(
        make_message(chat_id=42, from_user=boss, text="999888777")
    )

    async with sessionmaker() as db:
        devs = (await db.scalars(select(Developer.user_id))).all()
        assert 999888777 in devs

    added_texts = [data["text"] for _, data in flow.sent_texts()]
    assert any("добавлен" in txt for txt in added_texts)
