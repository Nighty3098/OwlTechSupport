"""Parsing and resolving team member references."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import Message, MessageOriginHiddenUser, MessageOriginUser


@dataclass(slots=True)
class MemberRef:
    username: str | None = None
    user_id: int | None = None
    hidden: bool = False


def extract_member_ref(message: Message) -> MemberRef | None:
    """Extract a member reference from text (@name / id) or a forwarded message."""
    # Forwarded message (legacy field and modern forward_origin).
    if message.forward_from is not None:
        return MemberRef(username=message.forward_from.username, user_id=message.forward_from.id)
    origin = message.forward_origin
    if isinstance(origin, MessageOriginUser):
        sender = origin.sender_user
        return MemberRef(username=sender.username, user_id=sender.id)
    if isinstance(origin, MessageOriginHiddenUser):
        # The author forbids forwarding with their identity revealed.
        return MemberRef(hidden=True)

    if not message.text:
        return None

    # text_mention entity: hidden username but known user object.
    for entity in message.entities or []:
        if entity.type == "text_mention" and entity.user is not None:
            return MemberRef(username=entity.user.username, user_id=entity.user.id)

    raw = message.text.strip().lstrip("@")
    if raw.isdigit():
        return MemberRef(user_id=int(raw))
    if raw and " " not in raw:
        return MemberRef(username=raw.removeprefix("@"))
    return None


async def resolve_member(bot: Bot, ref: MemberRef) -> MemberRef:
    """Fill in the missing side of the reference when possible.

    Resolving ``username -> user_id`` uses :meth:`Bot.get_chat`, which works
    only if the bot has already seen the user; failures are ignored.
    """
    if ref.user_id is None and ref.username is not None:
        try:
            chat = await bot.get_chat(f"@{ref.username}")
            ref.user_id = chat.id
        except Exception:  # noqa: BLE001 - resolution is best-effort
            pass
    return ref
