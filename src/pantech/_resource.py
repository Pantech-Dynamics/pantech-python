"""Base classes for resources, and the hand-written helpers the generated ones extend."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, Mapping, Optional, cast
from urllib.parse import quote

from ._exceptions import CloudFailedError, OperationFailedError, OrderFailedError, WaitTimeoutError
from ._types import NotGiven

if TYPE_CHECKING:
    from ._base_client import AsyncAPIClient, SyncAPIClient
    from .types import CloudConnection, CloudScan, DatabaseOrder, InstanceOrder, Operation

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
]

OPERATION_DONE = frozenset({"succeeded", "failed"})
ORDER_DONE = frozenset({"provisioned", "failed", "payment_failed"})
ORDER_FAILED = frozenset({"failed", "payment_failed"})
CONNECTION_DONE = frozenset({"connected", "failed"})
SCAN_DONE = frozenset({"succeeded", "failed"})


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


def merge_params(values: Dict[str, Any], extra: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Drops arguments left at NOT_GIVEN and adds the caller's ``extra_*`` values."""
    out = {k: v for k, v in values.items() if not isinstance(v, NotGiven)}
    if extra:
        out.update(extra)
    return out
