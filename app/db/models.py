"""Database models: users, developers, bugs, features."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SaEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utcnow


class TicketStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_DEV = "in_dev"
    COMPLETED = "completed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str | None] = mapped_column(String(8))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reports: Mapped[int] = mapped_column(default=0)
    features: Mapped[int] = mapped_column(default=0)


class Developer(Base):
    __tablename__ = "developers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    bugs_closed: Mapped[int] = mapped_column(default=0)
    features_closed: Mapped[int] = mapped_column(default=0)
    added_by_user_id: Mapped[int] = mapped_column(BigInteger)
    added_by_username: Mapped[str | None] = mapped_column(String(64))
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TicketMixin:
    """Shared columns for bugs and features tickets."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text, default="")
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    reporter_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id"), index=True
    )
    reporter_username: Mapped[str | None] = mapped_column(String(64))

    reported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    started_by_username: Mapped[str | None] = mapped_column(String(64))
    started_by_user_id: Mapped[int | None] = mapped_column(BigInteger)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    completed_by_user_id: Mapped[int | None] = mapped_column(BigInteger)
    completed_by_username: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[TicketStatus] = mapped_column(
        SaEnum(TicketStatus, native_enum=False, length=16),
        default=TicketStatus.NOT_STARTED,
        index=True,
    )


class Bug(TicketMixin, Base):
    __tablename__ = "bugs"


class Feature(TicketMixin, Base):
    __tablename__ = "features"


TICKET_MODELS: dict[str, type[Bug] | type[Feature]] = {
    "bug": Bug,
    "feature": Feature,
}
