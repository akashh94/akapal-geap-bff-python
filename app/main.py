"""FastAPI app exposing the streaming chat contract:

    GET  /health

    POST /api/chat   Authorization: Bearer <portal session JWT>
                     { "message": str, "sessionId"?: str }
                  -> text/event-stream frames:
                     {"type": "meta",  "userId", "sessionId", "resumed"}
                     {"type": "delta", "text"}
                     {"type": "done",  "reply"}
                     {"type": "error", "error"}

Anything decided before the stream opens (401/400/403/502) is still returned as
a JSON body; once the stream is open, failures arrive as an `error` frame. Same
port, auth and create-or-resume rules as before.
"""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .agent import (
    AgentSessionNotFoundError,
    create_agent_session,
    run_agent_stream,
)
from .auth import require_user
from .config import ENGINE_ID
from .store import get_active_thread, owns_thread, save_thread

app = FastAPI(title="akapal-geap-bff")

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Disable buffering in front of the app (nginx-style reverse proxies).
    "X-Accel-Buffering": "no",
}


@app.exception_handler(HTTPException)
async def http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
    # Match the TS BFF's body shape ({"error": ...}) so the portal client,
    # which reads data.error, behaves identically.
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


class ChatRequest(BaseModel):
    message: str | None = None
    sessionId: str | None = None


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _yield_to_loop() -> None:
    # The Agent Engine SDK blocks the running event loop while it awaits each
    # streamed chunk, so uvicorn never gets a chance to flush the socket between
    # events -- without this, the whole reply arrives in one burst at the end.
    # Handing the loop a turn after every frame is what makes delivery actually
    # progressive.
    await asyncio.sleep(0)


async def _first_delta(stream: AsyncIterator[str]) -> str | None:
    """Pull the first text delta, or None if the turn produced no text.

    Raises `AgentSessionNotFoundError` if the session died before any output,
    which the caller uses to recreate and retry.
    """
    try:
        return await anext(stream)
    except StopAsyncIteration:
        return None


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "engine": ENGINE_ID}


@app.post("/api/chat")
async def chat(body: ChatRequest, user_id: str = Depends(require_user)):
    message = (body.message or "").strip()
    if not message:
        return JSONResponse(status_code=400, content={"error": "message is required"})

    # Resolve which agent thread this turn belongs to (ADK_SESSION_AND_BFF.md §3.3).
    thread_id: str | None = None
    resumed = False

    if body.sessionId:
        # Explicit thread requested: authorize before touching it.
        if not owns_thread(user_id, body.sessionId):
            return JSONResponse(status_code=403, content={"error": "Not your session"})
        thread_id = body.sessionId
        resumed = True
    else:
        thread_id = get_active_thread(user_id)
        resumed = thread_id is not None

    try:
        if thread_id is None:
            thread_id = await create_agent_session(user_id)
            save_thread(user_id, thread_id)

        stream = run_agent_stream(user_id, thread_id, message)
        try:
            first = await _first_delta(stream)
        except AgentSessionNotFoundError:
            # Stale/evicted session: recreate once, re-persist, retry.
            thread_id = await create_agent_session(user_id)
            save_thread(user_id, thread_id)
            resumed = False
            stream = run_agent_stream(user_id, thread_id, message)
            first = await _first_delta(stream)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc) or "Agent error"
        print(f"[bff] chat failed: {detail}")
        return JSONResponse(status_code=502, content={"error": detail})

    # Past this point the thread is resolved; the turn streams from here.
    assert thread_id is not None
    session_id = thread_id

    async def event_stream() -> AsyncIterator[str]:
        yield _sse(
            {
                "type": "meta",
                "userId": user_id,
                "sessionId": session_id,
                "resumed": resumed,
            }
        )
        await _yield_to_loop()
        chunks: list[str] = []
        try:
            if first is not None:
                chunks.append(first)
                yield _sse({"type": "delta", "text": first})
                await _yield_to_loop()
            async for delta in stream:
                chunks.append(delta)
                yield _sse({"type": "delta", "text": delta})
                await _yield_to_loop()
        except Exception as exc:  # noqa: BLE001
            print(f"[bff] stream failed: {exc}")
            yield _sse({"type": "error", "error": str(exc) or "Agent error"})
            return

        save_thread(user_id, session_id)
        yield _sse({"type": "done", "reply": "".join(chunks).strip()})

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )
