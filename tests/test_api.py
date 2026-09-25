from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import AgentRunResultEvent, FunctionToolCallEvent
from pydantic_ai.messages import ToolCallPart

from purser_agent.lookup import PurserDeps, build_agent
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


class _FakeRunEvents:
    """Mimics `AgentRunEvents`: an async context manager that is also an
    async iterator over pydantic_ai's own event dataclasses."""

    def __init__(self, events: list) -> None:
        self._events = events

    async def __aenter__(self) -> _FakeRunEvents:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for ev in self._events:
            yield ev


class _FakeAgent:
    """Stands in for the real pydantic_ai agent so most chat tests never hit
    an LLM -- but models the *real* `run_stream_events()` contract (a run of
    `FunctionToolCallEvent`s followed by one trailing `AgentRunResultEvent`)
    using pydantic_ai's own event dataclasses, not a hand-rolled stand-in.

    A previous version of this fake exposed `stream_text()`, a method the
    real streaming API for a structured-output agent does not have (it
    raises `"stream_text() can only be used with text responses"`); every
    test built on it was asserting the behaviour of a method that could
    never be called for real, so six green tests missed a chat endpoint
    that never worked. `test_chat_works_against_a_real_pydantic_ai_agent`
    below is the test that would have caught it.
    """

    def __init__(self, output: Answer, tool_calls: list[tuple[str, dict]] | None = None) -> None:
        self._output = output
        self._tool_calls = tool_calls or []
        self.prompts: list[str] = []

    def run_stream_events(self, prompt: str, deps=None) -> _FakeRunEvents:
        self.prompts.append(prompt)
        events: list = [
            FunctionToolCallEvent(part=ToolCallPart(tool_name=name, args=args))
            for name, args in self._tool_calls
        ]
        events.append(AgentRunResultEvent(result=SimpleNamespace(output=self._output)))
        return _FakeRunEvents(events)


class _RaisingAgent:
    def run_stream_events(self, prompt: str, deps=None):
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


def test_section_returns_readable_pages(client):
    r = client.get("/api/section/4.2")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 8
    assert all("blocks" in p and "numbered_lines" not in p for p in body)
    kinds = {b["kind"] for p in body for b in p["blocks"]}
    assert "heading" in kinds and "bullet" in kinds


def test_section_reader_slices_by_page_bounds(client):
    body = client.get("/api/section/4.4", params={"page_from": 1, "page_to": 2}).json()
    assert len(body) == 2
    assert body[0]["page_in_section"] == 1


def test_section_reader_returns_every_page_of_a_long_section(client):
    """Section 4.4 is 80 pages. The old UI capped the reader at 4 pages and
    40 lines -- this pins that the endpoint itself carries no such cap."""
    body = client.get("/api/section/4.4").json()
    assert len(body) == 80


def test_unknown_section_404s(client):
    assert client.get("/api/section/99.9").status_code == 404


def test_section_rejects_non_positive_page_bounds(client):
    """`page_from`/`page_to` are 1-based; a non-positive value is malformed
    input (422), not a legitimate request that happens to clamp to nothing or
    to match via negative-slice semantics."""
    assert client.get("/api/section/4.4", params={"page_from": 0}).status_code == 422
    assert client.get("/api/section/4.4", params={"page_from": -5, "page_to": 2}).status_code == 422
    assert client.get("/api/section/4.4", params={"page_to": 0}).status_code == 422


