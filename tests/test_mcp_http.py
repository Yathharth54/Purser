"""/mcp over HTTP: off unless a token is set, closed without it, POST only."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

TOKEN = "s3cret-token"
H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "test", "version": "0"}},
}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}


def _client():
    from purser_api.main import app

    return TestClient(app, follow_redirects=False)


def _auth(token: str = TOKEN) -> dict:
    return {**H, "Authorization": f"Bearer {token}"}


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("PURSER_MCP_TOKEN", TOKEN)


def test_it_is_off_when_no_token_is_set(monkeypatch):
    monkeypatch.delenv("PURSER_MCP_TOKEN", raising=False)
    with _client() as c:
        assert c.post("/mcp", json=LIST, headers=_auth()).status_code == 404


def test_a_blank_token_counts_as_unset(monkeypatch):
    monkeypatch.setenv("PURSER_MCP_TOKEN", "   ")
    with _client() as c:
        assert c.post("/mcp", json=LIST, headers=_auth("")).status_code == 404


@pytest.mark.parametrize("headers", [H, _auth("wrong"), {**H, "Authorization": TOKEN}])
def test_it_is_closed_without_the_right_token(token, headers):
    with _client() as c:
        r = c.post("/mcp", json=LIST, headers=headers)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_the_right_token_lists_the_tools(token):
    with _client() as c:
        assert c.post("/mcp", json=INIT, headers=_auth()).status_code == 200
        r = c.post("/mcp", json=LIST, headers=_auth())
    assert r.status_code == 200  # on /mcp exactly, no 307 (Review Focus 2)
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == {"search", "toc", "read_section", "read_page", "lookup_term", "ask"}


def test_the_scheme_is_case_insensitive(token):
    with _client() as c:
        r = c.post("/mcp", json=LIST, headers={**H, "Authorization": f"bearer {TOKEN}"})
    assert r.status_code == 200


def test_a_token_stored_with_a_trailing_newline_still_works(monkeypatch):  # Review Focus 4
    monkeypatch.setenv("PURSER_MCP_TOKEN", TOKEN + "\n")
    with _client() as c:
        assert c.post("/mcp", json=LIST, headers=_auth()).status_code == 200


@pytest.mark.parametrize("method", ["get", "delete"])
def test_only_post_is_served(token, method):  # Review Focus 1: GET would hang
    with _client() as c:
        r = c.request(method.upper(), "/mcp", headers=_auth())
    assert r.status_code == 405
    assert r.headers["allow"] == "POST"


def test_it_survives_a_new_event_loop(token):  # Review Focus 3
    for _ in range(2):  # each TestClient runs its own loop
        with _client() as c:
            assert c.post("/mcp", json=LIST, headers=_auth()).status_code == 200


def test_the_passcode_gate_does_not_apply_to_mcp(token, monkeypatch):
    monkeypatch.setenv("PURSER_PASSCODE", "tulip-42")
    with _client() as c:
        assert c.post("/mcp", json=LIST, headers=_auth()).status_code == 200
