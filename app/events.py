"""Turning the agent's event stream into reply text.

The Agent Engine SDK yields events as dicts shaped like:

    {"author": "user"|"<agent>", "partial": bool,
     "content": {"role": ..., "parts": [{"text": "..."} ]}}

`StreamDeltaPlanner` decides which text to forward as each event arrives, so the
client can render progressively instead of waiting for the whole (potentially
long, multi-agent) turn. It mirrors the reference planner in
``akapal-geap-ui/server.js``:

* partial events are incremental streaming chunks -- always forwarded;
* the final, non-partial event for a turn repeats the full settled text, so it
  is forwarded only when nothing has been streamed yet for that author (this
  covers turns that never streamed partials, so no text is silently dropped);
* a blank line is inserted between consecutive turns from different authors,
  matching how the assembled reply joins segments.
"""

from typing import Any


class StreamDeltaPlanner:
    """Stateful mapper from agent events to text deltas."""

    def __init__(self) -> None:
        self._author: str | None = None
        self._sent_any = False

    def process(self, event: Any) -> list[str]:
        deltas: list[str] = []
        if not isinstance(event, dict) or event.get("author") == "user":
            return deltas

        author = event.get("author")
        if author != self._author:
            if self._author is not None and self._sent_any:
                deltas.append("\n\n")
            self._author = author
            self._sent_any = False

        parts = (event.get("content") or {}).get("parts") or []
        text = "".join(
            part.get("text") or ""
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
        if not text:
            return deltas

        if event.get("partial") or not self._sent_any:
            deltas.append(text)
            self._sent_any = True
        return deltas
