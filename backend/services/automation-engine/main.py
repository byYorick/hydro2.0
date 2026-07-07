"""Service entrypoint delegating to standalone AE3-Lite runtime."""

import asyncio

# Инициализирует JSON-логи и log-context filter до импорта runtime.
import ae3lite.main  # noqa: F401

from ae3lite.main import main


if __name__ == "__main__":
    asyncio.run(main())
