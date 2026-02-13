"""Единая схема канонических типов узлов Hydro 2.0."""

from __future__ import annotations

from typing import Optional, Set


CANONICAL_NODE_TYPES: Set[str] = {
    "ph",
    "ec",
    "climate",
    "irrig",
    "light",
    "relay",
    "water_sensor",
    "recirculation",
    "unknown",
}


def normalize_node_type(value: Optional[str]) -> str:
    """Нормализует строку типа узла в каноничную форму."""
    normalized = str(value or "").strip().lower()
    if normalized in CANONICAL_NODE_TYPES:
        return normalized
    return "unknown"


def is_canonical_node_type(value: Optional[str]) -> bool:
    """Проверяет, что значение уже является каноническим типом узла."""
    normalized = str(value or "").strip().lower()
    return normalized in CANONICAL_NODE_TYPES
