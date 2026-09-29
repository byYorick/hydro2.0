"""Процесс automation-engine 1.0.0: один воркер AE4 и HTTP-поверхность."""

from __future__ import annotations

import asyncio

from ae4.runtime.app import serve


async def main() -> None:
    await serve()


if __name__ == "__main__":
    asyncio.run(main())
