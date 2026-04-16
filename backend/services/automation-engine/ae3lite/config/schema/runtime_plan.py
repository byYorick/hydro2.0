"""Pydantic v2 model for the full `plan.runtime` dict shape.

`RuntimePlan` mirrors the output of `resolve_two_tank_runtime(snapshot)` —
that is, the dict that handlers consume as `plan.runtime`. Unlike
`ZoneCorrection` (which mirrors raw `zone.correction` document), this model
is the **resolved + flattened** runtime view used by AE3 handlers.

Drift detection: `test_ae3lite_pydantic_jsonschema_parity.py` covers
`ZoneCorrection`. RuntimePlan does NOT have a JSON Schema mirror — it is the
Python-only contract for AE3 handlers (the canonical source for this
shape lives in `resolve_two_tank_runtime` itself).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from ae3lite.config.schema.zone_correction import (
    Controllers,
    Dosing,
    Retry,
    Runtime,
    Safety,
    Timing,
    Tolerance,
    _DictShim,
)


# ─── Type aliases ──────────────────────────────────────────────────────────

PhValue = Annotated[float, Field(ge=0.0, le=14.0)]
EcValue = Annotated[float, Field(ge=0.0, le=20.0)]
EcShare = Annotated[float, Field(ge=0.0, le=1.0)]
LabelStr = Annotated[str, Field(min_length=1, max_length=128)]
ChannelStr = Annotated[str, Field(min_length=1, max_length=64)]
PositiveCount500 = Annotated[int, Field(ge=1, le=500)]
PositiveCount100 = Annotated[int, Field(ge=1, le=100)]
LongSeconds = Annotated[int, Field(ge=1, le=86400)]
ShortSeconds = Annotated[int, Field(ge=0, le=86400)]
LargeMs = Annotated[int, Field(ge=0, le=3_600_000)]
EstopMs = Annotated[int, Field(ge=20, le=5000)]
HoursFloat = Annotated[float, Field(ge=0.0, le=24.0)]


# ─── Sub-blocks (nested) ───────────────────────────────────────────────────

class PrepareToleranceRuntime(_DictShim, BaseModel):
    """Runtime tolerance for prepare phase (mirrors source dict from
    `_build_prepare_tolerance_cfg`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ph_pct: Annotated[float, Field(ge=0.1, le=100.0)]
    ec_pct: Annotated[float, Field(ge=0.1, le=100.0)]


class CommandStep(_DictShim, BaseModel):
    """One step in a command plan (relay/pump/pwm). Mirrors entries produced
    by `_normalize_command_steps`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    channel: ChannelStr
    cmd: Annotated[str, Field(min_length=1, max_length=64)]
    params: Mapping[str, Any]
    node_types: list[str]
    complete_on_ack: bool


class FailSafeGuards(_DictShim, BaseModel):
    """Fail-safe delay/debounce guards consumed by phase handlers.

    Note: keys differ from `recipe_phase.FailSafeGuards` — runtime spec
    flattens the recipe shape and adds `recirculation_stop_on_solution_min`
    and `irrigation_stop_on_solution_min` booleans."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    clean_fill_min_check_delay_ms: LargeMs
    solution_fill_clean_min_check_delay_ms: LargeMs
    solution_fill_solution_min_check_delay_ms: LargeMs
    recirculation_stop_on_solution_min: bool
    irrigation_stop_on_solution_min: bool
    estop_debounce_ms: EstopMs


class IrrigationExecution(_DictShim, BaseModel):
    """Resolved irrigation execution params from `targets.irrigation`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    duration_sec: int | None = None
    interval_sec: int | None = None
    correction_during_irrigation: bool
    correction_slack_sec: Annotated[int, Field(ge=0, le=7200)]
    stage_timeout_sec: int | None = None


class IrrigationDecisionConfig(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lookback_sec: Annotated[int, Field(ge=60, le=86400)]
    min_samples: Annotated[int, Field(ge=1, le=100)]
    stale_after_sec: Annotated[int, Field(ge=30, le=86400)]
    hysteresis_pct: Annotated[float, Field(ge=0.0, le=100.0)]
    spread_alert_threshold_pct: Annotated[float, Field(ge=0.0, le=100.0)]


class IrrigationDecision(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: str
    config: IrrigationDecisionConfig


class IrrigationRecovery(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_continue_attempts: Annotated[int, Field(ge=1, le=30)]
    timeout_sec: Annotated[int, Field(ge=30, le=86400)]
    auto_replay_after_setup: bool
    max_setup_replays: Annotated[int, Field(ge=0, le=10)]


class IrrigationSafety(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stop_on_solution_min: bool


class SoilMoistureTarget(_DictShim, BaseModel):
    """Loose schema — two variants supported (subsystems.targets vs day_night
    fallback). All numeric fields optional. Validated structurally only."""

    model_config = ConfigDict(extra="allow", frozen=True)

    unit: str
    min: float | None = None
    max: float | None = None
    target: float | None = None
    day: float | None = None
    night: float | None = None
    day_start_time: str | None = None
    day_hours: float | None = None


class DayNightLighting(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    day_start_time: str | None = None
    day_hours: HoursFloat | None = None
    timezone: str | None = None


class DayNightChannelTargets(_DictShim, BaseModel):
    """Day/night targets for one channel (ph or ec). All optional —
    resolver sets None when source missing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    day: float | None = None
    night: float | None = None
    day_min: float | None = None
    day_max: float | None = None
    night_min: float | None = None
    night_max: float | None = None


class DayNightConfig(_DictShim, BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    lighting: DayNightLighting
    ph: DayNightChannelTargets
    ec: DayNightChannelTargets


# ─── Per-phase correction config ──────────────────────────────────────────

class CorrectionPhaseRuntime(_DictShim, BaseModel):
    """Flattened per-phase correction config produced by
    `_build_correction_cfg`. Differs from `ZoneCorrection`: hierarchy is
    promoted to the top level (no nested `dosing`/`retry`/`timing`), and
    extra runtime fields (`pump_calibration`, `actuators`,
    `ec_component_policy`) are present.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    dose_ec_channel: ChannelStr
    dose_ph_up_channel: ChannelStr
    dose_ph_down_channel: ChannelStr
    max_ec_dose_ml: Annotated[float, Field(ge=1.0, le=500.0)]
    max_ph_dose_ml: Annotated[float, Field(ge=0.5, le=200.0)]
    stabilization_sec: ShortSeconds
    max_ec_correction_attempts: PositiveCount500
    max_ph_correction_attempts: PositiveCount500
    prepare_recirculation_max_attempts: Annotated[int, Field(ge=1, le=100)]
    prepare_recirculation_max_correction_attempts: PositiveCount500
    telemetry_stale_retry_sec: Annotated[int, Field(ge=1, le=3600)]
    decision_window_retry_sec: Annotated[int, Field(ge=1, le=3600)]
    low_water_retry_sec: Annotated[int, Field(ge=1, le=3600)]
    solution_volume_l: Annotated[float, Field(ge=1.0, le=10_000.0)]
    controllers: Controllers
    pump_calibration: Mapping[str, Any]
    ec_component_policy: Mapping[str, Any]
    ec_dosing_mode: Literal["single", "multi_parallel", "multi_sequential"]
    ec_component_ratios: Mapping[str, Any]
    ec_excluded_components: tuple[str, ...]
    actuators: Mapping[str, Any]


# ─── Process calibration (per phase) ───────────────────────────────────────

class ProcessCalibrationRuntime(_DictShim, BaseModel):
    """Loose model: calibration entries are read straight from
    `pump_calibrations` table — they carry lifecycle metadata
    (`valid_from/to`, `is_active`, `meta`) that resolver does not strip.
    `extra="allow"` keeps it forward-compatible.
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    ec_gain_per_ml: float | None = None
    ph_up_gain_per_ml: float | None = None
    ph_down_gain_per_ml: float | None = None
    ph_per_ec_ml: float | None = None
    ec_per_ph_ml: float | None = None
    transport_delay_sec: int | None = None
    settle_sec: int | None = None
    confidence: float | None = None
    source: str | None = None
    meta: Any = None


# ─── Root: RuntimePlan ─────────────────────────────────────────────────────

class RuntimePlan(_DictShim, BaseModel):
    """Full typed mirror of `plan.runtime` dict (output of
    `resolve_two_tank_runtime`).

    32 top-level fields + 10 nested structures. Drift detection: any change
    in `resolve_two_tank_runtime` output that adds/removes/renames a key must
    be reflected here.

    `RuntimePlan`
    implements a read-only dict-like API (`__getitem__`, `get`, `__contains__`,
    `keys`, `items`, `values`). Legacy nested reads like
    `plan.runtime["correction"]["retry"]["telemetry_stale_retry_sec"]` still
    work because nested values are also dict-like (Pydantic models with the
    same shim).

    Per-instance shim cost: ~1 attribute lookup + ~1 dict() call per top-level
    read. Negligible vs handler I/O.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Required node setup
    required_node_types: list[str]

    # Timeouts / poll intervals
    clean_fill_timeout_sec: Annotated[int, Field(ge=30, le=86400)]
    solution_fill_timeout_sec: Annotated[int, Field(ge=30, le=86400)]
    prepare_recirculation_timeout_sec: Annotated[int, Field(ge=30, le=7200)]
    prepare_recirculation_correction_slack_sec: Annotated[int, Field(ge=0, le=7200)]
    level_poll_interval_sec: Annotated[int, Field(ge=5, le=3600)]
    clean_fill_retry_cycles: Annotated[int, Field(ge=0, le=20)]
    level_switch_on_threshold: Annotated[float, Field(ge=0.0, le=1.0)]
    telemetry_max_age_sec: Annotated[int, Field(ge=5, le=3600)]
    irr_state_max_age_sec: Annotated[int, Field(ge=5, le=3600)]
    irr_state_wait_timeout_sec: Annotated[float, Field(ge=0.0, le=30.0)]
    sensor_mode_stabilization_time_sec: ShortSeconds

    # Sensor labels (plural — singular dropped in v1)
    clean_max_sensor_labels: list[LabelStr]
    clean_min_sensor_labels: list[LabelStr]
    solution_max_sensor_labels: list[LabelStr]
    solution_min_sensor_labels: list[LabelStr]

    # Targets (resolved from active phase_targets)
    target_ph: PhValue
    target_ec: EcValue
    target_ph_min: PhValue
    target_ph_max: PhValue
    target_ec_min: EcValue
    target_ec_max: EcValue
    target_ec_prepare: EcValue
    target_ec_prepare_min: EcValue
    target_ec_prepare_max: EcValue
    npk_ec_share: EcShare

    # Day/night
    day_night_enabled: bool
    day_night_config: DayNightConfig

    # Tolerance
    prepare_tolerance: PrepareToleranceRuntime
    prepare_tolerance_by_phase: dict[str, PrepareToleranceRuntime]

    # PID state/configs/calibrations (loose — owned by handlers)
    pid_state: Mapping[str, Any]
    pid_configs: Mapping[str, Any]
    process_calibrations: dict[str, ProcessCalibrationRuntime]

    # Correction
    correction: CorrectionPhaseRuntime
    correction_by_phase: dict[str, CorrectionPhaseRuntime]

    # Command plans (10 plan names hardcoded by two_tank topology)
    command_specs: dict[str, list[CommandStep]]

    # Fail-safe + irrigation subsystems
    fail_safe_guards: FailSafeGuards
    irrigation_execution: IrrigationExecution
    irrigation_decision: IrrigationDecision
    irrigation_recovery: IrrigationRecovery
    irrigation_safety: IrrigationSafety
    soil_moisture_target: SoilMoistureTarget | None = None
    # Derived: cycle_start_planner injects the active workflow phase string
    # (snapshot.workflow_phase normalized) for handler convenience.
    zone_workflow_phase: str | None = None
    # Optional cycle context consumed by await_ready observability/events.
    grow_cycle_id: int | None = None
    # Derived: cycle_start_planner injects the bundle_revision tag locked
    # for the active irrigation decision snapshot. Optional — only set when
    # `task.irrigation_bundle_revision` is non-empty.
    bundle_revision: str | None = None
    # Phase 5: monotonic `zones.config_revision` at plan-build time. Used by
    # `BaseStageHandler._checkpoint()` to detect live-mode config edits (compared
    # to current `zones.config_revision`). Distinct from `bundle_revision`
    # (content hash) — this is a simple integer counter incremented by
    # `ZoneConfigRevisionService::bumpAndAudit`.
    config_revision: int | None = None


# ─── Re-export of building blocks (handy for tests / type-aware consumers) ──

__all__ = [
    "RuntimePlan",
    "CorrectionPhaseRuntime",
    "PrepareToleranceRuntime",
    "CommandStep",
    "FailSafeGuards",
    "IrrigationExecution",
    "IrrigationDecision",
    "IrrigationDecisionConfig",
    "IrrigationRecovery",
    "IrrigationSafety",
    "SoilMoistureTarget",
    "DayNightConfig",
    "DayNightLighting",
    "DayNightChannelTargets",
    "ProcessCalibrationRuntime",
    # Re-exports from zone_correction for convenience:
    "Controllers",
    "Dosing",
    "Retry",
    "Runtime",
    "Safety",
    "Timing",
    "Tolerance",
]
