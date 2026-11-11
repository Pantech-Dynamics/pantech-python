"""The official Python SDK for the Pantech Dynamics public API.

    import pantech

    client = pantech.Pantech()  # reads PANTECH_API_KEY
    order = client.instances.create(
        name="web-1", plan_slug="starter", image_slug="ubuntu-24-04", ssh_key_id="sshk_…"
    )
    client.instances.wait_for_order(order["order_id"])

Docs: https://docs.pantechdynamics.com/sdks/python
"""

from . import iam, types
from ._base_client import DEFAULT_BASE_URL, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT
from ._client import AsyncPantech, Pantech
from ._exceptions import (
    CERTIFICATE_ERROR_CODES,
    DNS_ERROR_CODES,
    DOMAIN_ERROR_CODES,
    IAM_ERROR_CODES,
    REGISTRY_ERROR_CODES,
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    CertificateErrorCode,
    CertificateFailedError,
    CloudFailedError,
    ConflictError,
    DNSErrorCode,
    DNSFailedError,
    DomainErrorCode,
    FieldError,
    IamErrorCode,
    InternalServerError,
    NotFoundError,
    OperationFailedError,
    OrderFailedError,
    PantechError,
    PaymentRequiredError,
    PermissionDeniedError,
    PreconditionFailedError,
    RateLimitError,
    RegistryErrorCode,
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
    "iam",
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
    "DNS_ERROR_CODES",
    "DOMAIN_ERROR_CODES",
    "RegistryErrorCode",
    "REGISTRY_ERROR_CODES",
    "IamErrorCode",
    "IAM_ERROR_CODES",
    "CertificateErrorCode",
    "CERTIFICATE_ERROR_CODES",
    "__version__",
]
