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

class PrepareToleranceRuntime(BaseModel):
    """Runtime tolerance for prepare phase (mirrors source dict from
    `_build_prepare_tolerance_cfg`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ph_pct: Annotated[float, Field(ge=0.1, le=100.0)]
    ec_pct: Annotated[float, Field(ge=0.1, le=100.0)]


class CommandStep(BaseModel):
    """One step in a command plan (relay/pump/pwm). Mirrors entries produced
    by `_normalize_command_steps`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    channel: ChannelStr
    cmd: Annotated[str, Field(min_length=1, max_length=64)]
    params: Mapping[str, Any]
    node_types: list[str]
    complete_on_ack: bool


class FailSafeGuards(BaseModel):
    """Fail-safe delay/debounce guards consumed by phase handlers.

    Note: keys differ from `recipe_phase.FailSafeGuards` — runtime spec
    flattens the recipe shape and adds `recirculation_stop_on_solution_min`
    and `irrigation_stop_on_solution_min` booleans. `clean_fill_min_check_delay_ms`
    is deprecated: clean_fill does not consume it; the value remains mirror-only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    clean_fill_min_check_delay_ms: LargeMs
    solution_fill_clean_min_check_delay_ms: LargeMs
    solution_fill_solution_min_check_delay_ms: LargeMs
    solution_topup_clean_min_check_delay_ms: LargeMs = 5000
    solution_topup_solution_min_check_delay_ms: LargeMs = 60000
    recirculation_stop_on_solution_min: bool
    irrigation_stop_on_solution_min: bool
    estop_debounce_ms: EstopMs


class IrrigationExecution(BaseModel):
    """Resolved irrigation execution params from `targets.irrigation`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    duration_sec: int | None = None
    interval_sec: int | None = None
    correction_during_irrigation: bool
    # Inline nutrient during irrigation: none = pH-only; calcium|npk = pH + that EC pump.
    irrigation_ec_component: Literal["none", "calcium", "npk"] = "none"
    correction_slack_sec: Annotated[int, Field(ge=0, le=7200)]
    stage_timeout_sec: int | None = None


class IrrigationDecisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lookback_sec: Annotated[int, Field(ge=60, le=86400)]
    min_samples: Annotated[int, Field(ge=1, le=100)]
    stale_after_sec: Annotated[int, Field(ge=30, le=86400)]
    hysteresis_pct: Annotated[float, Field(ge=0.0, le=100.0)]
    spread_alert_threshold_pct: Annotated[float, Field(ge=0.0, le=100.0)]


class IrrigationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: str
    config: IrrigationDecisionConfig


class IrrigationRecovery(BaseModel):
    """Setup-replay only, not chemistry.

    Post-irrigation EC/pH recovery stages were removed; ``enabled`` stays False.
    Live consumers (irrigation_check / workflow_router) read only:
    - ``max_setup_replays`` — solution_min → setup replay budget
    - ``auto_replay_after_setup`` — auto-restart irrigation after setup replay
    Field name kept for runtime_plan / config schema compat (rename is out of scope).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False  # chemistry recovery removed; always False at runtime
    max_continue_attempts: Annotated[int, Field(ge=1, le=30)] = 3
    timeout_sec: Annotated[int, Field(ge=30, le=86400)] = 600
    auto_replay_after_setup: bool = False
    max_setup_replays: Annotated[int, Field(ge=0, le=10)] = 0


class RecircDiluteConfig(BaseModel):
    """Dilute-on-overshoot thresholds for prepare recirculation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ec_overshoot_dilute_pct: Annotated[float, Field(ge=1.0, le=100.0)] = 15.0
    dilute_pulse_sec: Annotated[int, Field(ge=1, le=600)] = 10
    dilute_max_attempts: Annotated[int, Field(ge=0, le=20)] = 3
    dilute_settle_sec: Annotated[int, Field(ge=0, le=3600)] = 30


