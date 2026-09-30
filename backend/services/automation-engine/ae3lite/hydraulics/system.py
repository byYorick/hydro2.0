"""Контракт одной гидравлической системы внутри общего исполнителя."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class HydraulicSystem:
    """Что система наблюдает, чем командует и какие стадии графа ей принадлежат.

    ``borrows`` — привод чужой системы, который нужен только на время шага
    (импульс разбавления). Владелец привода остаётся у своей системы.
    ``handlers`` — ключи ``StageDef.handler``, которые имеет право исполнять
    только этот модуль. Общий ``command`` остаётся у исполнителя.
    ``handler_deps`` — какие зависимости роутер передаёт в конструктор handler-а.
    ``kind``: ``flow`` (длинный граф зоны), ``hosted`` (вложенная машина),
    ``tick`` (короткий прогон). ``scope``: ``zone`` или ``greenhouse``.
    """

    system_id: str
    watches: tuple[str, ...]
    controls: tuple[str, ...]
    stages: frozenset[str]
    handlers: Mapping[str, type]
    borrows: tuple[str, ...] = ()
    hosted_by_stages: frozenset[str] = field(default_factory=frozenset)
    kind: str = "flow"
    scope: str = "zone"
    required_node_types: frozenset[str] = field(default_factory=frozenset)
    handler_deps: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
