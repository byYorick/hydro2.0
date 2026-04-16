"""Canonical config loader for AE3.

Public entry points:

- `load_zone_correction(payload, zone_id=None, namespace='zone.correction')`
  Validates a `zone.correction` base-config payload against the Pydantic
  schema (mirrors `schemas/zone_correction.v1.json`). Returns immutable
  `ZoneCorrection` model. Raises `ConfigValidationError` on failure with
  structured Pydantic errors.

Payload building and typed loading both live under `ae3lite.config`;
runtime code should consume the typed model directly.
"""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from ae3lite.config.errors import ConfigValidationError
from ae3lite.config.schema.recipe_phase import RecipePhase
from ae3lite.config.schema.runtime_plan import RuntimePlan
from ae3lite.config.schema.zone_correction import ZoneCorrection


def load_zone_correction(
    payload: Mapping[str, Any],
    *,
    zone_id: int | None = None,
    namespace: str = "zone.correction",
) -> ZoneCorrection:
    """Validate and parse a `zone.correction` base-config payload.

    `payload` corresponds to one of:
      - `automation_config_documents.payload.base_config` (Laravel side),
      - `snapshot.correction_config.base` (AE3 side, after compiler merge),
      - `snapshot.correction_config.phases.<phase>` (AE3 side, post-merge).

    Phase 2 deliberately does NOT unwrap the document wrapper
    `{preset_id, base_config, phase_overrides, resolved_config}` — that is
    the Laravel validator's job (see `JsonSchemaValidator`). Here we validate
    only the merged runtime-facing shape AE3 actually consumes.
    """
    if not isinstance(payload, Mapping):
        raise ConfigValidationError(
            zone_id=zone_id,
            namespace=namespace,
            errors=[{"loc": (), "type": "type_error",
                     "msg": f"payload must be a mapping, got {type(payload).__name__}"}],
        )

    try:
        return ZoneCorrection.model_validate(dict(payload))
    except ValidationError as exc:
        raise ConfigValidationError(
            zone_id=zone_id,
            namespace=namespace,
            errors=[_clean_error(e) for e in exc.errors(include_url=False)],
        ) from exc


def load_recipe_phase(
    payload: Mapping[str, Any],
    *,
    zone_id: int | None = None,
    cycle_id: int | None = None,
    namespace: str = "recipe.phase",
) -> RecipePhase:
    """Validate and parse a recipe phase runtime payload.

    `payload` corresponds to the merged shape of `grow_cycles.currentPhase`
    + zone target overrides that AE3 reads as `snapshot.phase_targets`,
    `snapshot.targets`, and `snapshot.diagnostics_execution`.

    Used by live-mode hot-reload of recipe phase and by config parity tests.

    `cycle_id` is included in the error context but not (yet) stored on
    `ConfigValidationError` — refine when Phase 5 wires the call site.
    """
    if not isinstance(payload, Mapping):
        raise ConfigValidationError(
            zone_id=zone_id,
            namespace=namespace,
            errors=[{"loc": (), "type": "type_error",
                     "msg": f"payload must be a mapping, got {type(payload).__name__}"}],
        )

    try:
        return RecipePhase.model_validate(dict(payload))
    except ValidationError as exc:
        raise ConfigValidationError(
            zone_id=zone_id,
            namespace=namespace,
            errors=[_clean_error(e) for e in exc.errors(include_url=False)],
        ) from exc


def load_runtime_plan(
    payload: Mapping[str, Any],
    *,
    zone_id: int | None = None,
    namespace: str = "runtime.plan",
) -> RuntimePlan:
    """Validate and parse the full `plan.runtime` dict produced by the
    AE3 runtime payload builder."""
    if not isinstance(payload, Mapping):
        raise ConfigValidationError(
            zone_id=zone_id,
            namespace=namespace,
            errors=[{"loc": (), "type": "type_error",
                     "msg": f"payload must be a mapping, got {type(payload).__name__}"}],
        )

    try:
        return RuntimePlan.model_validate(dict(payload))
    except ValidationError as exc:
        raise ConfigValidationError(
            zone_id=zone_id,
            namespace=namespace,
            errors=[_clean_error(e) for e in exc.errors(include_url=False)],
        ) from exc


def _clean_error(err: dict[str, Any]) -> dict[str, Any]:
    """Strip Pydantic error entry to the fields AE3 actually uses in events."""
    return {
        "loc": list(err.get("loc", ())),
        "type": err.get("type", "invalid"),
        "msg": err.get("msg", ""),
    }
