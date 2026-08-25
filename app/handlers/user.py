"""User flows: bug report, feature request, contact developer."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Config
from ..db.models import User
from ..keyboards.callbacks import UserActionCB
from ..keyboards.user import user_menu_kb
from ..services.repo import create_ticket
from ..services.tickets import MAX_ATTACHMENTS, send_ticket_to_support
from ..states import TicketForm

SUPPORTED_ATTACHMENT_KINDS = {
    "photo": "photo",
    "document": "document",
    "video": "video",
    "audio": "audio",
}

# Telegram delivers an album (media group) as several messages; the ticket
# is submitted after this many seconds WITHOUT new items of the group, so
# slow uploads of big files simply extend the wait.
ALBUM_WAIT_SEC = 1.5


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


async def submit_ticket(
    session: AsyncSession,
    *,
    kind: str,
    reporter_user_id: int,
    reporter_username: str | None,
    content: str,
    attachments: list[dict],
    bot: Bot,
    config: Config,
    translator,
) -> None:
    ticket = await create_ticket(
        session,
        kind,
        reporter_user_id=reporter_user_id,
        reporter_username=reporter_username,
        content=content,
        attachments=attachments,
    )
    await send_ticket_to_support(bot, config, translator, kind, ticket)


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
        session: AsyncSession,
        sessionmaker: async_sessionmaker[AsyncSession],
        t: Callable[..., str],
        i18n,
        bot: Bot,
        config: Config,
    ) -> None:
        """The first message of the form becomes the ticket right away.

        Album items share a ``media_group_id`` and are merged into one
        ticket after a short debounce.
        """
        data = await state.get_data()
        kind = data.get("kind") or "bug"
        text, attachments = extract_content(message)

        group_id = message.media_group_id
        if group_id is None:
            if not text.strip() and not attachments:
                await message.answer(t("ticket_need_content"))
                return
            await submit_ticket(
                session,
                kind=kind,
                reporter_user_id=db_user.user_id,
                reporter_username=db_user.username,
                content=text.strip(),
                attachments=attachments,
                bot=bot,
                config=config,
                translator=i18n,
            )
            await state.clear()
            await message.answer(t("ticket_sent"), reply_markup=user_menu_kb(t))
            return

        albums = dict(data.get("albums", {}))
        parts = list(albums.get(group_id, []))
        parts.append({"text": text.strip(), "attachments": attachments})
        albums[group_id] = parts

        # Every new item invalidates previously scheduled finalizers and
        # extends the wait - only the latest generation submits.
        generation = int(data.get("albums_generation", 0)) + 1
        await state.update_data(albums=albums, albums_generation=generation)

        reporter_user_id = db_user.user_id
        reporter_username = db_user.username

        async def finish_album(expected_generation: int) -> None:
            await asyncio.sleep(ALBUM_WAIT_SEC)
            fresh = await state.get_data()
            if int(fresh.get("albums_generation", 0)) != expected_generation:
                return  # more items arrived - newer finalizer takes over
            pending = dict(fresh.get("albums", {}))
            collected = pending.pop(group_id, [])
            if not collected:
                return  # form was cancelled meanwhile
            await state.update_data(albums=pending)

            seen: set[str] = set()
            texts: list[str] = []
            for part in collected:
                value = part["text"]
                if value and value not in seen:
                    seen.add(value)
                    texts.append(value)
            merged = [
                attachment
                for part in collected
                for attachment in part["attachments"]
            ][:MAX_ATTACHMENTS]
            content = "\n".join(texts)
            if not content and not merged:
                return

            # The middleware session is closed by now - open a fresh one.
            async with sessionmaker() as album_session:
                await submit_ticket(
                    album_session,
                    kind=kind,
                    reporter_user_id=reporter_user_id,
                    reporter_username=reporter_username,
                    content=content,
                    attachments=merged,
                    bot=bot,
                    config=config,
                    translator=i18n,
                )
                await album_session.commit()
            await state.clear()
            await message.answer(t("ticket_sent"), reply_markup=user_menu_kb(t))

        asyncio.create_task(finish_album(generation))

    return router
