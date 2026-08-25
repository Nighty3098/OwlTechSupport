"""Team management: list, add, remove developers."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import User
from ...filters.developer import IsDeveloper
from ...keyboards.admin import team_menu_kb
from ...keyboards.callbacks import TeamCB
from ...services.members import extract_member_ref, resolve_member
from ...services.repo import add_developer, list_developers, remove_developer
from ...states import MemberInput

logger = logging.getLogger(__name__)

CHUNK_SIZE = 3500


def get_router() -> Router:
    router = Router(name="admin_team")
    router.callback_query.filter(IsDeveloper())
    router.message.filter(IsDeveloper())

    @router.callback_query(TeamCB.filter(F.action == "menu"))
    async def team_menu(callback: CallbackQuery, t: Callable[..., str]) -> None:
        user = callback.from_user
        logger.info(
            "team_menu user=%d (@%s)",
            user.id if user else 0,
            (user.username if user else None) or "?",
        )
        await callback.message.answer(t("team_title"), reply_markup=team_menu_kb(t))
        await callback.answer()

    @router.callback_query(TeamCB.filter(F.action == "add"))
    async def team_add_start(
        callback: CallbackQuery,
        state: FSMContext,
        t: Callable[..., str],
    ) -> None:
        user = callback.from_user
        logger.info(
            "team_add_start user=%d (@%s)",
            user.id if user else 0,
            (user.username if user else None) or "?",
        )
        await state.set_state(MemberInput.waiting)
        await state.update_data(action="add")
        await callback.message.answer(t("ask_member_add"))
        await callback.answer()

    @router.callback_query(TeamCB.filter(F.action == "remove"))
    async def team_remove_start(
        callback: CallbackQuery,
        state: FSMContext,
        t: Callable[..., str],
    ) -> None:
        user = callback.from_user
        logger.info(
            "team_remove_start user=%d (@%s)",
            user.id if user else 0,
            (user.username if user else None) or "?",
        )
        await state.set_state(MemberInput.waiting)
        await state.update_data(action="remove")
        await callback.message.answer(t("ask_member_remove"))
        await callback.answer()

    @router.message(MemberInput.waiting)
    async def member_input(
        message: Message,
        state: FSMContext,
        session: AsyncSession,
        db_user: User,
        bot: Bot,
        t: Callable[..., str],
    ) -> None:
        data = await state.get_data()
        action: str = data.get("action", "add")
        # The form stays open until a successful add/remove, so the admin
        # can retry immediately; /cancel exits explicitly.

        ref = extract_member_ref(message)
        if ref is None or (ref.user_id is None and ref.username is None):
            logger.info(
                "member_input_invalid user=%d (@%s) action=%s",
                db_user.user_id,
                db_user.username or "?",
                action,
            )
            await message.answer(t("invalid_input"))
            return

        if ref.hidden:
            logger.info(
                "member_input_hidden_forward user=%d (@%s) action=%s",
                db_user.user_id,
                db_user.username or "?",
                action,
            )
            await message.answer(t("forward_hidden"))
            return

        with contextlib.suppress(Exception):
            ref = await resolve_member(bot, ref)

        if action == "add":
            if ref.user_id is None:
                # Could not resolve the id from the username.
                logger.info(
                    "member_resolve_failed user=%d (@%s) target=@%s",
                    db_user.user_id,
                    db_user.username or "?",
                    ref.username or "?",
                )
                await message.answer(t("cannot_resolve"))
                return
            developer = await add_developer(
                session,
                user_id=ref.user_id,
                username=ref.username,
                added_by_user_id=db_user.user_id,
                added_by_username=db_user.username,
            )
            label = developer.username or str(developer.user_id)
            logger.info(
                "developer_added by=%d (@%s) target=%d (@%s)",
                db_user.user_id,
                db_user.username or "?",
                developer.user_id,
                label,
            )
            await message.answer(t("member_added", username=label))
        else:
            victim = await remove_developer(session, user_id=ref.user_id, username=ref.username)
            if victim is None:
                logger.info(
                    "developer_remove_not_found user=%d (@%s) target=%d (@%s)",
                    db_user.user_id,
                    db_user.username or "?",
                    ref.user_id or 0,
                    ref.username or "?",
                )
                await message.answer(t("member_not_found"))
                return
            logger.info(
                "developer_removed by=%d (@%s) target=%d (@%s)",
                db_user.user_id,
                db_user.username or "?",
                victim.user_id,
                victim.username or "?",
            )
            await message.answer(
                t("member_removed", username=victim.username or str(victim.user_id))
            )
        await state.clear()

    @router.callback_query(TeamCB.filter(F.action == "list"))
    async def team_list(
        callback: CallbackQuery,
        session: AsyncSession,
        t: Callable[..., str],
    ) -> None:
        user = callback.from_user
        developers = await list_developers(session)
        logger.info(
            "team_list user=%d (@%s) count=%d",
            user.id if user else 0,
            (user.username if user else None) or "?",
            len(developers),
        )
        if not developers:
            await callback.message.answer(t("team_empty"))
            await callback.answer()
            return

        entries = [
            t(
                "team_entry",
                username=f"@{d.username}" if d.username else t("no_data"),
                user_id=d.user_id,
                added_by=f"@{d.added_by_username}"
                if d.added_by_username
                else t("no_data"),
                added_at=d.added_at.strftime("%d.%m.%Y %H:%M UTC"),
            )
            for d in developers
        ]
        for chunk in split_entries(entries, CHUNK_SIZE):
            await callback.message.answer(chunk)
        await callback.answer()

    return router


def split_entries(entries: list[str], size: int) -> list[str]:
    """Join entries with a blank line, splitting into messages of <= ``size`` chars."""
    chunks: list[str] = []
    current = ""
    for entry in entries:
        candidate = f"{current}\n\n{entry}" if current else entry
        if len(candidate) > size and current:
            chunks.append(current)
            current = entry
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
