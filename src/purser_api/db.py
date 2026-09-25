from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Engine,
    ForeignKey,
    String,
    TypeDecorator,
    event,
)
from sqlalchemy import delete as sa_delete
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Session, SQLModel, create_engine, select


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class _UTCDateTime(TypeDecorator):
    """timestamptz on Postgres; on SQLite, which stores no zone, read back as UTC.

    Without this a SQLite round trip returns naive datetimes, and the history's
    `updated_at.isoformat()` would reach the phone with no offset at all.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


_TZ = _UTCDateTime()


class Thread(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    title: str = "New conversation"
    created_at: datetime = Field(default_factory=_now, sa_type=_TZ)
    # "Last used": bumped on every turn, so the history lists, and prunes, by it.
    updated_at: datetime = Field(
        default_factory=_now, sa_type=_TZ, sa_column_kwargs={"onupdate": _now, "index": True}
    )


class Message(SQLModel, table=True):
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"),)

    id: str = Field(default_factory=_new_id, primary_key=True)
    # ON DELETE CASCADE: removing a chat removes its messages in the database.
    thread_id: str = Field(
        sa_column=Column(String, ForeignKey("thread.id", ondelete="CASCADE"), index=True)
    )
    role: Literal["user", "assistant"] = Field(sa_type=String)
    body: str
    # list[Citation] -- real JSON (jsonb on Postgres), not a string of it.
    citations_json: list = Field(
        default_factory=list, sa_column=Column(JSON().with_variant(JSONB(), "postgresql"))
    )
    created_at: datetime = Field(default_factory=_now, sa_type=_TZ)


class LoginFailure(SQLModel, table=True):
    """One wrong passcode attempt. Counted across all instances to pause logins."""

    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=_now, sa_type=_TZ, sa_column_kwargs={"index": True})


def _var_dir() -> Path:
    return Path(os.environ.get("PURSER_VAR_DIR", "var"))


def database_url() -> str:
    """Where chats live: Postgres when DATABASE_URL is set (Neon on Vercel,
    whose function filesystem is wiped between requests), else local SQLite."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        for scheme in ("postgresql://", "postgres://"):
            if url.startswith(scheme):
                return "postgresql+psycopg://" + url[len(scheme) :]
        return url
    return f"sqlite:///{_var_dir() / 'app.sqlite'}"


def max_threads() -> int:
    """How many chats to keep. The least recently used beyond this are pruned."""
    # At least 1: pruning to 0 would delete the chat being started.
    return max(1, int(os.environ.get("PURSER_MAX_THREADS", "100")))


def prune_threads(s: Session, keep: int) -> int:
    """Delete every chat but the `keep` most recently used, with their messages.

    Messages are deleted explicitly rather than relying on ON DELETE CASCADE,
    so SQLite databases created before the cascade existed are pruned too.
    Returns how many chats were removed.
    """
    stale = s.exec(select(Thread.id).order_by(Thread.updated_at.desc()).offset(keep)).all()
    if not stale:
        return 0
    s.exec(sa_delete(Message).where(Message.thread_id.in_(stale)))
    s.exec(sa_delete(Thread).where(Thread.id.in_(stale)))
    s.commit()
    return len(stale)


def _enable_sqlite_fk(dbapi_connection, connection_record) -> None:
    """SQLite ships foreign-key enforcement OFF by default, per connection.

    Without this, `Message.thread_id`'s foreign_key declaration is decorative:
    a message pointing at a nonexistent thread commits silently.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_engine: Engine | None = None


def engine() -> Engine:
    global _engine
    if _engine is None:
        url = database_url()
        if url.startswith("sqlite"):
            _var_dir().mkdir(parents=True, exist_ok=True)
            _engine = create_engine(url)
            event.listen(_engine, "connect", _enable_sqlite_fk)
        else:
            # Neon closes idle connections; pre-ping replaces a dead one
            # instead of failing the request that happens to draw it.
            _engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=3)
        SQLModel.metadata.create_all(_engine)
    return _engine


def reset_engine() -> None:
    """Drop the cached engine so a new `PURSER_VAR_DIR` takes effect.

    Needed by tests: `engine()` otherwise caches its first engine for the
    life of the process, so a test that reads `PURSER_VAR_DIR` after another
    test (or the real app) already called `engine()` would silently bind to
    that earlier database instead of its own isolated one.
    """
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def session() -> Session:
    return Session(engine())
