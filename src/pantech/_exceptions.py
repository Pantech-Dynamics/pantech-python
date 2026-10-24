"""Errors raised by the SDK.

Every error is a ``PantechError``. An error answer from the API is an
``APIError`` built from its ``application/problem+json`` body, with a
subclass per HTTP status; branch on ``err.code``, which is stable, rather
than on the message.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, TypedDict

import httpx

__all__ = [
    "PantechError",
    "APIError",
    "BadRequestError",
    "AuthenticationError",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "ValidationError",
    "RateLimitError",
    "InternalServerError",
    "APIConnectionError",
    "APITimeoutError",
    "WaitTimeoutError",
    "OperationFailedError",
    "OrderFailedError",
    "WebhookVerificationError",
    "FieldError",
]


class FieldError(TypedDict):
    """One invalid field of a ``422 VALIDATION_FAILED``."""

    field: str
    code: str
    message: str


class PantechError(Exception):
    """The base of every error the SDK raises."""


class APIError(PantechError):
    """The API answered with an error.

    Attributes mirror the problem document: ``status``, ``code`` (stable, for
    branching), ``title``, ``detail`` (plain language, safe to show),
    ``request_id`` (quote it to support) and ``errors`` (field errors on 422).
    """

    status: int
    code: str
    title: str
    detail: str
    request_id: Optional[str]
    errors: List[FieldError]
    type: Optional[str]
    headers: httpx.Headers
    body: Any

    def __init__(
        self,
        *,
        status: int,
        code: str = "",
        title: str = "",
        detail: str = "",
        request_id: Optional[str] = None,
        errors: Optional[List[FieldError]] = None,
        type: Optional[str] = None,
        headers: Optional[httpx.Headers] = None,
        body: Any = None,
    ) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.request_id = request_id
        self.errors = errors or []
        self.type = type
        self.headers = headers if headers is not None else httpx.Headers()
        self.body = body
        super().__init__(self._message())

    @property
    def status_code(self) -> int:
        """The HTTP status, under the name httpx uses."""
        return self.status

    def _message(self) -> str:
        text = self.detail if self.detail and not self._detail_repeats_fields() else self.title
        msg = f"{self.status}"
        if self.code:
            msg += f" {self.code}"
        if text:
            msg += f": {text}"
        for fe in self.errors:
            name = fe.get("field") or ""
            msg += f"; {name + ': ' if name else ''}{fe.get('message', '')} ({fe.get('code', '')})"
        if self.request_id:
            msg += f" (request_id: {self.request_id})"
        # The API serves no such path: usually a base_url without /public/v1.
        if self.status == 404 and self.code.endswith("NO_ROUTE"):
            msg += ". Check base_url: it must end in /public/v1, for example https://api.pantechdynamics.com/public/v1"
        return msg

    def _detail_repeats_fields(self) -> bool:
        # A 422's detail is built from its field errors, which are listed anyway.
        if not self.errors:
            return False
        parts = []
        for fe in self.errors:
            message = (fe.get("message") or "").strip().rstrip(".")
            parts.append(f"{fe['field']}: {message}" if fe.get("field") else message)
        return self.detail in ("One or more fields are invalid.", "; ".join(parts) + ".")


class BadRequestError(APIError):
    """400: the request was malformed, for example a bad filter value."""


class AuthenticationError(APIError):
    """401: the API key is missing, wrong, revoked or expired."""


class PaymentRequiredError(APIError):
    """402: not enough credit for this order."""


class PermissionDeniedError(APIError):
    """403: the key or its member may not do this (``INSUFFICIENT_SCOPE``, ``AI_APPS_DISABLED``…)."""


class NotFoundError(APIError):
    """404: nothing with this id, or no such route (check ``base_url``)."""


class ConflictError(APIError):
    """409: the resource is not in a state that allows this, or the name is taken."""


class ValidationError(APIError):
    """422: one or more fields are invalid; see ``errors``."""


class RateLimitError(APIError):
    """429: too many requests. ``retry_after`` is the wait the API asked for, in seconds."""

    @property
    def retry_after(self) -> Optional[float]:
        return parse_retry_after(self.headers.get("retry-after"))


class InternalServerError(APIError):
    """5xx: something failed on the API's side. Retrying with the same Idempotency-Key is safe."""


class APIConnectionError(PantechError):
    """The request did not get an answer: DNS, TLS, a dropped connection."""

    def __init__(self, message: str = "Could not connect to the Pantech API.") -> None:
        super().__init__(message)


class APITimeoutError(APIConnectionError):
    """The request timed out."""

    def __init__(self, message: str = "The request to the Pantech API timed out.") -> None:
        super().__init__(message)


class WaitTimeoutError(PantechError, TimeoutError):
    """A wait helper gave up before the operation or order finished. It may still finish."""


class OperationFailedError(PantechError):
    """An operation finished with ``status: failed``. ``code`` and ``reason`` are safe to show."""

    def __init__(self, operation: Mapping[str, Any]) -> None:
        self.operation = operation
        failure: Mapping[str, Any] = operation.get("failure") or {}
        self.code: str = str(failure.get("code") or "")
        self.reason: str = str(failure.get("reason") or "")
        msg = f"Operation {operation.get('id', '')} failed"
        if self.code:
            msg += f": {self.code}"
        if self.reason:
            msg += f": {self.reason}"
        super().__init__(msg)


class OrderFailedError(PantechError):
    """An instance or database order ended in ``failed`` or ``payment_failed``."""

    def __init__(self, kind: str, order: Mapping[str, Any]) -> None:
        self.order = order
        self.status: str = str(order.get("status") or "")
        self.code: str = str(order.get("failure_code") or "")
        what = "payment failed" if self.status == "payment_failed" else "failed"
        msg = f"{kind} order {order.get('id', '')} {what}"
        if self.code:
            msg += f": {self.code}"
        super().__init__(msg)


class WebhookVerificationError(PantechError):
    """A webhook delivery's ``Pantech-Signature`` did not verify. Reject the request."""


_STATUS_ERRORS: Dict[int, type] = {
    400: BadRequestError,
    401: AuthenticationError,
    402: PaymentRequiredError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
    429: RateLimitError,
}


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    """The delay-seconds form of Retry-After; the HTTP-date form is ignored."""
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def make_api_error(response: httpx.Response) -> APIError:
    """Builds the right APIError subclass from an error response."""
    status = response.status_code
    body: Any = None
    try:
        body = response.json()
    except ValueError:
        body = response.text or None
    doc: Mapping[str, Any] = body if isinstance(body, dict) else {}
    errors: List[FieldError] = []
    for fe in doc.get("errors") or []:
        if isinstance(fe, dict):
            errors.append(
                FieldError(
                    field=str(fe.get("field") or ""),
                    code=str(fe.get("code") or ""),
                    message=str(fe.get("message") or ""),
                )
            )
    cls = _STATUS_ERRORS.get(status) or (InternalServerError if status >= 500 else APIError)
    err: APIError = cls(
        status=status,
        code=str(doc.get("code") or ""),
        title=str(doc.get("title") or response.reason_phrase or ""),
        detail=str(doc.get("detail") or ""),
        request_id=doc.get("request_id") or response.headers.get("x-request-id"),
        errors=errors,
        type=doc.get("type"),
        headers=response.headers,
        body=body,
    )
    return err