def test_page_image_returns_webp(client):
    r = client.get("/api/page/600/image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert len(r.content) > 1000


def test_page_image_out_of_range_404s(client):
    assert client.get("/api/page/99999/image").status_code == 404


def test_page_image_missing_pdf_path_returns_503(client, monkeypatch):
    """A missing/misconfigured PURSER_PDF_PATH is a container config error,
    not a client error and not a server bug -- 503, not an unhandled 500."""
    import purser_api.routers.manual as manual_mod

    def _raise():
        raise KeyError("PURSER_PDF_PATH")

    monkeypatch.setattr(manual_mod, "get_pdf_path", _raise)
    assert client.get("/api/page/600/image").status_code == 503


def test_page_image_render_failure_returns_503(client, monkeypatch):
    """A missing pdftoppm binary or a bad PDF at PURSER_PDF_PATH must also
    503, not surface as an unhandled 500 traceback."""
    import purser_api.routers.manual as manual_mod

    def _raise(pdf, pdf_page):
        raise OSError("pdftoppm: command not found")

    monkeypatch.setattr(manual_mod, "render_page", _raise)
    assert client.get("/api/page/600/image").status_code == 503


def test_threads_start_empty(client):
    assert client.get("/api/threads").json() == []


def test_chat_rejects_empty_message(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422


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


def test_chat_streams_answer_then_resolved_citations(client, monkeypatch):
    import purser_api.routers.chat as chat_mod

    answer = Answer(
        body="Evacuate via the nearest usable exit.",
        refs=[CiteRef(pdf_page=600, line_from=0, line_to=15)],
        not_in_manual=False,
    )
    monkeypatch.setattr(chat_mod, "get_agent", lambda: _FakeAgent(answer))
    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    resp = client.post("/api/chat", json={"message": "how do I evacuate?"})
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    assert [e["event"] for e in events] == ["thread", "delta", "citations", "done"]

    thread_id = json.loads(events[0]["data"])["thread_id"]
    assert json.loads(events[1]["data"])["text"] == answer.body

    citations = json.loads(events[2]["data"])
    assert len(citations) == 1
    # The citation carries verbatim manual text spliced by resolve(), never
    # anything the (fake) model wrote.
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


def test_chat_emits_tool_progress_events(client, monkeypatch):
    """`Answer` is structured output, so there is no token-level text to
    stream -- `FunctionToolCallEvent`s are the only progress signal before
    the final result. Kills the mutant that drops the `tool` event yield.
    """
    import purser_api.routers.chat as chat_mod

    answer = Answer(body="Evacuate now.", refs=[], not_in_manual=True)
    fake = _FakeAgent(answer, tool_calls=[("search", {"query": "evacuation"}), ("toc", {})])
    monkeypatch.setattr(chat_mod, "get_agent", lambda: fake)
    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    resp = client.post("/api/chat", json={"message": "how do I evacuate?"})
    events = _parse_sse(resp.text)
    assert [e["event"] for e in events] == ["thread", "tool", "tool", "delta", "citations", "done"]

    first_tool = json.loads(events[1]["data"])
    assert first_tool == {"name": "search", "args": {"query": "evacuation"}}
    second_tool = json.loads(events[2]["data"])
    assert second_tool == {"name": "toc", "args": {}}


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
            CiteRef(pdf_page=600, line_from=0, line_to=15),
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


def test_chat_citation_resolution_failure_emits_error_not_a_silent_truncation(client, monkeypatch):
    """Everything after the model call -- resolve_all, json encoding, the
    assistant-message write -- must be inside the same guard as the model
    call itself. Before this fix, a failure here truncated the stream after
    the last delta with no `error` and no `done`: HTTP 200, a
    complete-looking (uncited) answer, and no way for the client to tell
    that apart from a legitimate `not_in_manual` response.
    """
    import purser_api.routers.chat as chat_mod

    def _boom(corpus, refs):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(chat_mod, "resolve_all", _boom)
    answer = Answer(
        body="ok", refs=[CiteRef(pdf_page=600, line_from=0, line_to=2)], not_in_manual=False
    )
    monkeypatch.setattr(chat_mod, "get_agent", lambda: _FakeAgent(answer))
    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    resp = client.post("/api/chat", json={"message": "hi"})
    events = _parse_sse(resp.text)
    kinds = [e["event"] for e in events]
    assert kinds[-1] == "error"
    assert "citations" not in kinds
    assert "done" not in kinds
    assert "index unavailable" in json.loads(events[-1]["data"])["detail"]

    thread_id = json.loads(events[0]["data"])["thread_id"]
    hist = client.get(f"/api/threads/{thread_id}").json()
    assert [m["role"] for m in hist] == ["user"]


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

    threads = client.get("/api/threads").json()
    assert [t["id"] for t in threads] == [thread_id]
    hist = client.get(f"/api/threads/{thread_id}").json()
    assert [m["body"] for m in hist] == ["first", "ok", "second", "ok"]


def test_chat_includes_prior_turns_in_the_prompt(client, monkeypatch):
    """The fake must actually observe the prompt it's driven with -- a fake
    that ignores its argument entirely can't tell a working history window
    apart from one that silently drops all prior context. Kills the mutant
    that replaces `prior` with `""`.
    """
    import purser_api.routers.chat as chat_mod

    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    fake1 = _FakeAgent(Answer(body="first reply", refs=[], not_in_manual=True))
    monkeypatch.setattr(chat_mod, "get_agent", lambda: fake1)
    first = _parse_sse(client.post("/api/chat", json={"message": "first question"}).text)
    thread_id = json.loads(first[0]["data"])["thread_id"]

    fake2 = _FakeAgent(Answer(body="second reply", refs=[], not_in_manual=True))
    monkeypatch.setattr(chat_mod, "get_agent", lambda: fake2)
    client.post("/api/chat", json={"thread_id": thread_id, "message": "second question"})

    assert len(fake2.prompts) == 1
    prompt = fake2.prompts[0]
    assert "first question" in prompt
    assert "first reply" in prompt
    assert "second question" in prompt


def test_chat_history_window_reaches_far_enough_back(client, monkeypatch):
    """Three exchanges (6 messages) is comfortably inside the 12-message
    history window but would be entirely dropped if the window shrank to 1
    -- kills that mutant independent of `test_chat_includes_prior_turns...`,
    which alone wouldn't distinguish "prior is always empty" from "prior
    only sees the single most recent message".
    """
    import purser_api.routers.chat as chat_mod

    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    thread_id = None
    for i in range(3):
        fake = _FakeAgent(Answer(body=f"reply {i}", refs=[], not_in_manual=True))
        monkeypatch.setattr(chat_mod, "get_agent", lambda f=fake: f)
        payload = {"message": f"turn {i}"}
        if thread_id:
            payload["thread_id"] = thread_id
        events = _parse_sse(client.post("/api/chat", json=payload).text)
        thread_id = json.loads(events[0]["data"])["thread_id"]

    final_fake = _FakeAgent(Answer(body="final", refs=[], not_in_manual=True))
    monkeypatch.setattr(chat_mod, "get_agent", lambda: final_fake)
    client.post("/api/chat", json={"thread_id": thread_id, "message": "turn 3"})

    assert len(final_fake.prompts) == 1
    assert "turn 0" in final_fake.prompts[0]


def test_threads_are_listed_most_recently_updated_first(client, monkeypatch):
    import purser_api.routers.chat as chat_mod

    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())

    def _agent():
        return _FakeAgent(Answer(body="ok", refs=[], not_in_manual=True))

    monkeypatch.setattr(chat_mod, "get_agent", _agent)
    first = _parse_sse(client.post("/api/chat", json={"message": "alpha"}).text)
    first_id = json.loads(first[0]["data"])["thread_id"]

    monkeypatch.setattr(chat_mod, "get_agent", _agent)
    second = _parse_sse(client.post("/api/chat", json={"message": "beta"}).text)
    second_id = json.loads(second[0]["data"])["thread_id"]

    ids = [t["id"] for t in client.get("/api/threads").json()]
    assert ids == [second_id, first_id]

    # Continuing the OLDER thread must move it back to the front -- this is
    # what actually pins the `thread.updated_at` bump. The assertion above
    # alone would also pass on plain creation order with no bump at all.
    monkeypatch.setattr(chat_mod, "get_agent", _agent)
    client.post("/api/chat", json={"thread_id": first_id, "message": "alpha again"})

    ids = [t["id"] for t in client.get("/api/threads").json()]
    assert ids == [first_id, second_id]


def test_chat_works_against_a_real_pydantic_ai_agent(client, monkeypatch):
    """Ruling 41's contract test: drives a genuine `Agent[PurserDeps, Answer]`
    -- the real `build_agent`, registering the real five tools -- through the
    real `/api/chat` router. Only the model backend is swapped for
    pydantic_ai's offline `TestModel`, exactly the seam where `stream_text()`
    broke unconditionally for this agent's structured output. Every other
    chat test here replaces the agent object entirely with `_FakeAgent`,
    which is precisely the gap that let that regression through six green
    tests.

    `TestModel`'s default behaviour calls every registered tool once for
    real (against the real corpus), then emits `custom_output_args` as the
    final result -- its default output fails `Answer`'s
    `_claims_require_citations` validator (no refs), so a valid `Answer`
    payload must be supplied explicitly.
    """
    from pydantic_ai.models.test import TestModel

    import purser_agent.lookup as lookup_mod
    import purser_api.routers.chat as chat_mod
    from purser_api.deps import get_tools

    valid_answer_args = {
        "body": "Evacuate via the nearest usable exit.",
        "refs": [{"pdf_page": 600, "line_from": 12, "line_to": 15}],
        "not_in_manual": False,
    }
    test_model = TestModel(custom_output_args=valid_answer_args)
    monkeypatch.setattr(lookup_mod, "resolve_model", lambda: test_model)

    real_agent = build_agent(get_tools())
    monkeypatch.setattr(chat_mod, "get_agent", lambda: real_agent)
    monkeypatch.setattr(chat_mod, "get_deps", lambda: PurserDeps(tools=get_tools()))

    resp = client.post("/api/chat", json={"message": "how do I evacuate?"})
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    kinds = [e["event"] for e in events]
    assert kinds[0] == "thread"
    assert "tool" in kinds, "TestModel calls all five tools; the router must surface them"
    assert kinds[-2:] == ["citations", "done"]

    delta = next(e for e in events if e["event"] == "delta")
    assert json.loads(delta["data"])["text"] == valid_answer_args["body"]

    citations = json.loads(next(e for e in events if e["event"] == "citations")["data"])
    assert len(citations) == 1
    assert citations[0]["pdf_page"] == 600


def test_starting_a_new_chat_keeps_only_the_most_recent_chats(client, monkeypatch):
    """The history is capped (PURSER_MAX_THREADS, 100 by default): the least
    recently used chat goes when a new one would exceed it."""
    import purser_api.routers.chat as chat_mod
    from purser_agent.schemas import Answer

    monkeypatch.setenv("PURSER_MAX_THREADS", "2")
    answer = Answer(body="", refs=[], not_in_manual=True)
    monkeypatch.setattr(chat_mod, "get_agent", lambda: _FakeAgent(answer))
    monkeypatch.setattr(chat_mod, "get_deps", lambda: object())
    for q in ("first", "second", "third"):
        client.post("/api/chat", json={"message": q})
    titles = [t["title"] for t in client.get("/api/threads").json()]
    assert titles == ["third", "second"]
