from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from purser_api.db import Message, Thread, engine, reset_engine, session


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """A fresh engine bound to a throwaway directory, torn down after the test.

    Without `reset_engine()`, `engine()`'s module-level cache would keep
    whichever database the process first touched, so `PURSER_VAR_DIR` set
    here would be silently ignored.
    """
    monkeypatch.setenv("PURSER_VAR_DIR", str(tmp_path))
    reset_engine()
    yield tmp_path
    reset_engine()


def test_engine_creates_app_sqlite_under_purser_var_dir_and_round_trips(isolated_db):
    tmp_path = isolated_db
    engine()
    assert (tmp_path / "app.sqlite").is_file()

    with session() as s:
        thread = Thread(title="evac drill")
        s.add(thread)
        s.commit()
        s.refresh(thread)

        message = Message(thread_id=thread.id, role="user", body="hello")
        s.add(message)
        s.commit()
        s.refresh(message)

        assert s.exec(select(Thread)).all() == [thread]
        assert [m.id for m in s.exec(select(Message)).all()] == [message.id]
        assert thread.created_at.tzinfo is not None
        assert message.created_at.tzinfo is not None

        s.add(Message(thread_id="does-not-exist", role="user", body="orphan"))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()

        s.add(Message(thread_id=thread.id, role="banana", body="bad role"))
        with pytest.raises(IntegrityError):
            s.commit()


# --- Postgres in production, SQLite everywhere else ---------------------------


def test_tests_never_see_the_real_database_or_passcode():
    """.env now holds the live Neon URL and the app passcode; conftest must hide
    both so no test can write to production data or be locked out by auth."""
    import os

    assert "DATABASE_URL" not in os.environ
    assert "PURSER_PASSCODE" not in os.environ


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgres://u:p@host/db?sslmode=require",
            "postgresql+psycopg://u:p@host/db?sslmode=require",
        ),
        ("postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ],
)
def test_a_database_url_selects_postgres_through_psycopg(monkeypatch, given, expected):
    from purser_api.db import database_url

    monkeypatch.setenv("DATABASE_URL", given)
    assert database_url() == expected


def test_without_a_database_url_chats_live_in_local_sqlite(monkeypatch, tmp_path):
    from purser_api.db import database_url

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PURSER_VAR_DIR", str(tmp_path))
    assert database_url() == f"sqlite:///{tmp_path / 'app.sqlite'}"


def test_citations_are_stored_as_json_not_a_string(isolated_db):
    payload = [{"pdf_page": 597, "text": "open the door"}]
    with session() as s:
        thread = Thread(title="t")
        s.add(thread)
        s.commit()
        s.add(Message(thread_id=thread.id, role="assistant", body="b", citations_json=payload))
        s.commit()
    with session() as s:
        [m] = s.exec(select(Message)).all()
        assert m.citations_json == payload


def test_pruning_keeps_the_most_recently_used_chats_and_their_messages(isolated_db):
    from datetime import UTC, datetime, timedelta

    from purser_api.db import prune_threads

    base = datetime(2026, 9, 1, tzinfo=UTC)
    with session() as s:
        for n in range(5):
            t = Thread(id=f"t{n}", title=f"chat {n}", updated_at=base + timedelta(days=n))
            s.add(t)
            s.commit()
            s.add(Message(thread_id=t.id, role="user", body=f"q{n}"))
            s.commit()
        removed = prune_threads(s, keep=3)
        assert removed == 2
        assert sorted(t.id for t in s.exec(select(Thread)).all()) == ["t2", "t3", "t4"]
        assert sorted(m.body for m in s.exec(select(Message)).all()) == ["q2", "q3", "q4"]
