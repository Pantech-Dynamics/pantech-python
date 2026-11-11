"""Base classes for resources, and the hand-written helpers the generated ones extend."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, Mapping, Optional, cast
from urllib.parse import quote

from ._exceptions import (
    CertificateFailedError,
    CloudFailedError,
    DNSFailedError,
    OperationFailedError,
    OrderFailedError,
    PaymentRequiredError,
    WaitTimeoutError,
)
from ._types import NotGiven

if TYPE_CHECKING:
    from ._base_client import AsyncAPIClient, SyncAPIClient
    from .types import (
        Certificate,
        CloudConnection,
        CloudScan,
        DatabaseOrder,
        DNSRecord,
        DNSZone,
        DomainOrder,
        InstanceOrder,
        Operation,
    )

__all__ = [
    "SyncResource",
    "AsyncResource",
    "OperationsWaiter",
    "AsyncOperationsWaiter",
    "InstanceOrderWaiter",
    "AsyncInstanceOrderWaiter",
    "DatabaseOrderWaiter",
    "AsyncDatabaseOrderWaiter",
    "CloudConnectionWaiter",
    "AsyncCloudConnectionWaiter",
    "CloudScanWaiter",
    "AsyncCloudScanWaiter",
    "DNSZoneWaiter",
    "AsyncDNSZoneWaiter",
    "DNSRecordWaiter",
    "AsyncDNSRecordWaiter",
    "DomainOrderWaiter",
    "CertificateWaiter",
    "AsyncCertificateWaiter",
    "AsyncDomainOrderWaiter",
]

OPERATION_DONE = frozenset({"succeeded", "failed"})
ORDER_DONE = frozenset({"provisioned", "failed", "payment_failed"})
ORDER_FAILED = frozenset({"failed", "payment_failed"})
CONNECTION_DONE = frozenset({"connected", "failed"})
SCAN_DONE = frozenset({"succeeded", "failed"})
RECORD_DONE = frozenset({"active", "failed"})
CERTIFICATE_READY = frozenset({"issued", "renewing"})
CERTIFICATE_DONE = CERTIFICATE_READY | {"failed", "revoked", "expired"}
ZONE_READY = frozenset({"awaiting_delegation", "active"})
ZONE_DONE = ZONE_READY | {"failed", "deleting", "deleted"}
DOMAIN_ORDER_DONE = frozenset({"succeeded", "failed"})
DOMAIN_ORDER_DONE_OR_UNPAID = DOMAIN_ORDER_DONE | {"awaiting_payment"}


def path_param(value: str) -> str:
    """Escapes one path segment, so an id can never change the route."""
    if not isinstance(value, str) or value == "":
        raise ValueError(f"expected a non-empty id string, got {value!r}")
    return quote(value, safe="")


class SyncResource:
    def __init__(self, client: SyncAPIClient) -> None:
        self._client = client


class AsyncResource:
    def __init__(self, client: AsyncAPIClient) -> None:
        self._client = client


def _check_wait_args(timeout: Optional[float], poll_interval: float) -> None:
    if poll_interval <= 0:
        raise ValueError("poll_interval must be positive")
    if timeout is not None and (timeout < 0 or math.isnan(timeout)):
        raise ValueError("timeout must be 0 or more, or None to wait forever")


def _timed_out(what: str, ident: str, status: str, timeout: Optional[float]) -> WaitTimeoutError:
    return WaitTimeoutError(
        f"{what} {ident} did not finish within {timeout:g}s; it is still {status or 'pending'}. "
        "It may still finish: wait again or check it later."
    )


class OperationsWaiter(SyncResource):
    def wait(
        self,
        operation_id: str,
        *,
        timeout: Optional[float] = 600.0,
        poll_interval: float = 2.0,
        raise_on_failure: bool = True,
    ) -> Operation:
        """Polls ``GET /operations/{id}`` until it ``succeeded`` or ``failed``.

        Raises ``OperationFailedError`` on failure (unless ``raise_on_failure``
        is false) and ``WaitTimeoutError`` after *timeout* seconds (``None``
        waits forever).
        """
        _check_wait_args(timeout, poll_interval)
        path = f"/operations/{path_param(operation_id)}"
        deadline = None if timeout is None else self._client._clock() + timeout
        while True:
            op = cast(Dict[str, Any], self._client.request("GET", path))
            status = str(op.get("status") or "")
            if status in OPERATION_DONE:
                if status == "failed" and raise_on_failure:
                    raise OperationFailedError(op)
                return cast("Operation", op)
            delay = poll_interval
            if deadline is not None:
                remaining = deadline - self._client._clock()
                if remaining <= 0:
                    raise _timed_out("Operation", operation_id, status, timeout)
                delay = min(delay, remaining)
            self._client._sleep(delay)


class AsyncOperationsWaiter(AsyncResource):
    async def wait(
        self,
        operation_id: str,
        *,
        timeout: Optional[float] = 600.0,
        poll_interval: float = 2.0,
        raise_on_failure: bool = True,
    ) -> Operation:
        """Polls ``GET /operations/{id}`` until it ``succeeded`` or ``failed``.

        Raises ``OperationFailedError`` on failure (unless ``raise_on_failure``
        is false) and ``WaitTimeoutError`` after *timeout* seconds (``None``
        waits forever).
        """
        _check_wait_args(timeout, poll_interval)
        path = f"/operations/{path_param(operation_id)}"
        deadline = None if timeout is None else self._client._clock() + timeout
        while True:
            op = cast(Dict[str, Any], await self._client.request("GET", path))
            status = str(op.get("status") or "")
            if status in OPERATION_DONE:
                if status == "failed" and raise_on_failure:
                    raise OperationFailedError(op)
                return cast("Operation", op)
            delay = poll_interval
            if deadline is not None:
                remaining = deadline - self._client._clock()
                if remaining <= 0:
                    raise _timed_out("Operation", operation_id, status, timeout)
                delay = min(delay, remaining)
            await self._client._sleep(delay)


def _wait_order_sync(
    resource: SyncResource, kind: str, base: str, order_id: str, timeout: Optional[float], poll_interval: float
) -> Dict[str, Any]:
    _check_wait_args(timeout, poll_interval)
    client = resource._client
    path = f"{base}/{path_param(order_id)}"
    deadline = None if timeout is None else client._clock() + timeout
    while True:
        order = cast(Dict[str, Any], client.request("GET", path))
        status = str(order.get("status") or "")
        if status in ORDER_DONE:
            if status in ORDER_FAILED:
                raise OrderFailedError(kind, order)
            return order
        delay = poll_interval
        if deadline is not None:
            remaining = deadline - client._clock()
            if remaining <= 0:
                raise _timed_out(f"{kind} order", order_id, status, timeout)
            delay = min(delay, remaining)
        client._sleep(delay)


async def _wait_order_async(
    resource: AsyncResource, kind: str, base: str, order_id: str, timeout: Optional[float], poll_interval: float
) -> Dict[str, Any]:
    _check_wait_args(timeout, poll_interval)
    client = resource._client
    path = f"{base}/{path_param(order_id)}"
    deadline = None if timeout is None else client._clock() + timeout
    while True:
        order = cast(Dict[str, Any], await client.request("GET", path))
        status = str(order.get("status") or "")
        if status in ORDER_DONE:
            if status in ORDER_FAILED:
                raise OrderFailedError(kind, order)
            return order
        delay = poll_interval
        if deadline is not None:
            remaining = deadline - client._clock()
            if remaining <= 0:
                raise _timed_out(f"{kind} order", order_id, status, timeout)
            delay = min(delay, remaining)
        await client._sleep(delay)


class InstanceOrderWaiter(SyncResource):
    def wait_for_order(
        self, order_id: str, *, timeout: Optional[float] = 900.0, poll_interval: float = 3.0
    ) -> InstanceOrder:
        """Polls ``GET /instance-orders/{id}`` until the order is ``provisioned``.

        Raises ``OrderFailedError`` on ``failed`` or ``payment_failed``, and
        ``WaitTimeoutError`` after *timeout* seconds.
        """
        order = _wait_order_sync(self, "Instance", "/instance-orders", order_id, timeout, poll_interval)
        return cast("InstanceOrder", order)


class AsyncInstanceOrderWaiter(AsyncResource):
    async def wait_for_order(
        self, order_id: str, *, timeout: Optional[float] = 900.0, poll_interval: float = 3.0
    ) -> InstanceOrder:
        """Polls ``GET /instance-orders/{id}`` until the order is ``provisioned``.

        Raises ``OrderFailedError`` on ``failed`` or ``payment_failed``, and
        ``WaitTimeoutError`` after *timeout* seconds.
        """
        order = await _wait_order_async(self, "Instance", "/instance-orders", order_id, timeout, poll_interval)
        return cast("InstanceOrder", order)


class DatabaseOrderWaiter(SyncResource):
    def wait_for_order(
        self, order_id: str, *, timeout: Optional[float] = 1800.0, poll_interval: float = 5.0
    ) -> DatabaseOrder:
        """Polls ``GET /database-orders/{id}`` until the order is ``provisioned``.

        Raises ``OrderFailedError`` on ``failed`` or ``payment_failed``, and
        ``WaitTimeoutError`` after *timeout* seconds.
        """
        order = _wait_order_sync(self, "Database", "/database-orders", order_id, timeout, poll_interval)
        return cast("DatabaseOrder", order)


class AsyncDatabaseOrderWaiter(AsyncResource):
    async def wait_for_order(
        self, order_id: str, *, timeout: Optional[float] = 1800.0, poll_interval: float = 5.0
    ) -> DatabaseOrder:
        """Polls ``GET /database-orders/{id}`` until the order is ``provisioned``.

        Raises ``OrderFailedError`` on ``failed`` or ``payment_failed``, and
        ``WaitTimeoutError`` after *timeout* seconds.
        """
        order = await _wait_order_async(self, "Database", "/database-orders", order_id, timeout, poll_interval)
        return cast("DatabaseOrder", order)


def _wait_cloud_sync(
    resource: SyncResource,
    kind: str,
    path: str,
    ident: str,
    done: FrozenSet[str],
    timeout: Optional[float],
    poll_interval: float,
) -> Dict[str, Any]:
    _check_wait_args(timeout, poll_interval)
    client = resource._client
    deadline = None if timeout is None else client._clock() + timeout
    while True:
        item = cast(Dict[str, Any], client.request("GET", path))
        status = str(item.get("status") or "")
        if status in done:
            if status == "failed":
                raise CloudFailedError(kind, item)
            return item
        delay = poll_interval
        if deadline is not None:
            remaining = deadline - client._clock()
            if remaining <= 0:
                raise _timed_out(f"Cloud {kind}", ident, status, timeout)
            delay = min(delay, remaining)
        client._sleep(delay)


async def _wait_cloud_async(
    resource: AsyncResource,
    kind: str,
    path: str,
    ident: str,
    done: FrozenSet[str],
    timeout: Optional[float],
    poll_interval: float,
) -> Dict[str, Any]:
    _check_wait_args(timeout, poll_interval)
    client = resource._client
    deadline = None if timeout is None else client._clock() + timeout
    while True:
        item = cast(Dict[str, Any], await client.request("GET", path))
        status = str(item.get("status") or "")
        if status in done:
            if status == "failed":
                raise CloudFailedError(kind, item)
            return item
        delay = poll_interval
        if deadline is not None:
            remaining = deadline - client._clock()
            if remaining <= 0:
                raise _timed_out(f"Cloud {kind}", ident, status, timeout)
            delay = min(delay, remaining)
        await client._sleep(delay)


class CloudConnectionWaiter(SyncResource):
    def wait(
        self, connection_id: str, *, timeout: Optional[float] = 600.0, poll_interval: float = 5.0
    ) -> CloudConnection:
        """Polls ``GET /cloud-connections/{id}`` until the connection is ``connected``.

        Set the role ARN with ``update`` first: a connection awaiting it is
        waited on too. Raises ``CloudFailedError`` when the check fails, and
        ``WaitTimeoutError`` after *timeout* seconds (``None`` waits forever).
        """
        path = f"/cloud-connections/{path_param(connection_id)}"
        conn = _wait_cloud_sync(self, "connection", path, connection_id, CONNECTION_DONE, timeout, poll_interval)
        return cast("CloudConnection", conn)


class AsyncCloudConnectionWaiter(AsyncResource):
    async def wait(
        self, connection_id: str, *, timeout: Optional[float] = 600.0, poll_interval: float = 5.0
    ) -> CloudConnection:
        """Polls ``GET /cloud-connections/{id}`` until the connection is ``connected``.

        Set the role ARN with ``update`` first: a connection awaiting it is
        waited on too. Raises ``CloudFailedError`` when the check fails, and
        ``WaitTimeoutError`` after *timeout* seconds (``None`` waits forever).
        """
        path = f"/cloud-connections/{path_param(connection_id)}"
        conn = await _wait_cloud_async(self, "connection", path, connection_id, CONNECTION_DONE, timeout, poll_interval)
        return cast("CloudConnection", conn)


class CloudScanWaiter(SyncResource):
    def wait(self, scan_id: str, *, timeout: Optional[float] = 1800.0, poll_interval: float = 10.0) -> CloudScan:
        """Polls ``GET /cloud-scans/{id}`` until the scan ``succeeded``.

        The result has no inventory: read it with ``get(scan_id, include="inventory")``.
        Raises ``CloudFailedError`` when the scan fails, and ``WaitTimeoutError``
        after *timeout* seconds (``None`` waits forever).
        """
        path = f"/cloud-scans/{path_param(scan_id)}"
        scan = _wait_cloud_sync(self, "scan", path, scan_id, SCAN_DONE, timeout, poll_interval)
        return cast("CloudScan", scan)


class AsyncCloudScanWaiter(AsyncResource):
    async def wait(self, scan_id: str, *, timeout: Optional[float] = 1800.0, poll_interval: float = 10.0) -> CloudScan:
        """Polls ``GET /cloud-scans/{id}`` until the scan ``succeeded``.

        The result has no inventory: read it with ``get(scan_id, include="inventory")``.
        Raises ``CloudFailedError`` when the scan fails, and ``WaitTimeoutError``
        after *timeout* seconds (``None`` waits forever).
        """
        path = f"/cloud-scans/{path_param(scan_id)}"
        scan = await _wait_cloud_async(self, "scan", path, scan_id, SCAN_DONE, timeout, poll_interval)
        return cast("CloudScan", scan)


def _wait_status_sync(
    resource: SyncResource,
    what: str,
    path: str,
    ident: str,
    done: FrozenSet[str],
    timeout: Optional[float],
    poll_interval: float,
) -> Dict[str, Any]:
    """Polls *path* until its ``status`` is in *done*; the caller decides what a failure means."""
    _check_wait_args(timeout, poll_interval)
    client = resource._client
    deadline = None if timeout is None else client._clock() + timeout
    while True:
        item = cast(Dict[str, Any], client.request("GET", path))
        status = str(item.get("status") or "")
        if status in done:
            return item
        delay = poll_interval
        if deadline is not None:
            remaining = deadline - client._clock()
            if remaining <= 0:
                raise _timed_out(what, ident, status, timeout)
            delay = min(delay, remaining)
        client._sleep(delay)


async def _wait_status_async(
    resource: AsyncResource,
    what: str,
    path: str,
    ident: str,
    done: FrozenSet[str],
    timeout: Optional[float],
    poll_interval: float,
) -> Dict[str, Any]:
    _check_wait_args(timeout, poll_interval)
    client = resource._client
    deadline = None if timeout is None else client._clock() + timeout
    while True:
        item = cast(Dict[str, Any], await client.request("GET", path))
        status = str(item.get("status") or "")
        if status in done:
            return item
        delay = poll_interval
        if deadline is not None:
            remaining = deadline - client._clock()
            if remaining <= 0:
                raise _timed_out(what, ident, status, timeout)
            delay = min(delay, remaining)
        await client._sleep(delay)


class DNSZoneWaiter(SyncResource):
    def wait(self, zone_id: str, *, timeout: Optional[float] = 300.0, poll_interval: float = 3.0) -> DNSZone:
        """Polls ``GET /dns/zones/{id}`` until the zone has its name servers.

        That is ``awaiting_delegation`` (set them at your registrar) or
        ``active``; delegation itself is up to your registrar. Raises
        ``DNSFailedError`` if the zone fails or is being deleted, and
        ``WaitTimeoutError`` after *timeout* seconds (``None`` waits forever).
        """
        path = f"/dns/zones/{path_param(zone_id)}"
        zone = _wait_status_sync(self, "DNS zone", path, zone_id, ZONE_DONE, timeout, poll_interval)
        if zone.get("status") not in ZONE_READY:
            raise DNSFailedError("zone", zone)
        return cast("DNSZone", zone)


class AsyncDNSZoneWaiter(AsyncResource):
    async def wait(self, zone_id: str, *, timeout: Optional[float] = 300.0, poll_interval: float = 3.0) -> DNSZone:
        """Polls ``GET /dns/zones/{id}`` until the zone has its name servers.

        That is ``awaiting_delegation`` (set them at your registrar) or
        ``active``; delegation itself is up to your registrar. Raises
        ``DNSFailedError`` if the zone fails or is being deleted, and
        ``WaitTimeoutError`` after *timeout* seconds (``None`` waits forever).
        """
        path = f"/dns/zones/{path_param(zone_id)}"
        zone = await _wait_status_async(self, "DNS zone", path, zone_id, ZONE_DONE, timeout, poll_interval)
        if zone.get("status") not in ZONE_READY:
            raise DNSFailedError("zone", zone)
        return cast("DNSZone", zone)


class CertificateWaiter(SyncResource):
    def wait(self, certificate_id: str, *, timeout: Optional[float] = 600.0, poll_interval: float = 5.0) -> Certificate:
        """Polls ``GET /certificates/{id}`` until the certificate is ``issued``.

        With Pantech DNS that is usually within two minutes. A name validated by
        CNAME waits until you add it (up to 72 hours): pass a longer *timeout*,
        or ``None``. Raises ``CertificateFailedError`` when it fails, is revoked
        or expires, and ``WaitTimeoutError`` after *timeout* seconds.
        """
        path = f"/certificates/{path_param(certificate_id)}"
        cert = _wait_status_sync(self, "Certificate", path, certificate_id, CERTIFICATE_DONE, timeout, poll_interval)
        if cert.get("status") not in CERTIFICATE_READY:
            raise CertificateFailedError(cert)
        return cast("Certificate", cert)


class AsyncCertificateWaiter(AsyncResource):
    async def wait(
        self, certificate_id: str, *, timeout: Optional[float] = 600.0, poll_interval: float = 5.0
    ) -> Certificate:
        """Polls ``GET /certificates/{id}`` until the certificate is ``issued``.

        With Pantech DNS that is usually within two minutes. A name validated by
        CNAME waits until you add it (up to 72 hours): pass a longer *timeout*,
        or ``None``. Raises ``CertificateFailedError`` when it fails, is revoked
        or expires, and ``WaitTimeoutError`` after *timeout* seconds.
        """
        path = f"/certificates/{path_param(certificate_id)}"
        cert = await _wait_status_async(
            self, "Certificate", path, certificate_id, CERTIFICATE_DONE, timeout, poll_interval
        )
        if cert.get("status") not in CERTIFICATE_READY:
            raise CertificateFailedError(cert)
        return cast("Certificate", cert)


def _record_path(zone_id: str, record_id: str) -> str:
    return f"/dns/zones/{path_param(zone_id)}/records/{path_param(record_id)}"


class DNSRecordWaiter(SyncResource):
    def wait(
        self, zone_id: str, record_id: str, *, timeout: Optional[float] = 300.0, poll_interval: float = 3.0
    ) -> DNSRecord:
        """Polls ``GET /dns/zones/{zone_id}/records/{record_id}`` until the record set is ``active``.

        A change is usually live within a minute. Raises ``DNSFailedError``
        when it fails (the record set keeps its last good values), and
        ``WaitTimeoutError`` after *timeout* seconds (``None`` waits forever).
        """
        path = _record_path(zone_id, record_id)
        record = _wait_status_sync(self, "DNS record", path, record_id, RECORD_DONE, timeout, poll_interval)
        if record.get("status") == "failed":
            raise DNSFailedError("record", record)
        return cast("DNSRecord", record)


class AsyncDNSRecordWaiter(AsyncResource):
    async def wait(
        self, zone_id: str, record_id: str, *, timeout: Optional[float] = 300.0, poll_interval: float = 3.0
    ) -> DNSRecord:
        """Polls ``GET /dns/zones/{zone_id}/records/{record_id}`` until the record set is ``active``.

        A change is usually live within a minute. Raises ``DNSFailedError``
        when it fails (the record set keeps its last good values), and
        ``WaitTimeoutError`` after *timeout* seconds (``None`` waits forever).
        """
        path = _record_path(zone_id, record_id)
        record = await _wait_status_async(self, "DNS record", path, record_id, RECORD_DONE, timeout, poll_interval)
        if record.get("status") == "failed":
            raise DNSFailedError("record", record)
        return cast("DNSRecord", record)


def _domain_order_result(order: Dict[str, Any]) -> DomainOrder:
    status = order.get("status")
    if status == "failed":
        raise OrderFailedError("Domain", order)
    if status == "awaiting_payment":
        raise PaymentRequiredError.for_order("Domain", order)
    return cast("DomainOrder", order)


class DomainOrderWaiter(SyncResource):
    def wait_for_order(
        self,
        order_id: str,
        *,
        timeout: Optional[float] = 900.0,
        poll_interval: float = 5.0,
        wait_for_payment: bool = False,
    ) -> DomainOrder:
        """Polls ``GET /domain-orders/{id}`` until the order ``succeeded``.

        An order your credit does not cover waits in ``awaiting_payment`` for an
        hour (in US dollars the saved card is charged the difference; in naira
        the user adds credit): this raises ``PaymentRequiredError`` with
        ``payment_expires_at``, and ``payment_url`` only when the bank asks the
        user to confirm the payment. Call again with ``wait_for_payment=True``
        to keep waiting, or ``orders.retry_payment(order_id)`` to try again at
        once; an order not paid in time fails ``insufficient_credit`` and
        nothing is charged.

        Raises ``OrderFailedError`` when it ``failed`` (its ``code`` is the
        order's ``failure_code``; any amount taken is returned to your credit),
        and ``WaitTimeoutError`` after *timeout* seconds. A transfer can take
        days: pass a longer *timeout*, or ``None``, or check the order later.
        """
        path = f"/domain-orders/{path_param(order_id)}"
        done = DOMAIN_ORDER_DONE if wait_for_payment else DOMAIN_ORDER_DONE_OR_UNPAID
        order = _wait_status_sync(self, "Domain order", path, order_id, done, timeout, poll_interval)
        return _domain_order_result(order)


class AsyncDomainOrderWaiter(AsyncResource):
    async def wait_for_order(
        self,
        order_id: str,
        *,
        timeout: Optional[float] = 900.0,
        poll_interval: float = 5.0,
        wait_for_payment: bool = False,
    ) -> DomainOrder:
        """Polls ``GET /domain-orders/{id}`` until the order ``succeeded``.

        An order your credit does not cover waits in ``awaiting_payment`` for an
        hour (in US dollars the saved card is charged the difference; in naira
        the user adds credit): this raises ``PaymentRequiredError`` with
        ``payment_expires_at``, and ``payment_url`` only when the bank asks the
        user to confirm the payment. Call again with ``wait_for_payment=True``
        to keep waiting, or ``orders.retry_payment(order_id)`` to try again at
        once; an order not paid in time fails ``insufficient_credit`` and
        nothing is charged.

        Raises ``OrderFailedError`` when it ``failed`` (its ``code`` is the
        order's ``failure_code``; any amount taken is returned to your credit),
        and ``WaitTimeoutError`` after *timeout* seconds. A transfer can take
        days: pass a longer *timeout*, or ``None``, or check the order later.
        """
        path = f"/domain-orders/{path_param(order_id)}"
        done = DOMAIN_ORDER_DONE if wait_for_payment else DOMAIN_ORDER_DONE_OR_UNPAID
        order = await _wait_status_async(self, "Domain order", path, order_id, done, timeout, poll_interval)
        return _domain_order_result(order)


# Response fields that are secrets: a new registry token's ``secret`` and an
# exported certificate's ``private_key_pem``.
SECRET_FIELDS = frozenset({"secret", "private_key_pem"})


class _SecretHiddenDict(Dict[str, Any]):
    """A response dict whose secret fields never appear in ``repr()``, ``str()`` or logs.

    ``value["secret"]`` reads one; ``json.dumps`` and ``dict(value)`` keep it,
    because writing it to your own secret store is the point.
    """

    def __repr__(self) -> str:
        return repr({k: ("<hidden>" if k in SECRET_FIELDS else v) for k, v in self.items()})

    __str__ = __repr__


def hide_secret(value: Any) -> Any:
    """Wraps a response that carries a secret (a new registry token, an exported private key)."""
    if isinstance(value, dict):
        return _SecretHiddenDict(value)
    return value


def merge_headers(values: Dict[str, Any], extra: Optional[Mapping[str, str]]) -> Optional[Dict[str, str]]:
    """Request headers from typed arguments (``if_match``), skipping NOT_GIVEN, plus ``extra_headers``."""
    out = {k: str(v) for k, v in values.items() if not isinstance(v, NotGiven) and v is not None}
    if extra:
        out.update(extra)
    return out or None


def merge_params(values: Dict[str, Any], extra: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Drops arguments left at NOT_GIVEN and adds the caller's ``extra_*`` values."""
    out = {k: v for k, v in values.items() if not isinstance(v, NotGiven)}
    if extra:
        out.update(extra)
    return out
