from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic_ai import AgentRunResultEvent, FunctionToolCallEvent
from sqlmodel import select
from sse_starlette.sse import EventSourceResponse

from purser_api.citations import resolve_all
from purser_api.db import Message, Thread, session
from purser_api.deps import get_agent, get_deps, get_tools
from purser_api.schemas import ChatRequest, ThreadSummary

router = APIRouter(prefix="/api", tags=["chat"])
_HISTORY_TURNS = 12


@router.get("/threads", response_model=list[ThreadSummary])
def list_threads() -> list[ThreadSummary]:
    with session() as s:
        rows = s.exec(select(Thread).order_by(Thread.updated_at.desc())).all()
        return [
            ThreadSummary(id=t.id, title=t.title, updated_at=t.updated_at.isoformat()) for t in rows
        ]


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str) -> list[dict]:
    with session() as s:
        if s.get(Thread, thread_id) is None:
            raise HTTPException(status_code=404, detail="no such thread")
        rows = s.exec(
            select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at)
        ).all()
        return [
            {"role": m.role, "body": m.body, "citations": json.loads(m.citations_json)}
            for m in rows
        ]


def _load_history(thread_id: str) -> list[Message]:
    with session() as s:
        return list(
            s.exec(
                select(Message)
                .where(Message.thread_id == thread_id)
                .order_by(Message.created_at.desc())
                .limit(_HISTORY_TURNS)
            ).all()
        )[::-1]


@router.post("/chat")
async def chat(req: ChatRequest) -> EventSourceResponse:
    """Stream an answer, then emit its resolved citations.

    A `thread_id` the client supplies must already exist -- silently starting
    a fresh thread under a different id would strand the client's reference
    to it, and inserting a message against a nonexistent thread_id would trip
    the `Message.thread_id` foreign key and raise `IntegrityError` (a 500).
    Checking existence first turns that into an explicit 404 instead.
    """
    with session() as s:
        if req.thread_id:
            thread = s.get(Thread, req.thread_id)
            if thread is None:
                raise HTTPException(status_code=404, detail="no such thread")
        else:
            thread = Thread(title=req.message[:60])
            s.add(thread)
            s.commit()
            s.refresh(thread)
        thread_id = thread.id

        # `onupdate` only fires on an UPDATE statement against this row, and a
        # continuation turn otherwise never touches the Thread row at all --
        # so without this, a thread's position in `GET /threads` freezes at
        # its creation time forever, and a long-running conversation sinks
        # below every later throwaway thread instead of floating to the top.
        thread.updated_at = datetime.now(UTC)
        s.add(thread)
        s.add(Message(thread_id=thread_id, role="user", body=req.message))
        s.commit()

    history = _load_history(thread_id)
    prior = "\n".join(f"{m.role}: {m.body}" for m in history[:-1])
    prompt = (
        f"Earlier in this conversation:\n{prior}\n\nQuestion: {req.message}"
        if prior
        else req.message
    )

    async def events():
        yield {"event": "thread", "data": json.dumps({"thread_id": thread_id})}

        # Everything below can fail after the model has already answered --
        # citation resolution, JSON encoding, the assistant-message write --
        # and every one of those failures must still surface as an `error`
        # event, never a silently truncated 200 with no citations. A
        # `not_in_manual=True` / zero-citation answer is legitimate; a stream
        # that just stops is not, and the client cannot tell them apart
        # unless every failure path is guarded the same way.
        try:
            agent, deps = get_agent(), get_deps()
            output = None
            async with agent.run_stream_events(prompt, deps=deps) as stream:
                async for ev in stream:
                    if isinstance(ev, FunctionToolCallEvent):
                        # Structured output (`Answer`) has no text to stream
                        # token-by-token -- the model's only response is one
                        # tool-call payload, assembled complete. This is the
                        # only sub-answer progress signal available before
                        # the final result; it replaces a dead cursor.
                        yield {
                            "event": "tool",
                            "data": json.dumps(
                                {"name": ev.part.tool_name, "args": ev.part.args_as_dict()}
                            ),
                        }
                    elif isinstance(ev, AgentRunResultEvent):
                        output = ev.result.output

            if output is None:
                raise RuntimeError("agent run produced no result")

            # Kept as a `delta` event (singular, whole-body) so the PWA's
            # existing event contract is unchanged. Do not hand-roll partial
            # JSON parsing of the model's output-tool call to fake token
            # streaming here: `Answer` is validated as a whole document (see
            # `Answer._claims_require_citations`), and there is no safe,
            # supported way to stream a half-valid one.
            yield {"event": "delta", "data": json.dumps({"text": output.body})}

            citations = resolve_all(get_tools().corpus, output.refs)
            payload = [c.model_dump(mode="json") for c in citations]

            with session() as s:
                thread = s.get(Thread, thread_id)
                if thread is not None:
                    thread.updated_at = datetime.now(UTC)
                    s.add(thread)
                s.add(
                    Message(
                        thread_id=thread_id,
                        role="assistant",
                        body=output.body,
                        citations_json=json.dumps(payload),
                    )
                )
                s.commit()

            yield {"event": "citations", "data": json.dumps(payload)}
        except Exception as exc:  # noqa: BLE001 - surface any failure to the client
            yield {"event": "error", "data": json.dumps({"detail": str(exc)})}
            return

        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(events())
