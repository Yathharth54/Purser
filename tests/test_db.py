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
