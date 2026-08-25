"""Tests for keyboards, callbacks, filters and dispatcher wiring."""

from __future__ import annotations

import pytest
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser
from app.config import Config
from app.filters.developer import IsDeveloper
from app.keyboards.admin import admin_menu_kb, status_kb, team_menu_kb
from app.keyboards.callbacks import LangCB, StatusSetCB
from app.keyboards.user import LANGUAGES, language_kb, user_menu_kb


def test_language_keyboard_two_columns():
    kb = language_kb()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 6
    assert all(len(row) == 2 for row in kb.inline_keyboard)
    codes = {LangCB.unpack(btn.callback_data).code for btn in buttons}
    assert codes == {lang.code for lang in LANGUAGES}


def test_user_menu_buttons():
    from app.services.i18n import i18n

    kb = user_menu_kb(i18n.bound("ru"))
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert len(texts) == 3
    assert any("Баг" in txt for txt in texts)
    assert any("фич" in txt.lower() or "Фич" in txt for txt in texts)


def test_admin_and_team_keyboards():
    from app.services.i18n import i18n

    t = i18n.bound("en")
    assert len(admin_menu_kb(t).inline_keyboard[0]) == 2
    team_rows = team_menu_kb(t).inline_keyboard
    assert len(team_rows) == 3


def test_status_keyboard_three_statuses():
    from app.services.i18n import i18n

    kb = status_kb("bug", 5, i18n.bound("en"))
    data = [
        StatusSetCB.unpack(btn.callback_data) for row in kb.inline_keyboard for btn in row
    ]
    assert len(data) == 3
    assert all(item.ticket_id == 5 and item.kind == "bug" for item in data)
    statuses = {item.status for item in data}
    assert statuses == {"not_started", "in_dev", "completed"}


def test_callback_roundtrip():
    cb = StatusSetCB(kind="feature", ticket_id=12, status="completed")
    packed = cb.pack()
    unpacked = StatusSetCB.unpack(packed)
    assert (unpacked.kind, unpacked.ticket_id, unpacked.status) == (
        "feature",
        12,
        "completed",
    )
    assert LangCB(code="ja").pack() == "lang:ja"


def make_event(user_id: int):
    user = TgUser(id=user_id, is_bot=False, first_name="X")
    msg = Message(
        message_id=1,
        date=__import__("datetime").datetime.now(),
        chat=Chat(id=1, type="private"),
        from_user=user,
    )
    return msg


@pytest.mark.asyncio()
async def test_is_developer_filter(session, config: Config):
    flt = IsDeveloper()
    assert await flt(make_event(42), session, config)  # superadmin
    assert not await flt(make_event(1), session, config)


def test_create_dispatcher(sessionmaker, config: Config):
    from aiogram import Dispatcher
    from app.main import create_dispatcher

    dp = create_dispatcher(config, sessionmaker)
    assert isinstance(dp, Dispatcher)
    assert len(dp.sub_routers) == 5
