"""The two clients: ``Pantech`` (blocking) and ``AsyncPantech`` (asyncio)."""

from __future__ import annotations

from types import TracebackType
from typing import Mapping, Optional, Type, Union

import httpx

from ._base_client import DEFAULT_MAX_RETRIES, AsyncAPIClient, SyncAPIClient
from ._types import NOT_GIVEN, NotGiven, Timeout
from .resources._async import AsyncResources
from .resources._sync import Resources

__all__ = ["Pantech", "AsyncPantech"]


class Pantech(SyncAPIClient, Resources):
    """A client for the Pantech Dynamics public API.

    ``api_key`` defaults to ``$PANTECH_API_KEY`` and ``base_url`` to
    ``$PANTECH_API_URL``, else ``https://api.pantechdynamics.com/public/v1``.
    ``timeout`` (seconds, default 60, connect 10) bounds each attempt;
    ``max_retries`` (default 3) is how many times a failed attempt is retried.
    Use it as a context manager, or call ``close()``, to release connections.

        with Pantech() as client:
            for instance in client.instances.list_all():
                print(instance["name"])
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Union[Timeout, NotGiven] = NOT_GIVEN,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Optional[Mapping[str, str]] = None,
        user_agent: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            user_agent=user_agent,
            http_client=http_client,
        )
        self._init_resources(self)

    def __enter__(self) -> Pantech:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()


class AsyncPantech(AsyncAPIClient, AsyncResources):
    """The asyncio client. Same options as ``Pantech``; every method is awaited.

    async with AsyncPantech() as client:
        async for instance in client.instances.list_all():
            print(instance["name"])
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Union[Timeout, NotGiven] = NOT_GIVEN,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Optional[Mapping[str, str]] = None,
        user_agent: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            user_agent=user_agent,
            http_client=http_client,
        )
        self._init_resources(self)

    async def __aenter__(self) -> AsyncPantech:
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.close()
