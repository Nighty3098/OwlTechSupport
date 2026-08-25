"""Ticket rendering and delivery to the support chat."""

from __future__ import annotations

import contextlib
import html
from collections.abc import Callable
from datetime import datetime
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import Config
from ..db.models import Bug, Feature, TicketMixin, TicketStatus
from ..keyboards.callbacks import StatusPickCB
from .i18n import DEFAULT_LANGUAGE, Translator
from .repo import support_destination

DT_FORMAT = "%d.%m.%Y %H:%M UTC"
MAX_ATTACHMENTS = 10
PREVIEW_LIMIT = 80

STATUS_KEYS: dict[TicketStatus, str] = {
    TicketStatus.NOT_STARTED: "status_not_started",
    TicketStatus.IN_DEV: "status_in_dev",
    TicketStatus.COMPLETED: "status_completed",
}


def format_dt(value: datetime | None) -> str:
    return value.strftime(DT_FORMAT) if value else "—"


def author_label(username: str | None, user_id: int | None = None) -> str:
    """@username when known, otherwise the numeric id."""
    if username:
        return f"@{username}"
    if user_id is not None:
        return str(user_id)
    return "—"


def kind_label(kind: str, t: Callable[..., str]) -> str:
    return t("lbl_bug") if kind == "bug" else t("lbl_feature")


def emoji_for_kind(kind: str) -> str:
    return "🐞" if kind == "bug" else "💡"


def _preview(content: str) -> str:
    single_line = content.replace("\n", " ").strip()
    if len(single_line) > PREVIEW_LIMIT:
        return html.escape(single_line[:PREVIEW_LIMIT].rstrip(), quote=False) + "…"
    return html.escape(single_line, quote=False)


def format_ticket_summary(kind: str, ticket: TicketMixin, t: Callable[..., str]) -> str:
    """Compact multi-line summary used in the latest-tickets list."""
    lines = [
        f"{emoji_for_kind(kind)} #{ticket.id} · {t(STATUS_KEYS[ticket.status])}",
        f"{t('lbl_reporter')}: "
        + html.escape(author_label(ticket.reporter_username, ticket.reporter_user_id), quote=False),
        f"{t('lbl_reported_at')}: {format_dt(ticket.reported_at)}",
    ]
    if ticket.attachments:
        lines.append(f"{t('lbl_attachments')}: {len(ticket.attachments)}")
    if ticket.content:
        lines.append(_preview(ticket.content))

    # Work stage is relevant until the ticket is closed.
    if ticket.status is TicketStatus.COMPLETED:
        who = html.escape(
            author_label(ticket.completed_by_username, ticket.completed_by_user_id),
            quote=False,
        )
        lines.append(
            f"{t('lbl_completed_at')}: {format_dt(ticket.completed_at)} · "
            f"{t('lbl_completed_by')}: {who}"
        )
    elif ticket.status is TicketStatus.IN_DEV:
        who = html.escape(
            author_label(ticket.started_by_username, ticket.started_by_user_id),
            quote=False,
        )
        lines.append(
            f"{t('lbl_taken_at')}: {format_dt(ticket.updated_at)} · "
            f"{t('lbl_started_by')}: {who}"
        )
    return "\n".join(lines)


def build_ticket_text(kind: str, ticket: TicketMixin, t: Callable[..., str]) -> str:
    """Full ticket card with all DB fields (HTML parse mode)."""
    status_label = t(STATUS_KEYS[ticket.status])
    reporter_html = html.escape(
        author_label(ticket.reporter_username, ticket.reporter_user_id), quote=False
    )
    lines = [
        f"{emoji_for_kind(kind)} <b>{kind_label(kind, t)} #{ticket.id}</b>",
        f"{t('lbl_reporter')}: {reporter_html} (<code>{ticket.reporter_user_id}</code>)",
        f"{t('lbl_status')}: {status_label}",
        f"{t('lbl_reported_at')}: {format_dt(ticket.reported_at)}",
    ]
    if ticket.updated_at is not None:
        lines.append(f"{t('lbl_taken_at')}: {format_dt(ticket.updated_at)}")
    if ticket.started_by_username or ticket.started_by_user_id:
        starter = html.escape(
            author_label(ticket.started_by_username, ticket.started_by_user_id),
            quote=False,
        )
        lines.append(f"{t('lbl_started_by')}: {starter}")
    if ticket.completed_at is not None:
        lines.append(f"{t('lbl_completed_at')}: {format_dt(ticket.completed_at)}")
    if ticket.completed_by_username or ticket.completed_by_user_id:
        completed_by = html.escape(
            author_label(ticket.completed_by_username, ticket.completed_by_user_id),
            quote=False,
        )
        lines.append(f"{t('lbl_completed_by')}: {completed_by}")
    if ticket.attachments:
        lines.append(f"{t('lbl_attachments')}: {len(ticket.attachments)}")

    text = "\n".join(lines)
    if ticket.content:
        text += f"\n\n💬\n{html.escape(ticket.content, quote=False)}"
    return text


def change_status_markup(kind: str, ticket_id: int, t: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("change_status"),
        callback_data=StatusPickCB(kind=kind, ticket_id=ticket_id),
    )
    builder.adjust(1)
    return builder.as_markup()


async def send_attachment(
    bot: Bot,
    destination: dict[str, Any],
    attachment: dict[str, Any],
) -> None:
    """Resend a stored attachment by its file_id."""
    file_id: str = attachment["file_id"]
    method_by_kind: dict[str, tuple[Any, str]] = {
        "photo": (bot.send_photo, "photo"),
        "video": (bot.send_video, "video"),
        "audio": (bot.send_audio, "audio"),
        "document": (bot.send_document, "document"),
    }
    sender, param = method_by_kind.get(
        attachment.get("kind", "document"), method_by_kind["document"]
    )
    with contextlib.suppress(Exception):  # broken file ids must not break delivery
        await sender(**destination, **{param: file_id})


async def send_ticket_to_support(
    bot: Bot,
    config: Config,
    translator: Translator,
    kind: str,
    ticket: Bug | Feature,
) -> None:
    """Deliver a freshly created ticket to the support chat/topic."""
    if config.support_chat is None:
        return
    t = translator.bound(DEFAULT_LANGUAGE)
    destination = support_destination(config.support_chat)

    await bot.send_message(
        **destination,
        text=build_ticket_text(kind, ticket, t),
        reply_markup=change_status_markup(kind, ticket.id, t),
    )
    for attachment in ticket.attachments[:MAX_ATTACHMENTS]:
        await send_attachment(bot, destination, attachment)
