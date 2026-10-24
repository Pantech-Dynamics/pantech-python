"""Server-Sent Events, for ``operations.stream``."""

from __future__ import annotations

import json
from typing import Any, List, Optional, TypedDict

__all__ = ["ServerSentEvent", "SSEDecoder"]


class ServerSentEvent(TypedDict):
    """One event: ``event`` is ``"operation"`` or ``"error"``; ``data`` is the parsed JSON."""

    event: str
    data: Any
    id: Optional[str]


class SSEDecoder:
    """Turns lines into events, per the HTML Server-Sent Events rules."""

    def __init__(self) -> None:
        self._event = ""
        self._data: List[str] = []
        self._id: Optional[str] = None

    def feed(self, line: str) -> Optional[ServerSentEvent]:
        line = line.rstrip("\r\n")
        if line == "":
            return self._dispatch()
        if line.startswith(":"):  # a comment, such as ": keepalive"
            return None
        name, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if name == "event":
            self._event = value
        elif name == "data":
            self._data.append(value)
        elif name == "id":
            self._id = value
        return None

    def _dispatch(self) -> Optional[ServerSentEvent]:
        if not self._data and not self._event:
            return None
        raw = "\n".join(self._data)
        data: Any
        try:
            data = json.loads(raw) if raw else None
        except ValueError:
            data = raw
        event = ServerSentEvent(event=self._event or "message", data=data, id=self._id)
        self._event, self._data = "", []
        return event
