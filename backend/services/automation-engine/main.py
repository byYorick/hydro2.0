"""Service entrypoint delegating to standalone AE3-Lite runtime."""

import asyncio

from ae3lite.main import main


if __name__ == "__main__":
    asyncio.run(main())
