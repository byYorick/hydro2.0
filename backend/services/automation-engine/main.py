"""Процесс automation-engine: воркеры AE3 и AE4 в одном цикле.

Оба воркера поднимаются всегда. Отдельной переменной, которая гасит один из них, нет.
"""

from __future__ import annotations

import asyncio

# Инициализирует JSON-логи и log-context filter до импорта runtime.
import ae3lite.main  # noqa: F401

from ae3lite.runtime.app import serve
from ae4.runtime.env import Ae4RuntimeConfig
from ae4.runtime.worker import Ae4RuntimeWorker


async def main() -> None:
    ae4_worker = Ae4RuntimeWorker(config=Ae4RuntimeConfig.from_env())
    ae4_task = asyncio.create_task(ae4_worker.run(), name="ae4-runtime-worker")
    try:
        await serve()
    finally:
        await ae4_worker.shutdown()
        await ae4_task


if __name__ == "__main__":
    asyncio.run(main())
