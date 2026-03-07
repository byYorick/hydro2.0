"""Runtime entrypoints for AE3-Lite v2."""

from .config import Ae3RuntimeConfig
from .worker import Ae3RuntimeWorker


def build_ae3_runtime_bundle(*args, **kwargs):
    from .bootstrap import build_ae3_runtime_bundle as _build

    return _build(*args, **kwargs)


def create_app(*args, **kwargs):
    from .app import create_app as _create_app

    return _create_app(*args, **kwargs)


async def serve(*args, **kwargs):
    from .app import serve as _serve

    return await _serve(*args, **kwargs)


__all__ = [
    "Ae3RuntimeConfig",
    "Ae3RuntimeWorker",
    "build_ae3_runtime_bundle",
    "create_app",
    "serve",
]
