from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Field, Session, SQLModel, create_engine


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Thread(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    title: str = "New conversation"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Message(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    thread_id: str = Field(foreign_key="thread.id", index=True)
    role: str  # "user" | "assistant"
    body: str
    citations_json: str = "[]"  # list[Citation] as JSON
    created_at: datetime = Field(default_factory=_now)


def _var_dir() -> Path:
    return Path(os.environ.get("PURSER_VAR_DIR", "var"))


_engine = None


def engine():
    global _engine
    if _engine is None:
        var = _var_dir()
        var.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{var / 'app.sqlite'}")
        SQLModel.metadata.create_all(_engine)
    return _engine


def session() -> Session:
    return Session(engine())
