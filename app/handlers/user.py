"""User flows: bug report, feature request, contact developer."""

from __future__ import annotations

from collections.abc import Callable

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..config import Config
from ..db.models import User
from ..keyboards.callbacks import UserActionCB
from ..keyboards.user import user_menu_kb
from ..services.repo import create_ticket
from ..services.tickets import send_ticket_to_support
from ..states import TicketForm

SUPPORTED_ATTACHMENT_KINDS = {
    "photo": "photo",
    "document": "document",
    "video": "video",
    "audio": "audio",
}


def extract_content(message: Message) -> tuple[str, list[dict]]:
    """Text/caption plus supported attachments of a single message."""
    text = message.text or message.caption or ""
    attachments: list[dict] = []
    for source_kind, attachment_kind in SUPPORTED_ATTACHMENT_KINDS.items():
        media = getattr(message, source_kind)
        if media is None:
            continue
        # photo arrives as a list of sizes; keep the largest one.
        file_id = (
            max(media, key=lambda size: size.width).file_id
            if isinstance(media, list)
            else media.file_id
        )
        attachments.append({"file_id": file_id, "kind": attachment_kind})
    return text, attachments


def get_router() -> Router:
    router = Router(name="user")

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
        await state.update_data(kind=action)
        prompt = t("bug_prompt") if action == "bug" else t("feature_prompt")
        await callback.message.answer(prompt)
        await callback.answer()

    @router.message(TicketForm.collecting)
    async def receive_ticket(
        message: Message,
        state: FSMContext,
        db_user: User,
        session,
        t: Callable[..., str],
        i18n,
        bot: Bot,
        config: Config,
    ) -> None:
        """The very first message of the form becomes the ticket right away."""
        data = await state.get_data()
        kind = data.get("kind") or "bug"

        text, attachments = extract_content(message)
        if not text.strip() and not attachments:
            await message.answer(t("ticket_need_content"))
            return

        ticket = await create_ticket(
            session,
            kind,
            reporter_user_id=db_user.user_id,
            reporter_username=db_user.username,
            content=text.strip(),
            attachments=attachments,
        )
        await send_ticket_to_support(bot, config, i18n, kind, ticket)

        await state.clear()
        await message.answer(t("ticket_sent"), reply_markup=user_menu_kb(t))

    return router
