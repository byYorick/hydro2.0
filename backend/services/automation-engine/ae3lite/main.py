"""Точка входа standalone-сервиса AE3-Lite."""

from __future__ import annotations

import asyncio

from common.logging_setup import install_exception_handlers, setup_standard_logging

from ae3lite.infrastructure.log_context import attach_ae3_log_context_filter
from ae3lite.runtime import serve


def _bootstrap_logging() -> None:
    setup_standard_logging("automation-engine")
    install_exception_handlers("automation-engine")
    attach_ae3_log_context_filter()


_bootstrap_logging()


async def main() -> None:
    await serve()


if __name__ == "__main__":
    asyncio.run(main())
