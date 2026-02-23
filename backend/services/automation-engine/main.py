"""Compatibility entrypoint delegating to AE2-Lite runtime."""

import asyncio

from ae2lite.main import main as run_main


if __name__ == "__main__":
    asyncio.run(run_main())
