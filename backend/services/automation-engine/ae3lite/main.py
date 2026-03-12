"""Standalone AE3-Lite service entrypoint."""

from __future__ import annotations

import asyncio

from ae3lite.runtime import serve


async def main() -> None:
    await serve()


if __name__ == "__main__":
    asyncio.run(main())
