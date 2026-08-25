"""Tests for repository layer and models."""

from __future__ import annotations

import pytest
from app.db.models import Bug, Developer, Feature, TicketStatus, User
from app.services.repo import (
    add_developer,
    apply_status,
    count_new_tickets,
    create_ticket,
    find_developer,
    increment_user_counter,
    is_developer,
    list_developers,
    recent_tickets,
    remove_developer,
    seed_developers,
    set_language,
    sync_developer_username,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
async def user(session: AsyncSession) -> User:
    u = User(user_id=100, username="reporter")
    session.add(u)
    await session.flush()
    return u


@pytest.fixture()
async def developer(session: AsyncSession) -> Developer:
    d = Developer(
        user_id=200,
        username="dev",
        added_by_user_id=42,
        added_by_username="boss",
    )
    session.add(d)
    await session.flush()
    return d


async def test_user_defaults(session: AsyncSession, user: User):
    stored = (await session.scalars(select(User).where(User.user_id == 100))).one()
    assert stored.started_at is not None
    assert stored.reports == 0
    assert stored.features == 0
    assert stored.language is None


async def test_set_language(session: AsyncSession, user: User):
    await set_language(session, user.user_id, "ja")
    assert user.language == "ja"


async def test_increment_counters(session: AsyncSession, user: User):
    await increment_user_counter(session, user.user_id, "bug")
    await increment_user_counter(session, user.user_id, "bug")
    await increment_user_counter(session, user.user_id, "feature")
    assert (user.reports, user.features) == (2, 1)


async def test_is_developer(session: AsyncSession, developer: Developer):
    assert await is_developer(session, (42,), 42)
    assert await is_developer(session, (), 200)
    assert not await is_developer(session, (42,), 999)


async def test_add_and_find_developer(session: AsyncSession):
    created = await add_developer(
        session,
        user_id=300,
        username="NewDev",
        added_by_user_id=42,
        added_by_username="boss",
    )
    found = await find_developer(session, username="newdev")  # case-insensitive
    assert found is not None and found.id == created.id
    again = await add_developer(
        session,
        user_id=300,
        username="NewDev",
        added_by_user_id=1,
        added_by_username="x",
    )
    assert again.id == created.id  # no duplicates


async def test_remove_developer(session: AsyncSession, developer: Developer):
    victim = await remove_developer(session, user_id=200)
    assert victim is not None and victim.id == developer.id
    assert await find_developer(session, user_id=200) is None
    assert await remove_developer(session, username="ghost") is None


async def test_list_developers_sorted_by_added_at(session: AsyncSession):
    first = await add_developer(
        session, user_id=1, username="a", added_by_user_id=9, added_by_username="b"
    )
    second = await add_developer(
        session, user_id=2, username="c", added_by_user_id=9, added_by_username="b"
    )
    devs = await list_developers(session)
    assert [d.id for d in devs] == sorted([first.id, second.id])


async def test_seed_developers_is_idempotent(
    session: AsyncSession,
    developer: Developer,
):
    seeded = await seed_developers(session, (200, 301, 302))
    assert seeded == [301, 302]
    assert await find_developer(session, user_id=200) is not None
    # Second run creates nothing.
    assert await seed_developers(session, (200, 301, 302)) == []


async def test_seed_developers_backfills_username(
    session: AsyncSession,
    user: User,
):
    await seed_developers(session, (user.user_id,))
    dev = await find_developer(session, user_id=user.user_id)
    assert dev is not None
    assert dev.username == "reporter"


async def test_seed_heals_existing_row_without_username(
    session: AsyncSession,
    user: User,
):
    session.add(Developer(user_id=user.user_id, added_by_user_id=user.user_id))
    await session.flush()
    assert await seed_developers(session, (user.user_id,)) == []
    dev = await find_developer(session, user_id=user.user_id)
    assert dev.username == "reporter"


async def test_sync_developer_username(session: AsyncSession, developer: Developer):
    await sync_developer_username(session, developer.user_id, "renamed")
    assert (await find_developer(session, user_id=developer.user_id)).username == "renamed"
    # Unknown users and unchanged names are no-ops.
    await sync_developer_username(session, 999, "ghost")
    await sync_developer_username(session, developer.user_id, "renamed")


async def test_create_ticket_and_counters(session: AsyncSession, user: User):
    ticket = await create_ticket(
        session,
        "bug",
        reporter_user_id=user.user_id,
        reporter_username=user.username,
        content="crash on start",
        attachments=[{"file_id": "f1", "kind": "photo"}],
    )
    assert isinstance(ticket, Bug)
    assert ticket.status is TicketStatus.NOT_STARTED
    assert ticket.reported_at is not None
    assert user.reports == 1

    feature = await create_ticket(
        session,
        "feature",
        reporter_user_id=user.user_id,
        reporter_username=None,
        content="dark mode",
        attachments=[],
    )
    assert isinstance(feature, Feature)
    assert user.features == 1
    assert await count_new_tickets(session) == 2


async def test_apply_status_transitions(
    session: AsyncSession,
    user: User,
    developer: Developer,
):
    ticket = await create_ticket(
        session,
        "feature",
        reporter_user_id=user.user_id,
        reporter_username=user.username,
        content="add search",
        attachments=[],
    )

    # Not started -> In Dev: stamps updated_at only.
    await apply_status(session, ticket, TicketStatus.IN_DEV)
    assert ticket.updated_at is not None
    assert ticket.completed_at is None

    taken_at = ticket.updated_at
    await apply_status(session, ticket, TicketStatus.IN_DEV)
    assert ticket.updated_at == taken_at  # repeated call does not restamp

    # In Dev -> Completed: fills completed_* fields and dev counters.
    await apply_status(
        session,
        ticket,
        TicketStatus.COMPLETED,
        completed_by_user_id=developer.user_id,
        completed_by_username=developer.username,
    )
    assert ticket.completed_at is not None
    assert ticket.completed_by_username == "dev"
    assert developer.features_closed == 1
    assert developer.bugs_closed == 0


async def test_apply_status_counts_bugs_separately(
    session: AsyncSession,
    user: User,
    developer: Developer,
):
    bug = await create_ticket(
        session,
        "bug",
        reporter_user_id=user.user_id,
        reporter_username=None,
        content="500 error",
        attachments=[],
    )
    await apply_status(
        session,
        bug,
        TicketStatus.COMPLETED,
        completed_by_user_id=developer.user_id,
        completed_by_username=developer.username,
    )
    assert developer.bugs_closed == 1
    assert developer.features_closed == 0


async def test_recent_tickets_merge_order(session: AsyncSession, user: User):
    for i in range(3):
        await create_ticket(
            session,
            "bug" if i % 2 else "feature",
            reporter_user_id=user.user_id,
            reporter_username=None,
            content=f"t{i}",
            attachments=[],
        )
    merged = await recent_tickets(session, limit=10)
    kinds = [kind for kind, _ in merged]
    assert len(merged) == 3
    assert set(kinds) == {"bug", "feature"}
    reported = [t.reported_at for _, t in merged]
    assert reported == sorted(reported, reverse=True)


async def test_recent_tickets_limit(session: AsyncSession, user: User):
    for i in range(15):
        await create_ticket(
            session,
            "bug",
            reporter_user_id=user.user_id,
            reporter_username=None,
            content=f"t{i}",
            attachments=[],
        )
    assert len(await recent_tickets(session, limit=5)) == 5
