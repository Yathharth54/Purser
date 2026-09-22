from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
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

        agent, deps = get_agent(), get_deps()
        try:
            async with agent.run_stream(prompt, deps=deps) as stream:
                async for chunk in stream.stream_text(delta=True):
                    yield {"event": "delta", "data": json.dumps({"text": chunk})}
                output = await stream.get_output()
        except Exception as exc:  # noqa: BLE001 - surface failure to the client
            yield {"event": "error", "data": json.dumps({"detail": str(exc)})}
            return

        citations = resolve_all(get_tools().corpus, output.refs)
        payload = [c.model_dump(mode="json") for c in citations]

        with session() as s:
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
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(events())
