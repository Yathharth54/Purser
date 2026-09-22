from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import CheckConstraint, Engine, String, event
from sqlmodel import Field, Session, SQLModel, create_engine


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Thread(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    title: str = "New conversation"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now, sa_column_kwargs={"onupdate": _now})


class Message(SQLModel, table=True):
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"),)

    id: str = Field(default_factory=_new_id, primary_key=True)
    thread_id: str = Field(foreign_key="thread.id", index=True)
    role: Literal["user", "assistant"] = Field(sa_type=String)
    body: str
    citations_json: str = "[]"  # list[Citation] as JSON
    created_at: datetime = Field(default_factory=_now)


def _var_dir() -> Path:
    return Path(os.environ.get("PURSER_VAR_DIR", "var"))


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
        var = _var_dir()
        var.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{var / 'app.sqlite'}")
        event.listen(_engine, "connect", _enable_sqlite_fk)
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
