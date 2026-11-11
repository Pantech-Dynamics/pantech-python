"""Errors raised by the SDK.

Every error is a ``PantechError``. An error answer from the API is an
``APIError`` built from its ``application/problem+json`` body, with a
subclass per HTTP status; branch on ``err.code``, which is stable, rather
than on the message.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Literal, Mapping, Optional, TypedDict, get_args

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
    "PreconditionFailedError",
    "ValidationError",
    "RateLimitError",
    "InternalServerError",
    "APIConnectionError",
    "APITimeoutError",
    "WaitTimeoutError",
    "OperationFailedError",
    "OrderFailedError",
    "CloudFailedError",
    "DNSFailedError",
    "CertificateFailedError",
    "WebhookVerificationError",
    "FieldError",
    "DNSErrorCode",
    "DomainErrorCode",
    "RegistryErrorCode",
    "IamErrorCode",
    "CertificateErrorCode",
    "DNS_ERROR_CODES",
    "DOMAIN_ERROR_CODES",
    "REGISTRY_ERROR_CODES",
    "IAM_ERROR_CODES",
    "CERTIFICATE_ERROR_CODES",
]

# The problem ``code``s Pantech DNS answers with, besides the platform's usual
# ones (VALIDATION_FAILED, FORBIDDEN, NOT_FOUND, IDEMPOTENCY_CONFLICT,
# INSUFFICIENT_DELETE_SCOPE, RATE_LIMITED…). Compare ``err.code`` with these.
DNSErrorCode = Literal[
    "DNS_UNAVAILABLE",
    "DNS_ZONE_NOT_FOUND",
    "DNS_RECORD_NOT_FOUND",
    "DNS_ZONE_LIMIT_REACHED",
    "DNS_ZONE_CREATE_LIMIT_REACHED",
    "DNS_RECORD_LIMIT_REACHED",
    "DNS_ZONE_NAME_TAKEN",
    "DNS_ZONE_ACTIVE_ELSEWHERE",
    "DNS_RECORD_EXISTS",
    "DNS_CNAME_CONFLICT",
    "DNS_RECORD_READ_ONLY",
    "DNS_ZONE_SUSPENDED",
    "DNS_ZONE_NOT_WRITABLE",
    "DNS_ZONE_IN_USE_BY_DOMAIN",
    "VERSION_CONFLICT",
    "TOO_MANY_CHANGES",
    "INVALID_ZONE_FILE",
]

# The problem ``code``s of domain registration.
DomainErrorCode = Literal[
    "DOMAINS_UNAVAILABLE",
    "DOMAIN_NOT_FOUND",
    "DOMAIN_ORDER_NOT_FOUND",
    "DOMAIN_LOOKUP_UNAVAILABLE",
    "TLD_NOT_SOLD",
    "DOMAIN_NOT_AVAILABLE",
    "DOMAIN_NOT_TRANSFERABLE",
    "DOMAIN_ALREADY_HELD",
    "DOMAIN_ORDER_IN_FLIGHT",
    "DOMAIN_ORDER_NOT_AWAITING_PAYMENT",
    "DOMAIN_ORDER_LIMIT_REACHED",
    "DOMAIN_NOT_CONFIGURABLE",
    "DOMAIN_LOCKED",
    "DOMAIN_ZONE_MISMATCH",
]

# The problem ``code``s of the container registry.
RegistryErrorCode = Literal[
    "REGISTRY_UNAVAILABLE",
    "REGISTRY_NAMESPACE_NOT_SET",
    "REGISTRY_NAMESPACE_TAKEN",
    "REGISTRY_NAMESPACE_LOCKED",
    "INVALID_REGISTRY_NAMESPACE",
    "INVALID_REPOSITORY_NAME",
    "REPOSITORY_NOT_FOUND",
    "TAG_NOT_FOUND",
    "REGISTRY_TOKEN_NOT_FOUND",
    "REPOSITORY_EXISTS",
    "REPOSITORY_LIMIT_REACHED",
    "REGISTRY_STORAGE_LIMIT_REACHED",
    "REGISTRY_TOKEN_LIMIT_REACHED",
    "TAG_IMMUTABLE",
    "REPOSITORY_SUSPENDED",
]

# The problem ``code``s of teams and access policies.
IamErrorCode = Literal[
    "ACCESS_DENIED",
    "IAM_TEAM_NOT_FOUND",
    "IAM_POLICY_NOT_FOUND",
    "IAM_ATTACHMENT_NOT_FOUND",
    "IAM_TEAM_NAME_TAKEN",
    "IAM_POLICY_NAME_TAKEN",
    "IAM_TEAM_LIMIT_REACHED",
    "IAM_POLICY_LIMIT_REACHED",
    "IAM_ATTACHMENT_LIMIT_REACHED",
    "IAM_MANAGED_POLICY",
    "IAM_ADMIN_TARGET",
    "INVALID_POLICY",
    "VERSION_CONFLICT",
]

# The problem ``code``s of Certificate Manager.
CertificateErrorCode = Literal[
    "CERTIFICATES_UNAVAILABLE",
    "CERTIFICATE_NOT_FOUND",
    "CERTIFICATE_LIMIT_REACHED",
    "CERTIFICATE_REQUEST_LIMIT_REACHED",
    "CERTIFICATE_RATE_LIMITED",
    "CERTIFICATE_IN_USE",
    "CERTIFICATE_NOT_EXPORTABLE",
    "CERTIFICATE_NOT_ISSUED",
    "CERTIFICATE_NOT_REVOCABLE",
    "CERTIFICATE_NOT_IMPORTED",
    "CERTIFICATE_NOT_PENDING",
    "CERTIFICATE_NAMES_MISMATCH",
    "CONFLICT",
]

DNS_ERROR_CODES: FrozenSet[str] = frozenset(get_args(DNSErrorCode))
DOMAIN_ERROR_CODES: FrozenSet[str] = frozenset(get_args(DomainErrorCode))
REGISTRY_ERROR_CODES: FrozenSet[str] = frozenset(get_args(RegistryErrorCode))
IAM_ERROR_CODES: FrozenSet[str] = frozenset(get_args(IamErrorCode))
CERTIFICATE_ERROR_CODES: FrozenSet[str] = frozenset(get_args(CertificateErrorCode))


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
    """402: not enough credit for this order.

    ``domains.wait_for_order`` also raises it for an order ``awaiting_payment``
    (in US dollars the saved card is charged the difference; in naira the user
    adds credit): ``payment_url`` is the page where the bank asks the user to
    confirm the card payment, when it does (None otherwise), and
    ``payment_expires_at`` when the order fails ``insufficient_credit`` unless
    paid. ``order`` is the order as the API returned it. All three are None
    for a 402 answer.
    """

    payment_url: Optional[str] = None
    payment_expires_at: Optional[str] = None
    order: Optional[Mapping[str, Any]] = None

    @classmethod
    def for_order(cls, kind: str, order: Mapping[str, Any]) -> PaymentRequiredError:
        """The error for an order waiting for a payment (no URL in the message: it is a payment link)."""
        expires = order.get("payment_expires_at")
        confirm = "The bank asks the user to confirm the card payment at payment_url. "
        err = cls(
            status=402,
            code="AWAITING_PAYMENT",
            title="Payment required",
            detail=(
                f"{kind} order {order.get('id', '')} is waiting for a payment: your credit does not cover it. "
                + (confirm if order.get("payment_url") else "")
                + "It must be paid"
                + (f" before {expires}" if expires else " within the hour")
                + "; the order goes on by itself once it is, and orders.retry_payment tries again at once."
            ),
        )
        err.payment_url = order.get("payment_url")
        err.payment_expires_at = expires
        err.order = order
        return err


class PermissionDeniedError(APIError):
    """403: the key or its member may not do this (``INSUFFICIENT_SCOPE``, ``AI_APPS_DISABLED``…)."""


class NotFoundError(APIError):
    """404: nothing with this id, or no such route (check ``base_url``)."""


class ConflictError(APIError):
    """409: the resource is not in a state that allows this, or the name is taken."""


class PreconditionFailedError(APIError):
    """412: the resource changed since you read it (``VERSION_CONFLICT``). Read it again and retry."""


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
    """An instance, database or domain order ended in ``failed`` or ``payment_failed``.

    ``code`` is the order's ``failure_code``, e.g. ``insufficient_credit``.
    """

    def __init__(self, kind: str, order: Mapping[str, Any]) -> None:
        self.order = order
        self.status: str = str(order.get("status") or "")
        self.code: str = str(order.get("failure_code") or "")
        what = "payment failed" if self.status == "payment_failed" else "failed"
        msg = f"{kind} order {order.get('id', '')} {what}"
        if self.code:
            msg += f": {self.code}"
        super().__init__(msg)


class CloudFailedError(PantechError):
    """A cloud connection's check or a scan ended ``failed``. ``code`` is stable; ``message`` says what to do."""

    def __init__(self, kind: str, resource: Mapping[str, Any]) -> None:
        self.kind = kind
        self.resource = resource
        failure: Mapping[str, Any] = resource.get("failure") or {}
        self.code: str = str(failure.get("code") or "")
        self.message: str = str(failure.get("message") or "")
        msg = f"Cloud {kind} {resource.get('id', '')} failed"
        if self.code:
            msg += f": {self.code}"
        if self.message:
            msg += f": {self.message}"
        super().__init__(msg)


