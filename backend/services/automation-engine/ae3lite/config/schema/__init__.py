"""Pydantic schemas mirroring `schemas/*.v1.json`.

Each module here corresponds to one JSON Schema file in repo-root `schemas/`.
Constraints (min/max/required/enum) must stay in sync with the JSON Schema
— Phase 7 adds CI check that regenerates AUTHORITY.md from JSON Schema to
catch drift.
"""

from ae3lite.config.schema.recipe_phase import RecipePhase
from ae3lite.config.schema.runtime_plan import RuntimePlan
from ae3lite.config.schema.zone_correction import ZoneCorrection

__all__ = ["RecipePhase", "RuntimePlan", "ZoneCorrection"]
