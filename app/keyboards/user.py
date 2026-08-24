"""Inline keyboards for regular users."""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .callbacks import LangCB, UserActionCB


class Language(NamedTuple):
    label: str
    code: str


LANGUAGES: tuple[Language, ...] = (
    Language("🇷🇺 Русский", "ru"),
    Language("🇬🇧 English", "en"),
    Language("🇯🇵 日本語", "ja"),
    Language("🇨🇳 中文", "zh"),
    Language("🇪🇸 Español", "es"),
    Language("🇩🇪 Deutsch", "de"),
)


def language_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lang in LANGUAGES:
        builder.button(text=lang.label, callback_data=LangCB(code=lang.code))
    builder.adjust(2)
    return builder.as_markup()


def user_menu_kb(t: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_bug_report"), callback_data=UserActionCB(action="bug"))
    builder.button(text=t("btn_feature"), callback_data=UserActionCB(action="feature"))
    builder.button(text=t("btn_contact_dev"), callback_data=UserActionCB(action="contact"))
    builder.adjust(1)
    return builder.as_markup()


def submit_cancel_kb(t: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_submit"), callback_data=UserActionCB(action="submit"))
    builder.button(text=t("btn_cancel"), callback_data=UserActionCB(action="cancel"))
    builder.adjust(2)
    return builder.as_markup()
