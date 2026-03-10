#!/usr/bin/env python3
from __future__ import annotations

import asyncio

from vito_tester import VITOTesterClient


async def main() -> None:
    client = VITOTesterClient()
    await client.start()
    me = await client._client.get_me()  # type: ignore[attr-defined]
    print(f"Авторизован как: {getattr(me, 'first_name', '')} (@{getattr(me, 'username', '')})")
    print(f"Твой chat_id: {getattr(me, 'id', '')}")
    print(f"Сессия сохранена в: {client.session_path}")
    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