class DNSFailedError(PantechError):
    """A DNS zone or record set ended ``failed`` (or the zone is being deleted).

    ``kind`` is ``zone`` or ``record``; ``code`` is its ``failure_code``, e.g.
    ``invalid_change`` or ``delegation_timeout``. A failed record change leaves
    its last good values answering.
    """

    def __init__(self, kind: str, resource: Mapping[str, Any]) -> None:
        self.kind = kind
        self.resource = resource
        status = str(resource.get("status") or "")
        self.code: str = str(resource.get("failure_code") or ("" if status == "failed" else status))
        if kind == "record":
            what = f"DNS record {resource.get('id', '')} ({resource.get('fqdn', '')} {resource.get('type', '')})"
        else:
            what = f"DNS zone {resource.get('id', '')} ({resource.get('name', '')})"
        msg = f"{what} {'failed' if status == 'failed' else 'is ' + status}"
        if self.code:
            msg += f": {self.code}"
        super().__init__(msg)


class CertificateFailedError(PantechError):
    """A certificate the SDK waited for ended ``failed``, ``revoked`` or ``expired``.

    ``code`` is its ``failure_code`` (e.g. ``validation_timeout``, ``caa_forbidden``), or the
    status when it has none.
    """

    def __init__(self, certificate: Mapping[str, Any]) -> None:
        self.certificate = certificate
        status = str(certificate.get("status") or "")
        self.code: str = str(certificate.get("failure_code") or status)
        names = certificate.get("names") or []
        first = names[0] if names else ""
        msg = f"Certificate {certificate.get('id', '')} ({first}) {status or 'failed'}"
        if self.code and self.code != status:
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
    412: PreconditionFailedError,
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
