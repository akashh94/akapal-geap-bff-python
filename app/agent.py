"""The agent-facing side: talk to the deployed Agent Engine over the SDK.

No REST plumbing and no event parser here -- `agentplatform.agent_engines.get`
returns a remote object with the engine's ADK operations registered
(`async_create_session`, `async_stream_query`, ...), and yields parsed dicts.
"""

from collections.abc import AsyncIterator
from typing import Any

import agentplatform
from agentplatform import agent_engines

from .config import ENGINE_LOCATION, ENGINE_PROJECT, ENGINE_RESOURCE
from .events import StreamDeltaPlanner

_remote: Any | None = None


class AgentSessionNotFoundError(Exception):
    """The stored session no longer exists on the agent (evicted / expired)."""


def _get_remote() -> Any:
    global _remote
    if _remote is None:
        agentplatform.init(project=ENGINE_PROJECT, location=ENGINE_LOCATION)
        _remote = agent_engines.get(ENGINE_RESOURCE)
    return _remote


def _looks_like_missing_session(exc: Exception) -> bool:
    message = str(exc).lower()
    return "session" in message and "not found" in message


async def create_agent_session(user_id: str) -> str:
    session = await _get_remote().async_create_session(user_id=user_id)
    session_id = session.get("id") if isinstance(session, dict) else None
    if not session_id:
        raise RuntimeError(f"Agent did not return a session id: {session!r}")
    return session_id


async def run_agent_stream(
    user_id: str, session_id: str, message: str
) -> AsyncIterator[str]:
    """Yield the reply as text deltas in the order the agent produces them.

    Raises `AgentSessionNotFoundError` if the session is gone -- typically
    before any delta is yielded, which is what lets the caller recreate and
    retry.
    """
    planner = StreamDeltaPlanner()
    try:
        # run_config is required for token-level streaming: without it ADK
        # defaults to StreamingMode.NONE and yields only the final event, so
        # there would be no partial chunks to forward.
        events = _get_remote().async_stream_query(
            user_id=user_id,
            session_id=session_id,
            message=message,
            run_config={"streaming_mode": "sse"},
        )
        async for event in events:
            for delta in planner.process(event):
                yield delta
    except Exception as exc:  # noqa: BLE001 - re-classified below
        if _looks_like_missing_session(exc):
            raise AgentSessionNotFoundError(str(exc)) from exc
        raise
