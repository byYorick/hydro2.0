"""Pydantic v2 model for recipe phase runtime payload.

Mirrors `schemas/recipe_phase.v1.json`. Used by AE3 to validate the merged
shape of `grow_cycles.currentPhase` payload (plus zone target overrides),
which AE3 reads as `snapshot.phase_targets`, `snapshot.targets` and
`snapshot.diagnostics_execution`.

Drift between this file and `recipe_phase.v1.json` is caught by
`test_ae3lite_pydantic_jsonschema_parity.py` (extend EXPECTED_FIELDS as
new fields are added).

Used by live-mode hot-reload of recipe phase and by schema/runtime parity
checks.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

# ─── Type aliases ──────────────────────────────────────────────────────────

PhValue = Annotated[float, Field(ge=0.0, le=14.0)]
EcValue = Annotated[float, Field(ge=0.0, le=20.0)]
Milliseconds600k = Annotated[int, Field(ge=0, le=600_000)]
Milliseconds60k = Annotated[int, Field(ge=0, le=60_000)]
SmallSeconds = Annotated[int, Field(ge=0, le=86400)]
PositiveCount100 = Annotated[int, Field(ge=1, le=100)]
ZeroToTen = Annotated[int, Field(ge=0, le=10)]
Percent100 = Annotated[float, Field(ge=0.0, le=100.0)]
EcShare = Annotated[float, Field(ge=0.0, le=1.0)]


# ─── phase_targets ─────────────────────────────────────────────────────────

class PhTargets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target: PhValue
    min: PhValue | None = None
    max: PhValue | None = None


class EcTargets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target: EcValue
    min: EcValue | None = None
    max: EcValue | None = None


class EcComponentRatios(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    npk_ec_share: EcShare | None = None


class PhaseTargetsExtensions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Day/night structure is recipe-owned and intentionally loose at this
    # schema version. Refine in v2.
    day_night: Mapping[str, Any] | None = None


class PhaseTargets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ph: PhTargets
    ec: EcTargets
    day_night_enabled: bool | None = None
    ec_component_ratios: EcComponentRatios | None = None
    extensions: PhaseTargetsExtensions | None = None


# ─── targets.irrigation ────────────────────────────────────────────────────

class IrrigationTargets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    correction_during_irrigation: bool
    correction_slack_sec: Annotated[int, Field(ge=0, le=7200)]
    stage_timeout_sec: Annotated[int, Field(ge=60, le=86400)]
    mode: Annotated[str, Field(max_length=32)] | None = None
    interval: Annotated[int, Field(ge=0)] | None = None
    duration: Annotated[int, Field(ge=0)] | None = None


class IrrigationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: Literal["task", "smart_soil_v1"]
    lookback_sec: Annotated[int, Field(ge=1, le=86400)] | None = None
    min_samples: Annotated[int, Field(ge=1, le=1000)] | None = None
    stale_threshold_sec: Annotated[int, Field(ge=1, le=86400)] | None = None
    hysteresis_percent: Percent100 | None = None


class IrrigationRecovery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_continue_attempts: PositiveCount100
    timeout_sec: Annotated[int, Field(ge=1, le=86400)]
    max_replays: ZeroToTen


class IrrigationSafety(BaseModel):
    """Loose schema (`additionalProperties: true` mirrored as Mapping[str, Any])."""
    model_config = ConfigDict(extra="allow", frozen=True)


class IrrigationSubsystemTargets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    soil_moisture: Mapping[str, Any] | None = None


class IrrigationSubsystem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: IrrigationDecision
    recovery: IrrigationRecovery
    safety: IrrigationSafety | None = None
    targets: IrrigationSubsystemTargets | None = None


class TargetsSubsystems(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    irrigation: IrrigationSubsystem | None = None


class TargetsExtensions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subsystems: TargetsSubsystems | None = None


class Targets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    irrigation: IrrigationTargets | None = None
    extensions: TargetsExtensions | None = None


# ─── diagnostics_execution ─────────────────────────────────────────────────

class CommandStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    channel: Annotated[str, Field(min_length=1, max_length=64)]
    cmd: Literal["set_relay", "set_pwm", "run_pump"]
    params: Mapping[str, Any] | None = None


class TwoTankCommands(BaseModel):
    """Per-plan relay command overrides. Plan names are fixed by the AE3
    two-tank topology (see runtime_plan_builder._REQUIRED_TWO_TANK_PLAN_CHANNELS).
    All plans optional at this schema level — runtime decides which are needed."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    irrigation_start: list[CommandStep] | None = None
    irrigation_stop: list[CommandStep] | None = None
    clean_fill_start: list[CommandStep] | None = None
    clean_fill_stop: list[CommandStep] | None = None
    solution_fill_start: list[CommandStep] | None = None
    solution_fill_stop: list[CommandStep] | None = None
    prepare_recirculation_start: list[CommandStep] | None = None
    prepare_recirculation_stop: list[CommandStep] | None = None
    irrigation_recovery_start: list[CommandStep] | None = None
    irrigation_recovery_stop: list[CommandStep] | None = None


class FailSafeGuards(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    clean_fill_min_check_delay_ms: Milliseconds600k
    solution_fill_min_check_delay_ms: Milliseconds600k
    solution_fill_max_check_delay_ms: Milliseconds600k
    estop_debounce_ms: Milliseconds60k


class DiagnosticsStartup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    irr_state_wait_timeout_sec: Annotated[float, Field(ge=0.0, le=30.0)]


class DiagnosticsExecution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    two_tank_commands: TwoTankCommands
    fail_safe_guards: FailSafeGuards
    startup: DiagnosticsStartup


# ─── Root ──────────────────────────────────────────────────────────────────

class RecipePhase(BaseModel):
    """Root model — recipe phase runtime payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase_targets: PhaseTargets
    targets: Targets
    diagnostics_execution: DiagnosticsExecution
