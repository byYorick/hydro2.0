"""Pure domain service for AE3-Lite correction dose planning."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
import math
from typing import Any, Mapping, Optional

from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.phase_utils import normalize_phase_key

_logger = logging.getLogger(__name__)

# ── Defaults for dose computation (5.1: named constants replacing magic numbers) ──

#: Default solution tank volume when not provided in correction_config.
_DEFAULT_SOLUTION_VOLUME_L: float = 100.0

#: Hard upper limit for a single EC dose when correction_config.max_ec_dose_ml is absent.
_DEFAULT_MAX_EC_DOSE_ML: float = 50.0

#: Hard upper limit for a single pH dose when correction_config.max_ph_dose_ml is absent.
_DEFAULT_MAX_PH_DOSE_ML: float = 20.0

# ── EC component selection fallback order (5.3) ──────────────────────────────

#: Preferred order for EC components when no ec_component_policy is configured.
#: Components not in this list are appended alphabetically after the listed ones.
_EC_COMPONENT_DEFAULT_ORDER: tuple[str, ...] = ("npk", "a", "b", "ca", "mg", "micro", "trace")


@dataclass(frozen=True)
class DosePlan:
    """Resolved correction actions for the current measurement snapshot."""

    needs_ec: bool = False
    ec_component: str = ""
    ec_node_uid: str = ""
    ec_channel: str = ""
    ec_amount_ml: float = 0.0
    ec_duration_ms: int = 0
    ec_retry_after_sec: Optional[int] = None

    needs_ph_up: bool = False
    needs_ph_down: bool = False
    ph_node_uid: str = ""
    ph_channel: str = ""
    ph_amount_ml: float = 0.0
    ph_duration_ms: int = 0
    ph_retry_after_sec: Optional[int] = None

    retry_after_sec: Optional[int] = None
    pid_state_updates: Mapping[str, Any] = field(default_factory=dict)

    @property
    def needs_any(self) -> bool:
        return self.needs_ec or self.needs_ph_up or self.needs_ph_down

    @property
    def ph_direction(self) -> str:
        if self.needs_ph_up:
            return "up"
        if self.needs_ph_down:
            return "down"
        return "none"


class CorrectionPlanner:
    """Domain planner for EC/pH dose pulses."""

    def is_within_tolerance(
        self,
        *,
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        ph_tolerance_pct: float,
        ec_tolerance_pct: float,
        ph_min: float | None = None,
        ph_max: float | None = None,
        ec_min: float | None = None,
        ec_max: float | None = None,
    ) -> bool:
        ph_has_explicit_window = ph_min is not None and ph_max is not None
        ec_has_explicit_window = ec_min is not None and ec_max is not None
        ph_lo, ph_hi = _resolve_bounds(
            target=target_ph,
            lower=ph_min,
            upper=ph_max,
            tolerance_pct=ph_tolerance_pct,
        )
        ec_lo, ec_hi = _resolve_bounds(
            target=target_ec,
            lower=ec_min,
            upper=ec_max,
            tolerance_pct=ec_tolerance_pct,
        )
        return ph_lo <= current_ph <= ph_hi and ec_lo <= current_ec <= ec_hi

    def build_dose_plan(
        self,
        *,
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        ph_tolerance_pct: float,
        ec_tolerance_pct: float,
        correction_config: Mapping[str, Any],
        workflow_phase: str | None = None,
        process_calibrations: Optional[Mapping[str, Any]] = None,
        ec_component_policy: Optional[Mapping[str, Any]] = None,
        pid_state: Optional[Mapping[str, Any]] = None,
        now: Optional[datetime] = None,
        ph_min: float | None = None,
        ph_max: float | None = None,
        ec_min: float | None = None,
        ec_max: float | None = None,
        ec_actuator: Optional[Mapping[str, Any]] = None,
        ec_actuators: Optional[Mapping[str, Any]] = None,
        ph_up_actuator: Optional[Mapping[str, Any]] = None,
        ph_down_actuator: Optional[Mapping[str, Any]] = None,
    ) -> DosePlan:
        phase_key = normalize_phase_key(workflow_phase)
        process_cfg = _phase_mapping(process_calibrations).get(phase_key, {})
        process_cfg = process_cfg if isinstance(process_cfg, Mapping) else {}
        pid_state = pid_state if isinstance(pid_state, Mapping) else {}
        now = _to_utc_naive(now or datetime.now(UTC))

        ph_lo, ph_hi = _resolve_bounds(
            target=target_ph,
            lower=ph_min,
            upper=ph_max,
            tolerance_pct=ph_tolerance_pct,
        )
        ec_lo, ec_hi = _resolve_bounds(
            target=target_ec,
            lower=ec_min,
            upper=ec_max,
            tolerance_pct=ec_tolerance_pct,
        )

        ph_has_explicit_window = ph_min is not None and ph_max is not None
        ec_has_explicit_window = ec_min is not None and ec_max is not None

        pid_updates = _reset_pid_state_if_inside_bounds(
            current_ph=current_ph,
            current_ec=current_ec,
            ph_lo=ph_lo,
            ph_hi=ph_hi,
            ec_lo=ec_lo,
            ec_hi=ec_hi,
            pid_state=pid_state,
            now=now,
        )

        predicted_ph = _apply_feedforward_bias(
            current_value=current_ph,
            pid_entry=_pid_entry(pid_state, "ph"),
            now=now,
        )

        controller_ec = _controller_cfg(correction_config, "ec")
        controller_ph = _controller_cfg(correction_config, "ph")
        solution_volume_l = _positive_float(correction_config.get("solution_volume_l"), _DEFAULT_SOLUTION_VOLUME_L)

        ec_gap = max(0.0, (ec_lo - current_ec) if ec_has_explicit_window else (target_ec - current_ec))
        ph_up_gap = max(0.0, (ph_lo - predicted_ph) if ph_has_explicit_window else (target_ph - predicted_ph))
        ph_down_gap = max(0.0, (predicted_ph - ph_hi) if ph_has_explicit_window else (predicted_ph - target_ph))

        ec_deadband = _non_negative_float(controller_ec.get("deadband"), 0.0)
        ph_deadband = _non_negative_float(controller_ph.get("deadband"), 0.0)

        ec_needs = ec_gap > 0.0 if ec_has_explicit_window else ec_gap > ec_deadband
        ph_needs_up = ph_up_gap > 0.0 if ph_has_explicit_window else ph_up_gap > ph_deadband
        ph_needs_down = ph_down_gap > 0.0 if ph_has_explicit_window else ph_down_gap > ph_deadband

        ec_retry_after = None
        ph_retry_after = None

        ec_component_name = ""
        ec_node_uid = ""
        ec_channel = ""
        ec_amount_ml = 0.0
        ec_duration_ms = 0

        ph_node_uid = ""
        ph_channel = ""
        ph_amount_ml = 0.0
        ph_duration_ms = 0

        if ec_needs:
            ec_retry_after = _retry_after(
                pid_entry=_pid_entry(pid_state, "ec"),
                min_interval_sec=_positive_int(controller_ec.get("min_interval_sec"), 0),
                now=now,
            )
            if ec_retry_after is None:
                resolved_component, resolved_ec = _resolve_ec_actuator(
                    ec_actuator=ec_actuator,
                    ec_actuators=ec_actuators,
                    ec_component_policy=ec_component_policy,
                    phase_key=phase_key,
                    default_channel=str(correction_config.get("dose_ec_channel") or "ec_npk_pump"),
                )
                ec_component_name = resolved_component
                ec_node_uid = str(resolved_ec["node_uid"])
                ec_channel = str(resolved_ec["channel"])
                calibration = resolved_ec.get("calibration")
                if not isinstance(calibration, Mapping):
                    raise PlannerConfigurationError(
                        f"EC dosing pump calibration is required (channel={ec_channel}, node={ec_node_uid})"
                    )
                ec_amount_ml, ec_pid_update = _compute_amount_ml(
                    kind="ec",
                    gap=ec_gap,
                    lower_bound=ec_lo,
                    current_value=current_ec,
                    controller_cfg=controller_ec,
                    correction_config=correction_config,
                    process_cfg=process_cfg,
                    calibration=calibration,
                    solution_volume_l=solution_volume_l,
                    pid_entry=_pid_entry(pid_state, "ec"),
                    now=now,
                )
                if ec_pid_update:
                    pid_updates["ec"] = ec_pid_update
                ec_duration_ms = _dose_ml_to_ms(ec_amount_ml, calibration, correction_config)
                ec_needs = ec_duration_ms > 0
            else:
                ec_needs = False

        if ph_needs_up or ph_needs_down:
            ph_retry_after = _retry_after(
                pid_entry=_pid_entry(pid_state, "ph"),
                min_interval_sec=_positive_int(controller_ph.get("min_interval_sec"), 0),
                now=now,
            )
            if ph_retry_after is None:
                default_channel = (
                    correction_config.get("dose_ph_up_channel") if ph_needs_up
                    else correction_config.get("dose_ph_down_channel")
                ) or ("ph_base_pump" if ph_needs_up else "ph_acid_pump")
                resolved_ph = ph_up_actuator if ph_needs_up else ph_down_actuator
                if resolved_ph is None:
                    raise PlannerConfigurationError(
                        f"PH correction needed but no actuator resolved for channel={default_channel}"
                    )
                ph_node_uid = str(resolved_ph["node_uid"])
                ph_channel = str(resolved_ph["channel"])
                calibration = resolved_ph.get("calibration")
                if not isinstance(calibration, Mapping):
                    raise PlannerConfigurationError(
                        f"PH dosing pump calibration is required (channel={ph_channel}, node={ph_node_uid})"
                    )
                ph_gap = ph_up_gap if ph_needs_up else ph_down_gap
                ph_amount_ml, ph_pid_update = _compute_amount_ml(
                    kind="ph_up" if ph_needs_up else "ph_down",
                    gap=ph_gap,
                    lower_bound=ph_lo if ph_needs_up else ph_hi,
                    current_value=predicted_ph,
                    controller_cfg=controller_ph,
                    correction_config=correction_config,
                    process_cfg=process_cfg,
                    calibration=calibration,
                    solution_volume_l=solution_volume_l,
                    pid_entry=_pid_entry(pid_state, "ph"),
                    now=now,
                )
                if ph_pid_update:
                    pid_updates["ph"] = ph_pid_update
                ph_duration_ms = _dose_ml_to_ms(ph_amount_ml, calibration, correction_config)
                ph_needs_up = ph_needs_up and ph_duration_ms > 0
                ph_needs_down = ph_needs_down and ph_duration_ms > 0
            else:
                ph_needs_up = False
                ph_needs_down = False

        if ec_needs:
            # In a delayed in-flow process we must re-observe after every dose.
            # Returning EC and pH in the same tick would recreate the legacy
            # piggyback behaviour and compound transport-delay error.
            ph_needs_up = False
            ph_needs_down = False
            ph_node_uid = ""
            ph_channel = ""
            ph_amount_ml = 0.0
            ph_duration_ms = 0
            ph_retry_after = None

        retry_after = _min_positive(ec_retry_after, ph_retry_after)
        return DosePlan(
            needs_ec=ec_needs,
            ec_component=ec_component_name,
            ec_node_uid=ec_node_uid,
            ec_channel=ec_channel,
            ec_amount_ml=ec_amount_ml,
            ec_duration_ms=ec_duration_ms,
            ec_retry_after_sec=ec_retry_after,
            needs_ph_up=ph_needs_up,
            needs_ph_down=ph_needs_down,
            ph_node_uid=ph_node_uid,
            ph_channel=ph_channel,
            ph_amount_ml=ph_amount_ml,
            ph_duration_ms=ph_duration_ms,
            ph_retry_after_sec=ph_retry_after,
            retry_after_sec=retry_after,
            pid_state_updates=pid_updates,
        )


def _resolve_bounds(
    *,
    target: float,
    lower: float | None,
    upper: float | None,
    tolerance_pct: float,
) -> tuple[float, float]:
    if lower is not None and upper is not None:
        return float(lower), float(upper)
    tol = abs(float(target)) * (float(tolerance_pct) / 100.0)
    return float(target) - tol, float(target) + tol


def _phase_mapping(raw: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    return raw if isinstance(raw, Mapping) else {}


def _pid_entry(pid_state: Mapping[str, Any], kind: str) -> Mapping[str, Any]:
    entry = pid_state.get(kind)
    return entry if isinstance(entry, Mapping) else {}


def _controller_cfg(correction_config: Mapping[str, Any], kind: str) -> Mapping[str, Any]:
    controllers = correction_config.get("controllers")
    controller = controllers.get(kind) if isinstance(controllers, Mapping) else None
    if isinstance(controller, Mapping):
        return controller
    return {}


def _resolve_ec_actuator(
    *,
    ec_actuator: Optional[Mapping[str, Any]],
    ec_actuators: Optional[Mapping[str, Any]],
    ec_component_policy: Optional[Mapping[str, Any]],
    phase_key: str,
    default_channel: str,
) -> tuple[str, Mapping[str, Any]]:
    if isinstance(ec_actuator, Mapping):
        return "", ec_actuator

    if not isinstance(ec_actuators, Mapping) or not ec_actuators:
        raise PlannerConfigurationError(
            f"EC correction needed but no actuator resolved for channel={default_channel}"
        )

    phase_policy = ec_component_policy.get(phase_key) if isinstance(ec_component_policy, Mapping) else None
    phase_policy = phase_policy if isinstance(phase_policy, Mapping) else {}
    has_explicit_policy = bool(phase_policy)
    ranked: list[tuple[float, int, str, Mapping[str, Any]]] = []
    for name, actuator in ec_actuators.items():
        if not isinstance(actuator, Mapping):
            continue
        component = str(name).strip().lower()
        component = component[3:] if component.startswith("ec_") else component
        if has_explicit_policy:
            weight = float(phase_policy.get(component) or phase_policy.get(name) or 0.0)
            order_idx = 0  # explicit policy overrides default ordering
        else:
            weight = 0.0
            # Use _EC_COMPONENT_DEFAULT_ORDER for deterministic, agronomically sensible selection.
            try:
                order_idx = _EC_COMPONENT_DEFAULT_ORDER.index(component)
            except ValueError:
                order_idx = len(_EC_COMPONENT_DEFAULT_ORDER)
        ranked.append((weight, order_idx, component, actuator))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    chosen = ranked[0] if ranked else None
    if chosen is None:
        raise PlannerConfigurationError(
            f"EC correction needed but no actuator resolved for channel={default_channel}"
        )
    return chosen[2], chosen[3]


def _retry_after(
    *,
    pid_entry: Mapping[str, Any],
    min_interval_sec: int,
    now: datetime,
) -> int | None:
    if min_interval_sec <= 0:
        return None
    last_dose_at = pid_entry.get("last_dose_at")
    if not isinstance(last_dose_at, datetime):
        return None
    elapsed = (_to_utc_naive(now) - _to_utc_naive(last_dose_at)).total_seconds()
    remaining = float(min_interval_sec) - elapsed
    if remaining <= 0:
        return None
    return max(1, int(math.ceil(remaining)))


def _apply_feedforward_bias(
    *,
    current_value: float,
    pid_entry: Mapping[str, Any],
    now: datetime,
) -> float:
    hold_until = pid_entry.get("hold_until")
    if not isinstance(hold_until, datetime):
        return current_value
    if _to_utc_naive(hold_until) <= _to_utc_naive(now):
        return current_value
    if str(pid_entry.get("last_correction_kind") or "").strip().lower() != "ec":
        return current_value
    return current_value + float(pid_entry.get("feedforward_bias") or 0.0)


def _compute_amount_ml(
    *,
    kind: str,
    gap: float,
    lower_bound: float,
    current_value: float,
    controller_cfg: Mapping[str, Any],
    correction_config: Mapping[str, Any],
    process_cfg: Mapping[str, Any],
    calibration: Mapping[str, Any],
    solution_volume_l: float,
    pid_entry: Mapping[str, Any],
    now: datetime,
) -> tuple[float, Mapping[str, Any]]:
    gain = _process_gain(kind=kind, process_cfg=process_cfg)
    pid_update = _next_pid_state(
        kind=kind,
        gap=gap,
        current_value=current_value,
        controller_cfg=controller_cfg,
        pid_entry=pid_entry,
        now=now,
    )
    if gain is not None:
        output_units = (
            float(controller_cfg.get("kp") or 0.0) * gap
            + float(controller_cfg.get("ki") or 0.0) * float(pid_update["integral"])
            + float(controller_cfg.get("kd") or 0.0) * float(pid_update["prev_derivative"])
        )
        dose_ml = output_units / gain if gain > 0 else 0.0
    else:
        raise PlannerConfigurationError(
            f"Process gain is required for {kind} in observation-driven correction mode"
        )

    if gain is not None and gap > 0:
        # A single pulse must not exceed the modelled dose required to reach the
        # nearest allowed bound/target. Without this cap, kp>1 PI output can
        # command a dose that overshoots the window in one step and causes
        # acid/base ping-pong during recirculation.
        dose_ml = min(dose_ml, gap / gain)

    min_effective_ml = max(0.0, float(calibration.get("min_effective_ml") or 0.0))
    if dose_ml > 0 and min_effective_ml > 0:
        dose_ml = max(dose_ml, min_effective_ml)

    controller_max = _positive_float(controller_cfg.get("max_dose_ml"), 0.0)
    if kind == "ec":
        contract_max = _positive_float(correction_config.get("max_ec_dose_ml"), _DEFAULT_MAX_EC_DOSE_ML)
    else:
        contract_max = _positive_float(correction_config.get("max_ph_dose_ml"), _DEFAULT_MAX_PH_DOSE_ML)
    max_ml = min(controller_max, contract_max) if controller_max > 0 else contract_max
    dose_ml = min(dose_ml, max_ml)
    dose_ml = round(max(0.0, dose_ml), 4)
    if dose_ml > 0:
        pid_update = {**pid_update, "last_dose_at": now}
    return dose_ml, pid_update


def _process_gain(*, kind: str, process_cfg: Mapping[str, Any]) -> float | None:
    key = {
        "ec": "ec_gain_per_ml",
        "ph_up": "ph_up_gain_per_ml",
        "ph_down": "ph_down_gain_per_ml",
    }.get(kind)
    if key is None:
        return None
    raw = process_cfg.get(key)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _next_pid_state(
    *,
    kind: str,
    gap: float,
    current_value: float,
    controller_cfg: Mapping[str, Any],
    pid_entry: Mapping[str, Any],
    now: datetime,
) -> Mapping[str, Any]:
    now = _to_utc_naive(now)
    integral = float(pid_entry.get("integral") or 0.0)
    prev_error = float(pid_entry.get("prev_error") or 0.0)
    prev_derivative = float(pid_entry.get("prev_derivative") or 0.0)
    last_measurement_at = pid_entry.get("last_measurement_at")
    alpha = float(controller_cfg.get("derivative_filter_alpha") or 1.0)
    alpha = min(1.0, max(0.0, alpha))
    derivative = 0.0
    if isinstance(last_measurement_at, datetime):
        dt = (now - _to_utc_naive(last_measurement_at)).total_seconds()
        if dt > 0:
            integral += gap * dt
            raw_derivative = (gap - prev_error) / dt
            derivative = alpha * raw_derivative + (1.0 - alpha) * prev_derivative
    max_integral = float(controller_cfg.get("max_integral") or 0.0)
    if max_integral > 0:
        integral = max(-max_integral, min(max_integral, integral))
    return {
        "integral": round(integral, 6),
        "prev_error": round(gap, 6),
        "prev_derivative": round(derivative, 6),
        "last_measurement_at": now,
        "last_measured_value": round(current_value, 6),
        "last_correction_kind": "ec" if kind == "ec" else "ph",
    }


def _reset_pid_state_if_inside_bounds(
    *,
    current_ph: float,
    current_ec: float,
    ph_lo: float,
    ph_hi: float,
    ec_lo: float,
    ec_hi: float,
    pid_state: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if ph_lo <= current_ph <= ph_hi and "ph" in pid_state:
        updates["ph"] = {
            "integral": 0.0,
            "prev_error": 0.0,
            "prev_derivative": 0.0,
            # Reset last_measurement_at so the next out-of-bounds tick computes
            # dt from now — not from a stale pre-reset timestamp, which would
            # cause an integral spike on re-entry.
            "last_measurement_at": now,
        }
    if ec_lo <= current_ec <= ec_hi and "ec" in pid_state:
        updates["ec"] = {
            "integral": 0.0,
            "prev_error": 0.0,
            "prev_derivative": 0.0,
            "last_measurement_at": now,
        }
    return updates


def _dose_ml_to_ms(
    dose_ml: float,
    calibration: Mapping[str, Any],
    correction_config: Mapping[str, Any],
) -> int:
    pump_calibration = correction_config.get("pump_calibration")
    if not isinstance(pump_calibration, Mapping):
        raise PlannerConfigurationError(
            "pump_calibration config is missing from correction_config"
        )
    min_dose_ms = _positive_int(pump_calibration.get("min_dose_ms"), 0)
    ml_min = _positive_float(pump_calibration.get("ml_per_sec_min"), 0.0)
    ml_max = _positive_float(pump_calibration.get("ml_per_sec_max"), 0.0)
    if min_dose_ms <= 0 or ml_min <= 0 or ml_max <= 0 or ml_max < ml_min:
        raise PlannerConfigurationError(
            "pump_calibration config is invalid; expected min_dose_ms/ml_per_sec_min/ml_per_sec_max"
        )
    raw = calibration.get("ml_per_sec")
    if raw is None:
        raise PlannerConfigurationError(
            "Pump calibration is missing ml_per_sec; cannot compute dose duration"
        )
    try:
        ml_per_sec = float(raw)
    except (TypeError, ValueError):
        raise PlannerConfigurationError(
            f"Pump calibration ml_per_sec is not numeric: {raw!r}"
        )
    if ml_per_sec <= 0:
        raise PlannerConfigurationError(
            f"Pump calibration ml_per_sec must be positive, got {ml_per_sec}"
        )
    if not (ml_min <= ml_per_sec <= ml_max):
        raise PlannerConfigurationError(
            f"Pump calibration ml_per_sec={ml_per_sec} is outside the valid range "
            f"[{ml_min}, {ml_max}]; check pump calibration data"
        )
    duration_ms = int(dose_ml / ml_per_sec * 1000)
    if duration_ms <= 0:
        return 0
    if duration_ms < min_dose_ms:
        _logger.warning(
            "Dose discarded: computed duration %dms is below minimum %dms "
            "(dose_ml=%.4f, ml_per_sec=%.4f). "
            "Check pump calibration or min_effective_ml setting.",
            duration_ms,
            min_dose_ms,
            dose_ml,
            ml_per_sec,
        )
        return 0
    return duration_ms


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _positive_float(raw: Any, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _positive_int(raw: Any, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _non_negative_float(raw: Any, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


def _min_positive(*values: Optional[int]) -> Optional[int]:
    candidates = [int(value) for value in values if value is not None and int(value) > 0]
    return min(candidates) if candidates else None