class IrrigationSafety(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stop_on_solution_min: bool


class SoilMoistureTarget(BaseModel):
    """Loose schema — two variants supported (subsystems.targets vs day_night
    fallback). All numeric fields optional. Validated structurally only."""

    model_config = ConfigDict(extra="allow", frozen=True)

    unit: str | None = None
    min: float | None = None
    max: float | None = None
    target: float | None = None
    day: float | None = None
    night: float | None = None
    day_start_time: str | None = None
    day_hours: float | None = None


class DayNightLighting(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    day_start_time: str | None = None
    day_hours: HoursFloat | None = None
    timezone: str | None = None


class DayNightChannelTargets(BaseModel):
    """Day/night targets for one channel (ph or ec). All optional —
    resolver sets None when source missing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    day: float | None = None
    night: float | None = None
    day_min: float | None = None
    day_max: float | None = None
    night_min: float | None = None
    night_max: float | None = None


class DayNightConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    lighting: DayNightLighting
    ph: DayNightChannelTargets
    ec: DayNightChannelTargets


# ─── Per-phase correction config ──────────────────────────────────────────

class CorrectionPhaseRuntime(BaseModel):
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
    safety: Mapping[str, Any] | None = None
    ec_dosing_mode: Literal["single", "multi_parallel", "multi_sequential"]
    ec_component_ratios: Mapping[str, Any]
    ec_excluded_components: tuple[str, ...]
    actuators: Mapping[str, Any]


# ─── Process calibration (per phase) ───────────────────────────────────────

class ProcessCalibrationRuntime(BaseModel):
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


# ─── Срезы подсистем. RuntimePlan — их объединение. ───────────────────────

_SLICE_CONFIG = ConfigDict(extra="forbid", frozen=True)


class SolutionRuntimeSlice(BaseModel):
    """Таймауты и датчики баков: solution / clean fill / topup / drain."""

    model_config = _SLICE_CONFIG

    clean_fill_timeout_sec: Annotated[int, Field(ge=30, le=86400)]
    solution_fill_timeout_sec: Annotated[int, Field(ge=30, le=86400)]
    prepare_recirculation_timeout_sec: Annotated[int, Field(ge=30, le=7200)]
    prepare_recirculation_correction_slack_sec: Annotated[int, Field(ge=0, le=7200)]
    solution_fill_correction_slack_sec: Annotated[int, Field(ge=0, le=7200)]
    level_poll_interval_sec: Annotated[int, Field(ge=5, le=3600)]
    clean_fill_retry_cycles: Annotated[int, Field(ge=0, le=20)]
    level_switch_on_threshold: Annotated[float, Field(ge=0.0, le=1.0)]
    sensor_mode_stabilization_time_sec: ShortSeconds
    clean_max_sensor_labels: list[LabelStr]
    clean_min_sensor_labels: list[LabelStr]
    solution_max_sensor_labels: list[LabelStr]
    solution_min_sensor_labels: list[LabelStr]
    solution_topup_enabled: bool = True
    solution_topup_timeout_sec: Annotated[int, Field(ge=30, le=86400)] = 900
    solution_topup_cooldown_sec: Annotated[int, Field(ge=0, le=86400)] = 300
    solution_change_enabled: bool = False
    solution_drain_timeout_sec: Annotated[int, Field(ge=30, le=86400)] = 900
    solution_change_operator_confirm_timeout_sec: Annotated[int, Field(ge=60, le=86400)] = 3600


class IrrigationRuntimeSlice(BaseModel):
    """Полив: irr_state, fail-safe и decision."""

    model_config = _SLICE_CONFIG

    telemetry_max_age_sec: Annotated[int, Field(ge=5, le=3600)]
    irr_state_max_age_sec: Annotated[int, Field(ge=5, le=3600)]
    irr_state_wait_timeout_sec: Annotated[float, Field(ge=0.0, le=30.0)]
    fail_safe_guards: FailSafeGuards
    irrigation_execution: IrrigationExecution
    irrigation_decision: IrrigationDecision
    irrigation_recovery: IrrigationRecovery
    irrigation_safety: IrrigationSafety
    irrigation_recovery_correction_slack_sec: Annotated[int, Field(ge=0, le=7200)] = 900
    irr_state_wait_poll_interval_sec: Annotated[float, Field(ge=0.0, le=5.0)] | None = None
    soil_moisture_target: SoilMoistureTarget | None = None
    semi_allows_active_flow: bool = False


class CorrectionRuntimeSlice(BaseModel):
    """Химия: targets, PID и correction config."""

    model_config = _SLICE_CONFIG

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
    prepare_tolerance: PrepareToleranceRuntime
    prepare_tolerance_by_phase: dict[str, PrepareToleranceRuntime]
    pid_state: Mapping[str, Any]
    pid_configs: Mapping[str, Any]
    process_calibrations: dict[str, ProcessCalibrationRuntime]
    correction: CorrectionPhaseRuntime
    correction_by_phase: dict[str, CorrectionPhaseRuntime]
    ec_component_ratios: Mapping[str, Any] = {}
    recirc: RecircDiluteConfig = RecircDiluteConfig()


class LightingRuntimeSlice(BaseModel):
    """День/ночь света, который гидравлический план несёт рядом с поливом."""

    model_config = _SLICE_CONFIG

    day_night_enabled: bool
    day_night_config: DayNightConfig


class RuntimePlan(
    SolutionRuntimeSlice,
    IrrigationRuntimeSlice,
    CorrectionRuntimeSlice,
    LightingRuntimeSlice,
):
    """Собранный план активного пакета topology.

    Поля — объединение срезов подсистем. Набор ``command_specs`` режет
    сборщик по ``TopologyPack.command_plan_keys``, схема остаётся общей:
    handler-ы читают атрибуты, а не dict.

    Drift detection: любое новое поле ``resolve_two_tank_runtime`` /
    ``assemble_pack_runtime`` должно попасть в свой срез.
    """

    model_config = _SLICE_CONFIG

    required_node_types: list[str]
    command_specs: dict[str, list[CommandStep]]
    zone_workflow_phase: str | None = None
    grow_cycle_id: int | None = None
    bundle_revision: str | None = None
    config_revision: int | None = None


# ─── Re-export of building blocks (handy for tests / type-aware consumers) ──

__all__ = [
    "RuntimePlan",
    "SolutionRuntimeSlice",
    "IrrigationRuntimeSlice",
    "CorrectionRuntimeSlice",
    "LightingRuntimeSlice",
    "CorrectionPhaseRuntime",
    "PrepareToleranceRuntime",
    "CommandStep",
    "FailSafeGuards",
    "IrrigationExecution",
    "IrrigationDecision",
    "IrrigationDecisionConfig",
    "IrrigationRecovery",
    "RecircDiluteConfig",
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
