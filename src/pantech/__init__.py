"""The official Python SDK for the Pantech Dynamics public API.

    import pantech

    client = pantech.Pantech()  # reads PANTECH_API_KEY
    order = client.instances.create(
        name="web-1", plan_slug="starter", image_slug="ubuntu-24-04", ssh_key_id="sshk_…"
    )
    client.instances.wait_for_order(order["order_id"])

Docs: https://docs.pantechdynamics.com/sdks/python
"""

from . import types
from ._base_client import DEFAULT_BASE_URL, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT
from ._client import AsyncPantech, Pantech
from ._exceptions import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    CloudFailedError,
    ConflictError,
    FieldError,
    InternalServerError,
    NotFoundError,
    OperationFailedError,
    OrderFailedError,
    PantechError,
    PaymentRequiredError,
    PermissionDeniedError,
    RateLimitError,
    ValidationError,
    WaitTimeoutError,
    WebhookVerificationError,
)
from ._types import NOT_GIVEN, NotGiven
from ._version import __version__
from ._webhooks import SIGNATURE_HEADER, verify_webhook

__all__ = [
    "Pantech",
    "AsyncPantech",
    "verify_webhook",
    "SIGNATURE_HEADER",
    "types",
    "NOT_GIVEN",
    "NotGiven",
    "DEFAULT_BASE_URL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT",
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
    "CloudFailedError",
    "WebhookVerificationError",
    "FieldError",
    "__version__",
]
