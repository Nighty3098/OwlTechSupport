"""Database access helpers (repository layer)."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import ChatTarget
from ..db.base import utcnow
from ..db.models import Bug, Developer, Feature, TicketMixin, TicketStatus, User

logger = logging.getLogger(__name__)

TICKET_KINDS: dict[str, type[Bug] | type[Feature]] = {"bug": Bug, "feature": Feature}
TICKET_KIND_BY_MODEL: dict[type, str] = {Bug: "bug", Feature: "feature"}


# ==== users ====


async def increment_user_counter(session: AsyncSession, user_id: int, kind: str) -> None:
    user = (await session.scalars(select(User).where(User.user_id == user_id))).first()
    if user is None:
        return
    if kind == "bug":
        user.reports += 1
    elif kind == "feature":
        user.features += 1


async def set_language(session: AsyncSession, user_id: int, language: str) -> None:
    user = (
        await session.scalars(select(User).where(User.user_id == user_id))
    ).first()
    if user is not None:
        user.language = language


# ==== developers / team ====


async def is_developer(
    session: AsyncSession,
    superadmin_ids: tuple[int, ...],
    user_id: int,
) -> bool:
    if user_id in superadmin_ids:
        return True
    developer = (
        await session.scalars(select(Developer).where(Developer.user_id == user_id))
    ).first()
    return developer is not None


async def find_developer(
    session: AsyncSession,
    *,
    user_id: int | None = None,
    username: str | None = None,
) -> Developer | None:
    stmt = select(Developer)
    if user_id is not None:
        stmt = stmt.where(Developer.user_id == user_id)
    elif username is not None:
        stmt = stmt.where(func.lower(Developer.username) == username.lower())
    else:
        return None
    return (await session.scalars(stmt)).first()


async def add_developer(
    session: AsyncSession,
    *,
    user_id: int,
    username: str | None,
    added_by_user_id: int,
    added_by_username: str | None,
) -> Developer:
    existing = await find_developer(session, user_id=user_id)
    if existing is not None:
        return existing
    developer = Developer(
        user_id=user_id,
        username=username,
        added_by_user_id=added_by_user_id,
        added_by_username=added_by_username,
        added_at=utcnow(),
    )
    session.add(developer)
    await session.flush()
    return developer


async def remove_developer(
    session: AsyncSession,
    *,
    user_id: int | None = None,
    username: str | None = None,
) -> Developer | None:
    victim = await find_developer(session, user_id=user_id, username=username)
    if victim is None:
        return None
    await session.execute(delete(Developer).where(Developer.id == victim.id))
    await session.flush()
    return victim


async def list_developers(session: AsyncSession) -> list[Developer]:
    return list(
        (await session.scalars(select(Developer).order_by(Developer.added_at))).all()
    )


async def seed_developers(session: AsyncSession, user_ids: Iterable[int]) -> list[int]:
    """Register superadmins as developers. Returns ids that were newly added.

    Existing rows without a username get it backfilled from the users table.
    """
    seeded: list[int] = []
    for user_id in user_ids:
        developer = await find_developer(session, user_id=user_id)
        known = (
            await session.scalars(select(User).where(User.user_id == user_id))
        ).first()
        if developer is None:
            session.add(
                Developer(
                    user_id=user_id,
                    username=known.username if known else None,
                    added_by_user_id=user_id,
                    added_by_username=None,
                    added_at=utcnow(),
                )
            )
            seeded.append(user_id)
        elif developer.username is None and known is not None:
            developer.username = known.username
            await session.flush()
    if seeded:
        await session.flush()
    return seeded


async def sync_developer_username(session: AsyncSession, user_id: int, username: str) -> None:
    """Mirror the current Telegram username onto the developers table."""
    developer = await find_developer(session, user_id=user_id)
    if developer is not None and developer.username != username:
        developer.username = username
        await session.flush()


# ==== tickets ====


async def count_new_tickets(session: AsyncSession) -> int:
    """Number of tickets that have not been started yet."""
    bugs = await session.scalar(
        select(func.count()).select_from(Bug).where(Bug.status == TicketStatus.NOT_STARTED)
    )
    features = await session.scalar(
        select(func.count())
        .select_from(Feature)
        .where(Feature.status == TicketStatus.NOT_STARTED)
    )
    return int(bugs or 0) + int(features or 0)


async def recent_tickets(
    session: AsyncSession,
    limit: int = 10,
) -> list[tuple[str, Bug | Feature]]:
    bugs = (await session.scalars(select(Bug).order_by(Bug.reported_at.desc()).limit(limit))).all()
    features = (
        await session.scalars(
            select(Feature).order_by(Feature.reported_at.desc()).limit(limit)
        )
    ).all()
    merged: list[tuple[datetime, str, Bug | Feature]] = [
        (t.reported_at, TICKET_KIND_BY_MODEL[type(t)], t) for t in (*bugs, *features)
    ]
    merged.sort(key=lambda row: row[0], reverse=True)
    return [(kind, ticket) for _, kind, ticket in merged[:limit]]


async def get_ticket(
    session: AsyncSession,
    kind: str,
    ticket_id: int,
) -> Bug | Feature | None:
    model = TICKET_KINDS.get(kind)
    if model is None:
        return None
    return await session.get(model, ticket_id)


async def create_ticket(
    session: AsyncSession,
    kind: str,
    *,
    reporter_user_id: int,
    reporter_username: str | None,
    content: str,
    attachments: list[dict],
) -> Bug | Feature:
    model = TICKET_KINDS[kind]
    ticket = model(
        reporter_user_id=reporter_user_id,
        reporter_username=reporter_username,
        content=content,
        attachments=attachments,
        status=TicketStatus.NOT_STARTED,
        reported_at=utcnow(),
    )
    session.add(ticket)
    await session.flush()
    logger.info(
        "db_ticket_created id=%d user=%d (@%s) type=%s",
        ticket.id,
        reporter_user_id,
        reporter_username or "?",
        kind,
    )
    await increment_user_counter(session, reporter_user_id, kind)
    return ticket


async def apply_status(
    session: AsyncSession,
    ticket: TicketMixin,
    status: TicketStatus,
    completed_by_user_id: int | None = None,
    completed_by_username: str | None = None,
    started_by_user_id: int | None = None,
    started_by_username: str | None = None,
) -> None:
    """Apply a new status and fill the corresponding audit columns."""
    previous = ticket.status
    ticket.status = status

    if status is TicketStatus.IN_DEV and previous is not TicketStatus.IN_DEV:
        ticket.updated_at = utcnow()
        # Mirror the developers table: the starter columns must hold the
        # same user_id/username pair that lives in developers.
        developer = (
            await find_developer(session, user_id=started_by_user_id)
            if started_by_user_id is not None
            else None
        )
        ticket.started_by_user_id = (
            developer.user_id if developer else started_by_user_id
        )
        ticket.started_by_username = (
            developer.username if developer else started_by_username
        )

    if status is TicketStatus.COMPLETED and previous is not TicketStatus.COMPLETED:
        ticket.completed_at = utcnow()
        ticket.completed_by_user_id = completed_by_user_id
        ticket.completed_by_username = completed_by_username
        developer = await find_developer(session, user_id=completed_by_user_id)
        if developer is not None and isinstance(ticket, Bug):
            developer.bugs_closed += 1
        elif developer is not None and isinstance(ticket, Feature):
            developer.features_closed += 1
    await session.flush()
    logger.info(
        "db_status_applied ticket_id=%d old=%s new=%s",
        ticket.id,
        previous.value,
        status.value,
    )


def support_destination(config_target: ChatTarget) -> dict:
    """Keyword args for send_message to honor chat + optional topic."""
    payload: dict = {"chat_id": config_target.chat_id}
    if config_target.topic_id is not None:
        payload["message_thread_id"] = config_target.topic_id
    return payload
