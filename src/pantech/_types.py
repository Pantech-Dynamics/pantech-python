"""Small shared types: the NOT_GIVEN sentinel and request option aliases."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Union

import httpx

__all__ = ["NOT_GIVEN", "NotGiven", "Headers", "Query", "Body", "Timeout"]


class NotGiven:
    """The default of every optional argument: leave the field out of the request.

    ``None`` is a real value (it sends JSON ``null``), so it cannot mean "not given".
    """

    _instance: Optional[NotGiven] = None

    def __new__(cls) -> NotGiven:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN = NotGiven()

Headers = Mapping[str, str]
Query = Mapping[str, Any]
Body = Mapping[str, Any]
# A number of seconds, an httpx.Timeout, or None for no timeout.
Timeout = Union[float, httpx.Timeout, None]
