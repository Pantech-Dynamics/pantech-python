"""TypedDicts for every request and response, generated from the API spec.

They are plain dicts at runtime: ``instance["name"]``.
"""

from .._streaming import ServerSentEvent
from ._generated import *  # noqa: F403
from ._generated import __all__ as _generated_all

__all__ = ["ServerSentEvent", *_generated_all]
