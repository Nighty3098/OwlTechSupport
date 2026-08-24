"""User flows: bug report, feature request, contact developer."""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..config import Config
from ..db.models import User
from ..keyboards.callbacks import UserActionCB
from ..keyboards.user import submit_cancel_kb, user_menu_kb
from ..services.repo import create_ticket
from ..services.tickets import MAX_ATTACHMENTS, send_ticket_to_support
from ..states import TicketForm

router = Router(name="user")

SUPPORTED_ATTACHMENT_KINDS = {
    "photo": "photo",
    "document": "document",
    "video": "video",
    "audio": "audio",
}


@router.callback_query(
    UserActionCB.filter(F.action.in_({"bug", "feature", "contact"}))
)
async def user_action(
    callback: CallbackQuery,
    callback_data: UserActionCB,
    state: FSMContext,
    t: Callable[..., str],
    config: Config,
) -> None:
    action = callback_data.action
    if action == "contact":
        await state.clear()
        await callback.message.answer(t("contact_text", url=config.contact_url))
        await callback.answer()
        return

    await state.clear()
    await state.set_state(TicketForm.collecting)
    await state.update_data(kind=action, texts=[], attachments=[])
    prompt = t("bug_prompt") if action == "bug" else t("feature_prompt")
    await callback.message.answer(prompt, reply_markup=submit_cancel_kb(t))
    await callback.answer()


@router.callback_query(UserActionCB.filter(F.action == "cancel"))
async def cancel_form(
    callback: CallbackQuery,
    state: FSMContext,
    t: Callable[..., str],
) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        with contextlib.suppress(Exception):
            await callback.message.delete()
        await callback.message.answer(t("cancelled"))
    await callback.answer()


@router.callback_query(UserActionCB.filter(F.action == "submit"))
async def submit_ticket(
    callback: CallbackQuery,
    callback_data: UserActionCB,
    state: FSMContext,
    db_user: User,
    session,
    t: Callable[..., str],
    i18n,
    bot: Bot,
    config: Config,
) -> None:
    data = await state.get_data()
    texts: list[str] = [text for text in data.get("texts", []) if text]
    attachments: list[dict] = data.get("attachments", [])
    kind: str | None = data.get("kind")

    if kind is None or (not texts and not attachments):
        await callback.answer(t("nothing_to_send"), show_alert=True)
        return

    ticket = await create_ticket(
        session,
        kind,
        reporter_user_id=db_user.user_id,
        reporter_username=db_user.username,
        content="\n\n".join(texts),
        attachments=attachments,
    )
    await send_ticket_to_support(bot, config, i18n, kind, ticket)

    await state.clear()
    if isinstance(callback.message, Message):
        with contextlib.suppress(Exception):
            await callback.message.delete()
    await callback.message.answer(t("ticket_sent"), reply_markup=user_menu_kb(t))
    await callback.answer()


@router.message(TicketForm.collecting)
async def collect_message(message: Message, state: FSMContext) -> None:
    """Accumulate any text/media the user sends while filling a ticket."""
    data = await state.get_data()
    texts: list[str] = list(data.get("texts", []))
    attachments: list[dict] = list(data.get("attachments", []))

    if message.text:
        texts.append(message.text)

    for source_kind, attachment_kind in SUPPORTED_ATTACHMENT_KINDS.items():
        media = getattr(message, source_kind)
        if media is not None and len(attachments) < MAX_ATTACHMENTS:
            attachments.append({"file_id": media.file_id, "kind": attachment_kind})

    await state.update_data(texts=texts, attachments=attachments)
