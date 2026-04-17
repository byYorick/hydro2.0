"""AE3 canonical configuration: Pydantic schemas, builders, loaders, mode handling.

This package is the Python-side mirror of `schemas/*.v1.json` — the single
canonical source of truth for automation config shape. All AE3 handlers
should read from typed models produced by `loader.py`, not from raw dicts.

The runtime payload builder and typed loaders live under `ae3lite.config`;
runtime code should consume the typed contract.
"""

from ae3lite.config.errors import (
    ConfigLoaderError,
    ConfigValidationError,
)
from ae3lite.config.loader import (
    load_runtime_plan,
    load_zone_correction,
)
from ae3lite.config.runtime_plan_builder import (
    default_two_tank_command_plan,
    resolve_two_tank_runtime,
    resolve_two_tank_runtime_plan,
)

__all__ = [
    "ConfigLoaderError",
    "ConfigValidationError",
    "default_two_tank_command_plan",
    "load_runtime_plan",
    "load_zone_correction",
    "resolve_two_tank_runtime",
    "resolve_two_tank_runtime_plan",
]
