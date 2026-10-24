from __future__ import annotations

import httpx

from .conftest import Recorder, json_response


def pages(request: httpx.Request) -> httpx.Response:
    cursor = request.url.params.get("cursor")
    if cursor is None:
        return json_response(200, {"data": [{"id": "vm_1"}, {"id": "vm_2"}], "next_cursor": "c2"})
    if cursor == "c2":
        return json_response(200, {"data": [{"id": "vm_3"}], "next_cursor": "c3"})
    return json_response(200, {"data": [{"id": "vm_4"}], "next_cursor": None})


def test_list_all_follows_next_cursor(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(pages)
    client = make_client(rec)
    ids = [inst["id"] for inst in client.instances.list_all(q="web", limit=2)]
    assert ids == ["vm_1", "vm_2", "vm_3", "vm_4"]
    assert [r.url.params.get("cursor") for r in rec.requests] == [None, "c2", "c3"]
    assert all(r.url.params["q"] == "web" and r.url.params["limit"] == "2" for r in rec.requests)


def test_list_all_is_lazy(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(pages)
    it = make_client(rec).instances.list_all()
    assert rec.requests == []
    assert next(iter(it))["id"] == "vm_1"
    assert len(rec.requests) == 1


def test_list_all_stops_on_a_repeated_cursor(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"data": [{"id": "x"}], "next_cursor": "same"}))
    assert len(list(make_client(rec).volumes.list_all())) == 2
    assert len(rec.requests) == 2


def test_single_page_lists(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"data": [{"id": "sshk_1"}], "next_cursor": None}))
    client = make_client(rec)
    assert [k["id"] for k in client.ssh_keys.list_all()] == ["sshk_1"]
    assert client.ssh_keys.list()["next_cursor"] is None


def test_nested_list_all(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(pages)
    subnets = list(make_client(rec).networks.subnets.list_all("net_1"))
    assert len(subnets) == 4
    assert rec.requests[0].url.path == "/public/v1/networks/net_1/subnets"


async def test_async_list_all(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(pages)
    client = make_async_client(rec)
    ids = [inst["id"] async for inst in client.instances.list_all()]
    assert ids == ["vm_1", "vm_2", "vm_3", "vm_4"]
    await client.close()
