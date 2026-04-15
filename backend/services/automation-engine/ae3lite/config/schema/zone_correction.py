"""Pydantic v2 model for `zone.correction` base config.

Mirrors `schemas/zone_correction.v1.json`. This is the shape of both
`automation_config_documents.payload.base_config` (for Laravel side) and of
each `snapshot.correction_config.phases.*` entry after compiler merge
(for AE3 runtime side).

Constraints match JSON Schema exactly. Drift between this file and
`zone_correction.v1.json` is a CI bug (Phase 7: auto-generate AUTHORITY.md
from JSON Schema and compare).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Re-import dict-shim from runtime_plan once it's loaded — avoid circular import
# by deferring. Since runtime_plan imports from this file, we define a local
# minimal shim here and runtime_plan re-uses semantics.


class _DictShim:
    """Read-only dict-like API for transition period (Phase 3.1 / B-5).

    Same semantics as `runtime_plan._DictShim`. Defined here to avoid a
    circular import (runtime_plan imports symbols from zone_correction).
    Phase 4 deletes both copies.
    """

    def __iter__(self):  # type: ignore[no-untyped-def]
        # Mapping ABC requires __iter__ + __len__. Iterate over field names.
        return iter(self.keys())

    def __len__(self) -> int:
        return sum(1 for _ in self.keys())

    def __getitem__(self, key: str) -> Any:
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        fields = getattr(type(self), "model_fields", {})
        if key not in fields:
            return False
        try:
            return getattr(self, key) is not None
        except AttributeError:
            return False

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self:
            return default
        return self[key]

    def keys(self):  # type: ignore[no-untyped-def]
        fields = getattr(type(self), "model_fields", {})
        return (k for k in fields if k in self)

    def items(self):  # type: ignore[no-untyped-def]
        return ((k, self[k]) for k in self.keys())

    def values(self):  # type: ignore[no-untyped-def]
        return (self[k] for k in self.keys())


# Register _DictShim as a virtual Mapping subclass so that
# `isinstance(model, Mapping)` returns True in legacy handler code.
Mapping.register(_DictShim)

# ─── Primitive type aliases ────────────────────────────────────────────────

Seconds = Annotated[int, Field(ge=1, le=86400)]
ShortSeconds = Annotated[int, Field(ge=0, le=3600)]
PositiveCount = Annotated[int, Field(ge=1, le=500)]
# Inclusive lower bound 0.1 — matches `minimum: 0.1` in zone_correction.v1.json
# (Phase 0-2 audit C-1 fix). Earlier `gt=0.0` would accept 0.05 silently.
Percent = Annotated[float, Field(ge=0.1, le=100.0)]
Milliliters = Annotated[float, Field(gt=0.0, le=1000.0)]
Liters = Annotated[float, Field(ge=1.0, le=10_000.0)]

# Non-negative gain/integral factors — used by PID sections.
Gain100 = Annotated[float, Field(ge=0.0, le=100.0)]
Gain1000 = Annotated[float, Field(ge=0.0, le=1000.0)]


# ─── Shared sub-blocks ─────────────────────────────────────────────────────

class AntiWindup(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool


class NoEffect(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    max_count: Annotated[int, Field(ge=1, le=10)]


class Observe(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    telemetry_period_sec: Annotated[int, Field(ge=1, le=300)]
    window_min_samples: Annotated[int, Field(ge=2, le=64)]
    decision_window_sec: Annotated[int, Field(ge=1, le=3600)]
    observe_poll_sec: Annotated[int, Field(ge=1, le=300)]
    min_effect_fraction: Annotated[float, Field(ge=0.01, le=1.0)]
    stability_max_slope: Annotated[float, Field(gt=0.0, le=100.0)]
    no_effect_consecutive_limit: Annotated[int, Field(ge=1, le=10)]


class PhOvershootGuard(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    hard_min: Annotated[float, Field(ge=0.0, le=14.0)]
    hard_max: Annotated[float, Field(ge=0.0, le=14.0)]


class EcOvershootGuard(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    hard_min: Annotated[float, Field(ge=0.0, le=20.0)]
    hard_max: Annotated[float, Field(ge=0.0, le=20.0)]


# ─── Controllers ───────────────────────────────────────────────────────────

class PhController(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["cross_coupled_pi_d"]
    kp: Gain1000
    ki: Gain100
    kd: Gain100
    derivative_filter_alpha: Annotated[float, Field(ge=0.0, le=1.0)]
    deadband: Annotated[float, Field(ge=0.0, le=2.0)]
    max_dose_ml: Milliliters
    min_interval_sec: Annotated[int, Field(ge=1, le=3600)]
    max_integral: Annotated[float, Field(gt=0.0, le=500.0)]
    anti_windup: AntiWindup
    overshoot_guard: PhOvershootGuard
    no_effect: NoEffect
    observe: Observe


class EcController(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["supervisory_allocator"]
    kp: Gain1000
    ki: Gain100
    kd: Gain100
    derivative_filter_alpha: Annotated[float, Field(ge=0.0, le=1.0)]
    deadband: Annotated[float, Field(ge=0.0, le=5.0)]
    max_dose_ml: Milliliters
    min_interval_sec: Annotated[int, Field(ge=1, le=3600)]
    max_integral: Annotated[float, Field(gt=0.0, le=500.0)]
    anti_windup: AntiWindup
    overshoot_guard: EcOvershootGuard
    no_effect: NoEffect
    observe: Observe


class Controllers(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ph: PhController
    ec: EcController


# ─── Runtime / Timing / Dosing / Retry / Tolerance / Safety ────────────────

class Runtime(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_node_type: Annotated[str, Field(min_length=1, max_length=64)]
    clean_fill_timeout_sec: Annotated[int, Field(ge=30, le=86400)]
    solution_fill_timeout_sec: Annotated[int, Field(ge=30, le=86400)]
    clean_fill_retry_cycles: Annotated[int, Field(ge=0, le=20)]
    level_switch_on_threshold: Annotated[float, Field(ge=0.0, le=1.0)]
    clean_max_sensor_label: Annotated[str, Field(min_length=1, max_length=128)]
    clean_min_sensor_label: Annotated[str, Field(min_length=1, max_length=128)]
    solution_max_sensor_label: Annotated[str, Field(min_length=1, max_length=128)]
    solution_min_sensor_label: Annotated[str, Field(min_length=1, max_length=128)]


class Timing(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sensor_mode_stabilization_time_sec: ShortSeconds
    stabilization_sec: ShortSeconds
    telemetry_max_age_sec: Annotated[int, Field(ge=5, le=3600)]
    irr_state_max_age_sec: Annotated[int, Field(ge=5, le=3600)]
    level_poll_interval_sec: Annotated[int, Field(ge=5, le=3600)]


class Dosing(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    solution_volume_l: Liters
    dose_ec_channel: Annotated[str, Field(min_length=1, max_length=64)]
    dose_ph_up_channel: Annotated[str, Field(min_length=1, max_length=64)]
    dose_ph_down_channel: Annotated[str, Field(min_length=1, max_length=64)]
    max_ec_dose_ml: Annotated[float, Field(ge=0.1, le=1000.0)]
    max_ph_dose_ml: Annotated[float, Field(ge=0.1, le=1000.0)]
    # `multi_sequential` is the legacy recipe-resolver value (v1 ec_component_policy);
    # `single` and `multi_parallel` come from the new catalog. All three accepted.
    ec_dosing_mode: Literal["single", "multi_parallel", "multi_sequential"]


class Retry(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_ec_correction_attempts: PositiveCount
    max_ph_correction_attempts: PositiveCount
    prepare_recirculation_timeout_sec: Annotated[int, Field(ge=30, le=7200)]
    prepare_recirculation_correction_slack_sec: Annotated[int, Field(ge=0, le=7200)]
    prepare_recirculation_max_attempts: Annotated[int, Field(ge=1, le=10)]
    prepare_recirculation_max_correction_attempts: PositiveCount
    telemetry_stale_retry_sec: Annotated[int, Field(ge=1, le=3600)]
    decision_window_retry_sec: Annotated[int, Field(ge=1, le=3600)]
    low_water_retry_sec: Annotated[int, Field(ge=1, le=3600)]


class PrepareTolerance(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ph_pct: Percent
    ec_pct: Percent


class Tolerance(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prepare_tolerance: PrepareTolerance


class Safety(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    safe_mode_on_no_effect: bool
    block_on_active_no_effect_alert: bool


# ─── Root ──────────────────────────────────────────────────────────────────

class ZoneCorrection(_DictShim, BaseModel):
    """Root model — `zone.correction` base config.

    Optional fields `ec_component_ratios`, `ec_excluded_components`, `system_type`
    are injected by the recipe nutrition resolver during grow_cycle bundle
    compile (RecipeNutritionRuntimeConfigResolver). They are not part of the
    catalog defaults but appear in resolved correction phases — schema accepts
    them so AE3 shadow validation matches reality.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    controllers: Controllers
    runtime: Runtime
    timing: Timing
    dosing: Dosing
    retry: Retry
    tolerance: Tolerance
    safety: Safety
    ec_component_ratios: dict[str, Annotated[float, Field(ge=0.0, le=100.0)]] | None = None
    ec_excluded_components: list[Annotated[str, Field(min_length=1, max_length=64)]] | None = None
    system_type: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    # TOP-LEVEL alias of dosing.ec_dosing_mode injected by recipe nutrition resolver.
    # Different field from `dosing.ec_dosing_mode` — they may carry different values
    # (recipe override vs catalog default). Both legal in resolved phase config.
    ec_dosing_mode: Literal["single", "multi_parallel", "multi_sequential"] | None = None
    ec_component_policy: dict[str, Any] | None = None
