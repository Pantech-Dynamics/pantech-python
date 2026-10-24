"""Verifying webhook deliveries.

Each delivery carries ``Pantech-Signature: t=<unix seconds>,v1=<hex>``: the
hex HMAC-SHA256 of ``"<t>.<raw body>"`` keyed with the webhook's secret
(``whsec_…``, used as is). For 24 hours after a rotation there are two
``v1`` values, one per secret; either may match.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import List, Optional, Union

from ._exceptions import WebhookVerificationError

__all__ = ["verify_webhook", "SIGNATURE_HEADER", "DEFAULT_TOLERANCE"]

SIGNATURE_HEADER = "Pantech-Signature"
DEFAULT_TOLERANCE = 300


def verify_webhook(
    secret: Union[str, bytes],
    header: Optional[str],
    body: Union[bytes, str],
    *,
    tolerance: Optional[float] = DEFAULT_TOLERANCE,
    now: Optional[float] = None,
) -> None:
    """Checks a delivery's ``Pantech-Signature`` header against its raw body.

    Pass the body exactly as received, before any JSON parsing. Raises
    ``WebhookVerificationError`` when the header is missing or malformed, the
    timestamp is more than *tolerance* seconds from now (``None`` skips that
    check), or no ``v1`` signature matches. Returns ``None`` when it verifies.
    """
    if not secret:
        raise WebhookVerificationError("No webhook secret given.")
    if not header:
        raise WebhookVerificationError(f"Missing {SIGNATURE_HEADER} header.")
    timestamp: Optional[str] = None
    signatures: List[bytes] = []
    for part in header.split(","):
        name, sep, value = part.strip().partition("=")
        if not sep:
            continue
        if name == "t":
            timestamp = value.strip()
        elif name == "v1":
            signatures.append(value.strip().encode("utf-8", "replace"))
    if timestamp is None or not timestamp.isdigit():
        raise WebhookVerificationError(f"{SIGNATURE_HEADER} has no valid timestamp.")
    if not signatures:
        raise WebhookVerificationError(f"{SIGNATURE_HEADER} has no v1 signature.")
    if tolerance is not None:
        current = time.time() if now is None else now
        if abs(current - int(timestamp)) > tolerance:
            raise WebhookVerificationError("The delivery's timestamp is outside the tolerance; it may be a replay.")

    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    raw = body.encode("utf-8") if isinstance(body, str) else body
    expected = (
        hmac.new(secret_bytes, timestamp.encode("ascii") + b"." + raw, hashlib.sha256).hexdigest().encode("ascii")
    )
    matched = False
    for candidate in signatures:
        # Compare every value, so timing does not reveal which one matched.
        matched |= hmac.compare_digest(expected, candidate)
    if not matched:
        raise WebhookVerificationError("No signature matches this body and secret.")
