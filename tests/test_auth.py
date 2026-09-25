"""The passcode gate. Nothing about the manual or her chats is served without it."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from purser_api.db import reset_engine

PASS = "tulip-42"


@pytest.fixture
def locked(tmp_path, monkeypatch):
    monkeypatch.setenv("PURSER_VAR_DIR", str(tmp_path))
    monkeypatch.setenv("PURSER_PASSCODE", PASS)
    monkeypatch.setattr("purser_api.auth.WRONG_PASSCODE_DELAY", 0)
    reset_engine()
    from purser_api.main import app

    with TestClient(app) as c:
        yield c
    reset_engine()


@pytest.mark.parametrize(
    "path", ["/api/toc", "/api/section/4.2", "/api/threads", "/api/page/597/image"]
)
def test_every_content_route_is_closed_without_the_passcode(locked, path):
    r = locked.get(path)
    assert r.status_code == 401
    assert "manual" not in r.text.lower() or "passcode" in r.text.lower()


def test_chat_is_closed_without_the_passcode(locked):
    assert locked.post("/api/chat", json={"message": "hi"}).status_code == 401


def test_health_and_session_stay_open_and_report_locked(locked):
    assert locked.get("/api/health").status_code == 200
    assert locked.get("/api/session").json() == {"authenticated": False, "required": True}


def test_a_wrong_passcode_is_refused(locked):
    r = locked.post("/api/login", json={"passcode": "nope"})
    assert r.status_code == 401
    assert "purser_session" not in r.cookies
    assert locked.get("/api/toc").status_code == 401


def test_the_right_passcode_opens_everything_and_is_remembered(locked):
    r = locked.post("/api/login", json={"passcode": PASS})
    assert r.status_code == 200
    token = r.cookies.get("purser_session")
    assert token and PASS not in token  # the cookie never carries the passcode
    assert "httponly" in r.headers["set-cookie"].lower()
    assert locked.get("/api/toc").status_code == 200
    assert locked.get("/api/session").json() == {"authenticated": True, "required": True}


def test_changing_the_passcode_logs_every_device_out(locked, monkeypatch):
    locked.post("/api/login", json={"passcode": PASS})
    monkeypatch.setenv("PURSER_PASSCODE", "a-new-one")
    assert locked.get("/api/toc").status_code == 401


def test_without_a_passcode_configured_the_app_is_open(tmp_path, monkeypatch):
    monkeypatch.setenv("PURSER_VAR_DIR", str(tmp_path))
    monkeypatch.delenv("PURSER_PASSCODE", raising=False)
    reset_engine()
    from purser_api.main import app

    with TestClient(app) as c:
        assert c.get("/api/toc").status_code == 200
        assert c.get("/api/session").json() == {"authenticated": True, "required": False}
    reset_engine()


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_api_docs_are_closed_too(locked, path):
    """They expose no data, but they map every endpoint and name the manual."""
    assert locked.get(path).status_code == 401


def test_the_gate_checks_the_path_the_app_actually_routes_on(tmp_path, monkeypatch):
    """Mounted under a prefix (root_path), /prefix/api/toc must still be gated."""
    monkeypatch.setenv("PURSER_VAR_DIR", str(tmp_path))
    monkeypatch.setenv("PURSER_PASSCODE", PASS)
    reset_engine()
    from purser_api.main import app

    with TestClient(app, root_path="/prefix") as c:
        assert c.get("/prefix/api/toc").status_code == 401
    reset_engine()


def test_repeated_wrong_guesses_pause_all_logins(locked, monkeypatch):
    """Parallel requests defeat a per-request delay, so failures are counted in
    the database -- shared by every instance -- and logins pause past a limit."""
    monkeypatch.setattr("purser_api.auth.MAX_FAILURES", 3)
    for _ in range(3):
        assert locked.post("/api/login", json={"passcode": "nope"}).status_code == 401
    r = locked.post("/api/login", json={"passcode": PASS})
    assert r.status_code == 429
    assert "purser_session" not in r.cookies


def test_old_wrong_guesses_stop_counting(locked, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from purser_api.db import LoginFailure, session

    monkeypatch.setattr("purser_api.auth.MAX_FAILURES", 3)
    with session() as s:
        for _ in range(5):
            s.add(LoginFailure(at=datetime.now(UTC) - timedelta(hours=2)))
        s.commit()
    assert locked.post("/api/login", json={"passcode": PASS}).status_code == 200
