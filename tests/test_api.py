from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from purser_agent.schemas import Answer, CiteRef
from purser_api.db import reset_engine

pytestmark = pytest.mark.skipif(not Path("data/manual.sqlite").is_file(), reason="index not built")


def _parse_sse(body: str) -> list[dict]:
    """Turn an SSE response body into [{"event": ..., "data": ...}, ...]."""
    events = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        kind, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                kind = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        if kind is not None:
            events.append({"event": kind, "data": data})
    return events


class _FakeStream:
    def __init__(self, chunks: list[str], output: Answer) -> None:
        self._chunks = chunks
        self._output = output

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def stream_text(self, delta: bool = True):
        for chunk in self._chunks:
            yield chunk

    async def get_output(self) -> Answer:
        return self._output


class _FakeAgent:
    """Stands in for the real pydantic_ai agent so chat tests never hit an LLM."""

    def __init__(self, output: Answer, chunks: list[str] | None = None) -> None:
        self._output = output
        self._chunks = chunks if chunks is not None else [output.body]

    def run_stream(self, prompt: str, deps=None) -> _FakeStream:
        return _FakeStream(self._chunks, self._output)


class _RaisingAgent:
    def run_stream(self, prompt: str, deps=None):
        raise RuntimeError("model backend unavailable")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient bound to an isolated var dir for every test.

    `engine()` caches its engine on first call and reads `PURSER_VAR_DIR` only
    then, so without `reset_engine()` here a test would silently bind to
    whatever database an earlier test (or the developer's own `var/app.sqlite`)
    already created.
    """
    monkeypatch.setenv("PURSER_VAR_DIR", str(tmp_path))
    reset_engine()

    from purser_api.main import app

    with TestClient(app) as c:
        yield c
    reset_engine()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_toc_lists_sections(client):
    body = client.get("/api/toc").json()
    assert len([n for n in body if n["section"]]) == 37


def test_section_returns_verbatim_pages(client):
    body = client.get("/api/section/4.4", params={"page_from": 1, "page_to": 2}).json()
    assert len(body) == 2
    assert body[0]["page_in_section"] == 1


def test_unknown_section_404s(client):
    assert client.get("/api/section/99.9").status_code == 404


def test_page_image_returns_webp(client):
    r = client.get("/api/page/600/image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert len(r.content) > 1000


def test_page_image_out_of_range_404s(client):
    assert client.get("/api/page/99999/image").status_code == 404


def test_threads_start_empty(client):
    assert client.get("/api/threads").json() == []


def test_chat_with_unknown_thread_id_404s(client):
    """Guards against silently minting a fresh thread under a different id
    when the client's thread_id does not exist -- see chat.py's docstring.
    Without the pre-check, this would 500 with an IntegrityError instead
    (Message.thread_id's foreign key), or worse, silently succeed with a
    stray new thread.
    """
    resp = client.post("/api/chat", json={"thread_id": "does-not-exist", "message": "hi"})
    assert resp.status_code == 404
    assert client.get("/api/threads").json() == []


def test_get_unknown_thread_404s(client):
    assert client.get("/api/threads/does-not-exist").status_code == 404


def test_chat_streams_deltas_then_resolved_citations(client, monkeypatch):
    import purser_api.routers.chat as chat_mod

    answer = Answer(
        body="Evacuate via the nearest usable exit.",
        refs=[CiteRef(pdf_page=600, line_from=0, line_to=2)],
        not_in_manual=False,
    )
    monkeypatch.setattr(
        chat_mod, "get_agent", lambda: _FakeAgent(answer, chunks=["Evacuate ", "via the exit."])
    )
    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    resp = client.post("/api/chat", json={"message": "how do I evacuate?"})
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    assert [e["event"] for e in events] == ["thread", "delta", "delta", "citations", "done"]

    thread_id = json.loads(events[0]["data"])["thread_id"]
    deltas = [json.loads(e["data"])["text"] for e in events[1:3]]
    assert deltas == ["Evacuate ", "via the exit."]

    citations = json.loads(events[3]["data"])
    assert len(citations) == 1
    # The citation carries verbatim manual text spliced by resolve(), never
    # anything the (fake) model wrote -- the fake's Answer.body is the
    # evacuation sentence above, not this text.
    assert citations[0]["pdf_page"] == 600
    assert citations[0]["section"] == "4.4"
    assert citations[0]["label"] == "PART FOUR §4.4 p.34"
    assert citations[0]["text"] and citations[0]["text"] != answer.body

    # Persisted to the thread, retrievable afterwards.
    hist = client.get(f"/api/threads/{thread_id}").json()
    assert [m["role"] for m in hist] == ["user", "assistant"]
    assert hist[0]["body"] == "how do I evacuate?"
    assert hist[1]["body"] == answer.body
    assert hist[1]["citations"] == citations

    threads = client.get("/api/threads").json()
    assert [t["id"] for t in threads] == [thread_id]


def test_chat_not_in_manual_answer_has_no_citations(client, monkeypatch):
    """A `not_in_manual=True` / zero-ref answer is a normal result, not an
    error: the stream must still complete cleanly with an empty citations
    list, never an error event.
    """
    import purser_api.routers.chat as chat_mod

    answer = Answer(body="The capital of Portugal is Lisbon.", refs=[], not_in_manual=True)
    monkeypatch.setattr(chat_mod, "get_agent", lambda: _FakeAgent(answer))
    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    resp = client.post("/api/chat", json={"message": "what is the capital of Portugal?"})
    events = _parse_sse(resp.text)
    assert [e["event"] for e in events][-2:] == ["citations", "done"]
    citations_event = next(e for e in events if e["event"] == "citations")
    assert json.loads(citations_event["data"]) == []


def test_chat_drops_unresolvable_refs_but_keeps_good_ones(client, monkeypatch):
    """Exercises the real resolve_all against the real corpus (get_tools is
    not stubbed) -- only the agent is fake. A ref for a real page but a line
    range far past its length must be dropped, not crash the stream.
    """
    import purser_api.routers.chat as chat_mod

    answer = Answer(
        body="Two things.",
        refs=[
            CiteRef(pdf_page=600, line_from=0, line_to=2),
            CiteRef(pdf_page=1, line_from=900, line_to=901),
        ],
    )
    monkeypatch.setattr(chat_mod, "get_agent", lambda: _FakeAgent(answer))
    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    resp = client.post("/api/chat", json={"message": "two things?"})
    events = _parse_sse(resp.text)
    citations = json.loads(next(e for e in events if e["event"] == "citations")["data"])
    assert len(citations) == 1
    assert citations[0]["pdf_page"] == 600


def test_chat_agent_failure_emits_error_event_not_500(client, monkeypatch):
    import purser_api.routers.chat as chat_mod

    monkeypatch.setattr(chat_mod, "get_agent", lambda: _RaisingAgent())
    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[-1]["event"] == "error"
    assert "model backend unavailable" in json.loads(events[-1]["data"])["detail"]

    # The user turn is persisted; the failed assistant turn is not.
    thread_id = json.loads(events[0]["data"])["thread_id"]
    hist = client.get(f"/api/threads/{thread_id}").json()
    assert [m["role"] for m in hist] == ["user"]


def test_chat_continues_an_existing_thread_instead_of_starting_a_new_one(client, monkeypatch):
    import purser_api.routers.chat as chat_mod

    answer = Answer(body="ok", refs=[], not_in_manual=True)
    monkeypatch.setattr(chat_mod, "get_agent", lambda: _FakeAgent(answer))
    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    first = _parse_sse(client.post("/api/chat", json={"message": "first"}).text)
    thread_id = json.loads(first[0]["data"])["thread_id"]

    second = _parse_sse(
        client.post("/api/chat", json={"thread_id": thread_id, "message": "second"}).text
    )
    assert json.loads(second[0]["data"])["thread_id"] == thread_id

    assert client.get("/api/threads").json() == [
        t for t in client.get("/api/threads").json() if t["id"] == thread_id
    ]
    hist = client.get(f"/api/threads/{thread_id}").json()
    assert [m["body"] for m in hist] == ["first", "ok", "second", "ok"]


def test_threads_are_listed_most_recently_updated_first(client, monkeypatch):
    import purser_api.routers.chat as chat_mod

    answer = Answer(body="ok", refs=[], not_in_manual=True)
    monkeypatch.setattr(chat_mod, "get_agent", lambda: _FakeAgent(answer))
    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    first = _parse_sse(client.post("/api/chat", json={"message": "alpha"}).text)
    first_id = json.loads(first[0]["data"])["thread_id"]
    second = _parse_sse(client.post("/api/chat", json={"message": "beta"}).text)
    second_id = json.loads(second[0]["data"])["thread_id"]

    ids = [t["id"] for t in client.get("/api/threads").json()]
    assert ids == [second_id, first_id]
