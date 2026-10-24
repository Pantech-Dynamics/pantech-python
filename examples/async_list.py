"""List instances and volumes concurrently with the asyncio client.

export PANTECH_API_KEY=PAN_...
python examples/async_list.py
"""

from __future__ import annotations

import asyncio

import pantech


async def main() -> None:
    async with pantech.AsyncPantech() as client:
        me, instances, volumes = await asyncio.gather(
            client.me.get(),
            collect(client.instances.list_all()),
            collect(client.volumes.list_all()),
        )
        print(f"Organization {me['organization_id']}")
        print(f"{len(instances)} instances:")
        for inst in instances:
            print(f"  {inst['id']}  {inst['name']:<24} {inst.get('observed_state', '')}")
        print(f"{len(volumes)} volumes:")
        for vol in volumes:
            print(f"  {vol['id']}  {vol['name']:<24} {vol.get('size_gb', '')} GB")


async def collect(items):  # type: ignore[no-untyped-def]
    return [item async for item in items]


if __name__ == "__main__":
    asyncio.run(main())
