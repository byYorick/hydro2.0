"""Request-local command dependencies; never mutate another module's globals.

Legacy ingress exports remain injectable, but concurrent requests keep their own
snapshot. Background recovery uses the default service dependencies.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from types import MappingProxyType
from typing import Callable, Mapping

_overrides: ContextVar[Mapping[str, Callable]] = ContextVar('command_dependencies', default=MappingProxyType({}))


@contextmanager
def bind_dependencies(**dependencies: Callable):
    token = _overrides.set(MappingProxyType(dict(_overrides.get()) | dict(dependencies)))
    try:
        yield
    finally:
        _overrides.reset(token)


def async_dependency(name: str, default: Callable) -> Callable:
    @wraps(default)
    async def invoke(*args, **kwargs):
        return await _overrides.get().get(name, default)(*args, **kwargs)

    return invoke


def sync_dependency(name: str, default: Callable) -> Callable:
    @wraps(default)
    def invoke(*args, **kwargs):
        return _overrides.get().get(name, default)(*args, **kwargs)

    return invoke
