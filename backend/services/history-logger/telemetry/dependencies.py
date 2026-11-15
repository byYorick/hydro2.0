"""Task-local dependency snapshots for the telemetry facade.

Nested helpers inherit their caller's bindings. Resetting the context always
restores the caller; no handler module globals are rewritten across awaits.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

_overrides: ContextVar[Mapping[str, Any]] = ContextVar('telemetry_dependencies', default=MappingProxyType({}))


@dataclass(frozen=True)
class Dependencies:
    values: Mapping[str, Any]

    def __getattr__(self, name: str) -> Any:
        try:
            return self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def snapshot(namespace: Mapping[str, Any]) -> Dependencies:
    return Dependencies(MappingProxyType(dict(namespace) | dict(_overrides.get())))


@contextmanager
def bind_dependencies(**dependencies: Any):
    token = _overrides.set(MappingProxyType(dict(dependencies)))
    try:
        yield
    finally:
        _overrides.reset(token)
