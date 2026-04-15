"""AE3 canonical configuration: Pydantic schemas, loader, mode handling.

This package is the Python-side mirror of `schemas/*.v1.json` — the single
canonical source of truth for automation config shape. All AE3 handlers
should read from typed models produced by `loader.py`, not from raw dicts.

Phase 2 status: shadow-mode only. `resolve_two_tank_runtime()` remains the
primary path; the loader here runs in parallel for validation auditing via
Prometheus counter `ae3_shadow_config_validation_total`.
"""

from ae3lite.config.errors import (
    ConfigLoaderError,
    ConfigValidationError,
)
from ae3lite.config.loader import (
    load_recipe_phase,
    load_runtime_plan,
    load_zone_correction,
)

__all__ = [
    "ConfigLoaderError",
    "ConfigValidationError",
    "load_recipe_phase",
    "load_runtime_plan",
    "load_zone_correction",
]
