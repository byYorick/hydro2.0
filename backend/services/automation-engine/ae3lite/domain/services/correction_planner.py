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
_EC_COMPONENT_DEFAULT_ORDER: tuple[str, ...] = ("npk", "a", "b", "calcium", "magnesium", "micro", "trace")


@dataclass(frozen=True)
class EcDoseStep:
    component: str
    node_uid: str
    channel: str
    amount_ml: float
    duration_ms: int


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
    ec_dose_sequence: tuple[EcDoseStep, ...] = ()

    needs_ph_up: bool = False
    needs_ph_down: bool = False
    ph_node_uid: str = ""
    ph_channel: str = ""
    ph_amount_ml: float = 0.0
    ph_duration_ms: int = 0
    ph_retry_after_sec: Optional[int] = None

    retry_after_sec: Optional[int] = None
    dose_discarded_reason: str = ""
    dose_discarded_details: Mapping[str, Any] = field(default_factory=dict)
    deferred_action: str = ""
    deferred_reason: str = ""
    deferred_details: Mapping[str, Any] = field(default_factory=dict)
    dead_zone_details: Mapping[str, Any] = field(default_factory=dict)
    pid_state_updates: Mapping[str, Any] = field(default_factory=dict)
    ec_pid_zone: str = ""
    ph_pid_zone: str = ""
    ec_pid_coeffs: Mapping[str, Any] = field(default_factory=dict)
    ph_pid_coeffs: Mapping[str, Any] = field(default_factory=dict)

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
        pid_configs: Optional[Mapping[str, Any]] = None,
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
        pid_configs = pid_configs if isinstance(pid_configs, Mapping) else {}
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

        ec_controller_cfg, ec_pid_zone, ec_pid_coeffs = _resolve_pid_controller_cfg(
            controller_cfg=controller_ec,
            pid_configs=pid_configs,
            pid_type="ec",
            gap=ec_gap,
        )
        ph_controller_cfg, ph_pid_zone, ph_pid_coeffs = _resolve_pid_controller_cfg(
            controller_cfg=controller_ph,
            pid_configs=pid_configs,
            pid_type="ph",
            gap=max(ph_up_gap, ph_down_gap),
        )

        ec_deadband = _non_negative_float(ec_controller_cfg.get("deadband"), 0.0)
        ph_deadband = _non_negative_float(ph_controller_cfg.get("deadband"), 0.0)

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
        ec_discarded_reason = ""
        ec_discarded_details: Mapping[str, Any] = {}
        ec_dose_sequence: tuple[EcDoseStep, ...] = ()

        ph_node_uid = ""
        ph_channel = ""
        ph_amount_ml = 0.0
        ph_duration_ms = 0
        ph_discarded_reason = ""
        ph_discarded_details: Mapping[str, Any] = {}
        deferred_action = ""
        deferred_reason = ""
        deferred_details: Mapping[str, Any] = {}

        if ec_needs:
            ec_retry_after = _retry_after(
                pid_entry=_pid_entry(pid_state, "ec"),
                min_interval_sec=_positive_int(controller_ec.get("min_interval_sec"), 0),
                now=now,
            )
            if ec_retry_after is None:
                ec_dosing_mode = str(correction_config.get("ec_dosing_mode") or "single").strip().lower() or "single"
                excluded = correction_config.get("ec_excluded_components") or ()
                excluded_set = {str(x).strip().lower() for x in excluded if str(x).strip()}
                multi_fail_closed = (
                    ec_dosing_mode == "multi_sequential"
                    and "npk" in excluded_set
                    and str(workflow_phase).strip().lower() == "irrigating"
                )
                if ec_dosing_mode == "multi_sequential" and isinstance(ec_actuators, Mapping):
                    ec_pid_entry = _pid_entry(pid_state, "ec")
                    ec_pid_update = _next_pid_state(
                        kind="ec",
                        gap=ec_gap,
                        current_value=current_ec,
                        controller_cfg=ec_controller_cfg,
                        pid_entry=ec_pid_entry,
                        now=now,
                    )
                    output_units = (
                        float(ec_controller_cfg.get("kp") or 0.0) * ec_gap
                        + float(ec_controller_cfg.get("ki") or 0.0) * float(ec_pid_update["integral"])
                        + float(ec_controller_cfg.get("kd") or 0.0) * float(ec_pid_update["prev_derivative"])
                    )

                    ratios_raw = correction_config.get("ec_component_ratios")
                    ratios_raw = ratios_raw if isinstance(ratios_raw, Mapping) else {}

                    active: dict[str, float] = {}
                    for k, v in ratios_raw.items():
                        name = str(k).strip().lower()
                        if not name or name in excluded_set:
                            continue
                        try:
                            weight = float(v)
                        except (TypeError, ValueError):
                            continue
                        if weight <= 0:
                            continue
                        active[name] = weight
                    active_sum = sum(active.values())
                    if multi_fail_closed and str(workflow_phase).strip().lower() == "irrigating" and active_sum <= 0:
                        raise PlannerConfigurationError(
                            "EC multi_sequential excludes NPK but no active EC components are configured"
                        )

                    if active_sum > 0:
                        preferred_order = ("calcium", "magnesium", "micro")
                        components = sorted(
                            active.keys(),
                            key=lambda c: (preferred_order.index(c) if c in preferred_order else 999, c),
                        )

                        seq: list[EcDoseStep] = []
                        discarded: list[dict[str, Any]] = []
                        total_ml = 0.0
                        total_ms = 0
                        contract_max = _positive_float(
                            correction_config.get("max_ec_dose_ml"), _DEFAULT_MAX_EC_DOSE_ML
                        )
                        controller_max = _positive_float(ec_controller_cfg.get("max_dose_ml"), 0.0)
                        max_ml = min(controller_max, contract_max) if controller_max > 0 else contract_max

                        for component in components:
                            ratio = float(active.get(component) or 0.0)
                            if ratio <= 0:
                                continue
                            active_ratio = ratio / active_sum
                            component_gap = ec_gap * active_ratio

                            resolved_ec = _find_ec_component_actuator(
                                ec_actuators=ec_actuators,
                                component=component,
                            )
                            if resolved_ec is None:
                                discarded.append({"component": component, "reason": "actuator_missing"})
                                continue

                            node_uid = str(resolved_ec["node_uid"])
                            channel = str(resolved_ec["channel"])
                            calibration = resolved_ec.get("calibration")
                            if not isinstance(calibration, Mapping):
                                raise PlannerConfigurationError(
                                    f"EC dosing pump calibration is required (channel={channel}, node={node_uid})"
                                )

                            gain = _ec_component_process_gain(
                                component=component,
                                process_cfg=process_cfg,
                                pid_entry=ec_pid_entry,
                                phase_key=phase_key,
                            )
                            if gain is None or gain <= 0:
                                raise PlannerConfigurationError(
                                    f"Process gain is required for ec component {component} in multi_sequential mode"
                                )

                            dose_ml = output_units * active_ratio / gain
                            dose_ml = min(dose_ml, component_gap / gain if component_gap > 0 else 0.0)
                            dose_ml = min(dose_ml, max_ml * active_ratio)

                            min_effective_ml = max(0.0, float(calibration.get("min_effective_ml") or 0.0))
                            if dose_ml > 0 and min_effective_ml > 0:
                                dose_ml = max(dose_ml, min_effective_ml)
                                # Re-apply caps after min_effective bump to avoid exceeding PID/contract limits.
                                dose_ml = min(dose_ml, component_gap / gain if component_gap > 0 else 0.0)
                                dose_ml = min(dose_ml, max_ml * active_ratio)
                                if dose_ml > 0 and dose_ml < min_effective_ml:
                                    discarded.append(
                                        {
                                            "component": component,
                                            "reason": "ec_min_effective_exceeds_caps",
                                            "node_uid": node_uid,
                                            "channel": channel,
                                            "min_effective_ml": min_effective_ml,
                                            "capped_ml": round(float(dose_ml), 4),
                                        }
                                    )
                                    continue
                            dose_ml = round(max(0.0, dose_ml), 4)

                            duration_ms, reason, details = _dose_ml_to_ms(dose_ml, calibration, correction_config)
                            if duration_ms <= 0 and dose_ml > 0:
                                discarded.append(
                                    {
                                        "component": component,
                                        "reason": reason or "ec_pulse_too_short",
                                        "node_uid": node_uid,
                                        "channel": channel,
                                        "amount_ml": dose_ml,
                                        **dict(details or {}),
                                    }
                                )
                                continue
                            if dose_ml <= 0 or duration_ms <= 0:
                                continue

                            seq.append(
                                EcDoseStep(
                                    component=component,
                                    node_uid=node_uid,
                                    channel=channel,
                                    amount_ml=dose_ml,
                                    duration_ms=int(duration_ms),
                                )
                            )
                            total_ml += dose_ml
                            total_ms += int(duration_ms)

                        if seq:
                            ec_component_name = "multi_sequential"
                            ec_dose_sequence = tuple(seq)
                            ec_node_uid = seq[0].node_uid
                            ec_channel = seq[0].channel
                            ec_amount_ml = round(total_ml, 4)
                            ec_duration_ms = int(total_ms)
                            if ec_pid_update:
                                if ec_pid_zone:
                                    ec_pid_update = {**ec_pid_update, "current_zone": ec_pid_zone}
                                pid_updates["ec"] = {**ec_pid_update, "last_dose_at": now}
                            ec_discarded_reason = "multi_component_partial" if discarded else ""
                            ec_discarded_details = {"discarded": discarded} if discarded else {}
                            ec_needs = ec_duration_ms > 0
                        else:
                            ec_discarded_reason = "ec_multi_component_no_effective_pulses"
                            ec_discarded_details = {"discarded": discarded}
                            ec_needs = False

                # Fail-closed: if multi_sequential is enabled and NPK is excluded during irrigation,
                # do NOT fallback to single-dose (which would default to ec_npk_pump).
                if multi_fail_closed and not ec_dose_sequence:
                    discarded = ()
                    if isinstance(ec_discarded_details, Mapping):
                        raw_discarded = ec_discarded_details.get("discarded")
                        if isinstance(raw_discarded, list):
                            discarded = tuple(
                                str(item.get("component") or "").strip().lower()
                                for item in raw_discarded
                                if isinstance(item, Mapping)
                            )
                    discarded_components = ", ".join(sorted({name for name in discarded if name})) or "none"
                    raise PlannerConfigurationError(
                        "EC multi_sequential produced no safe non-NPK doses during irrigation "
                        f"(discarded={discarded_components})"
                    )
                if not ec_dose_sequence and not multi_fail_closed:
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
                        controller_cfg=ec_controller_cfg,
                        correction_config=correction_config,
                        process_cfg=process_cfg,
                        phase_key=phase_key,
                        calibration=calibration,
                        solution_volume_l=solution_volume_l,
                        pid_entry=_pid_entry(pid_state, "ec"),
                        now=now,
                    )
                    if ec_pid_update:
                        if ec_pid_zone:
                            ec_pid_update = {**ec_pid_update, "current_zone": ec_pid_zone}
                        pid_updates["ec"] = ec_pid_update
                    ec_duration_ms, ec_discarded_reason, ec_discarded_details = _dose_ml_to_ms(
                        ec_amount_ml, calibration, correction_config,
                    )
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
                    controller_cfg=ph_controller_cfg,
                    correction_config=correction_config,
                    process_cfg=process_cfg,
                    phase_key=phase_key,
                    calibration=calibration,
                    solution_volume_l=solution_volume_l,
                    pid_entry=_pid_entry(pid_state, "ph"),
                    now=now,
                )
                if ph_pid_update:
                    if ph_pid_zone:
                        ph_pid_update = {**ph_pid_update, "current_zone": ph_pid_zone}
                    pid_updates["ph"] = ph_pid_update
                ph_duration_ms, ph_discarded_reason, ph_discarded_details = _dose_ml_to_ms(
                    ph_amount_ml, calibration, correction_config,
                )
                ph_needs_up = ph_needs_up and ph_duration_ms > 0
                ph_needs_down = ph_needs_down and ph_duration_ms > 0
            else:
                ph_needs_up = False
                ph_needs_down = False

        retry_after = _min_positive(ec_retry_after, ph_retry_after)
        dead_zone_details = {
            "ec_gap": round(ec_gap, 6),
            "ec_deadband": round(ec_deadband, 6),
            "ec_pid_zone": ec_pid_zone or None,
            "ph_up_gap": round(ph_up_gap, 6),
            "ph_down_gap": round(ph_down_gap, 6),
            "ph_deadband": round(ph_deadband, 6),
            "ph_pid_zone": ph_pid_zone or None,
            "ph_has_explicit_window": ph_has_explicit_window,
            "ec_has_explicit_window": ec_has_explicit_window,
        }
        return DosePlan(
            needs_ec=ec_needs,
            ec_component=ec_component_name,
            ec_node_uid=ec_node_uid,
            ec_channel=ec_channel,
            ec_amount_ml=ec_amount_ml,
            ec_duration_ms=ec_duration_ms,
            ec_retry_after_sec=ec_retry_after,
            ec_dose_sequence=ec_dose_sequence,
            needs_ph_up=ph_needs_up,
            needs_ph_down=ph_needs_down,
            ph_node_uid=ph_node_uid,
            ph_channel=ph_channel,
            ph_amount_ml=ph_amount_ml,
            ph_duration_ms=ph_duration_ms,
            ph_retry_after_sec=ph_retry_after,
            retry_after_sec=retry_after,
            dose_discarded_reason=ec_discarded_reason or ph_discarded_reason,
            dose_discarded_details=ec_discarded_details or ph_discarded_details,
            deferred_action=deferred_action,
            deferred_reason=deferred_reason,
            deferred_details=deferred_details,
            dead_zone_details=dead_zone_details,
            pid_state_updates=pid_updates,
            ec_pid_zone=ec_pid_zone,
            ph_pid_zone=ph_pid_zone,
            ec_pid_coeffs=ec_pid_coeffs,
            ph_pid_coeffs=ph_pid_coeffs,
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


def _resolve_pid_controller_cfg(
    *,
    controller_cfg: Mapping[str, Any],
    pid_configs: Mapping[str, Any],
    pid_type: str,
    gap: float,
) -> tuple[Mapping[str, Any], str, Mapping[str, Any]]:
    entry = pid_configs.get(pid_type)
    pid_cfg = entry.get("config") if isinstance(entry, Mapping) else None
    if not isinstance(pid_cfg, Mapping):
        return controller_cfg, "", {}

    zone_coeffs = pid_cfg.get("zone_coeffs")
    if not isinstance(zone_coeffs, Mapping):
        return _merge_pid_deadband(controller_cfg=controller_cfg, pid_cfg=pid_cfg), "", {}

    close_zone = _non_negative_float(pid_cfg.get("close_zone"), 0.0)
    far_zone = _non_negative_float(pid_cfg.get("far_zone"), 0.0)
    zone_name = "close" if gap <= close_zone or far_zone <= close_zone else "far"
    coeffs = zone_coeffs.get(zone_name)
    if not isinstance(coeffs, Mapping):
        return _merge_pid_deadband(controller_cfg=controller_cfg, pid_cfg=pid_cfg), "", {}

    merged = dict(_merge_pid_deadband(controller_cfg=controller_cfg, pid_cfg=pid_cfg))
    selected_coeffs: dict[str, float] = {}
    for key in ("kp", "ki", "kd"):
        value = coeffs.get(key)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        merged[key] = numeric
        selected_coeffs[key] = numeric
    return merged, zone_name, selected_coeffs


def _merge_pid_deadband(*, controller_cfg: Mapping[str, Any], pid_cfg: Mapping[str, Any]) -> Mapping[str, Any]:
    merged = dict(controller_cfg)
    dead_zone = pid_cfg.get("dead_zone")
    try:
        deadband = float(dead_zone)
    except (TypeError, ValueError):
        return merged
    if deadband >= 0:
        merged["deadband"] = deadband
    return merged


def _find_ec_component_actuator(
    *,
    ec_actuators: Mapping[str, Any],
    component: str,
) -> Mapping[str, Any] | None:
    """Best-effort lookup of an EC component actuator by normalized name."""
    want = str(component).strip().lower()
    if not want:
        return None
    direct = ec_actuators.get(want)
    if isinstance(direct, Mapping):
        return direct
    alt = ec_actuators.get(f"ec_{want}")
    if isinstance(alt, Mapping):
        return alt
    for name, actuator in ec_actuators.items():
        if not isinstance(actuator, Mapping):
            continue
        key = str(name).strip().lower()
        key = key[3:] if key.startswith("ec_") else key
        if key == want:
            return actuator
    return None


def _ec_component_process_gain(
    *,
    component: str,
    process_cfg: Mapping[str, Any],
    pid_entry: Mapping[str, Any],
    phase_key: str,
) -> float | None:
    """Resolve per-component EC gain, falling back to generic ec_gain_per_ml."""
    gains = process_cfg.get("ec_component_gains")
    gains = gains if isinstance(gains, Mapping) else {}
    entry = gains.get(component) if isinstance(gains.get(component), Mapping) else None
    if isinstance(entry, Mapping):
        raw = entry.get("ec_gain_per_ml")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            # Do not apply adaptive EMA here yet; keep per-component gains authoritative.
            return value
    return _process_gain(kind="ec", process_cfg=process_cfg, pid_entry=pid_entry, phase_key=phase_key)


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
    phase_key: str,
    calibration: Mapping[str, Any],
    solution_volume_l: float,
    pid_entry: Mapping[str, Any],
    now: datetime,
) -> tuple[float, Mapping[str, Any]]:
    gain = _process_gain(kind=kind, process_cfg=process_cfg, pid_entry=pid_entry, phase_key=phase_key)
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


def _process_gain(
    *,
    kind: str,
    process_cfg: Mapping[str, Any],
    pid_entry: Mapping[str, Any],
    phase_key: str,
) -> float | None:
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
    if value <= 0:
        return None

    stats = pid_entry.get("stats") if isinstance(pid_entry.get("stats"), Mapping) else {}
    adaptive = stats.get("adaptive") if isinstance(stats.get("adaptive"), Mapping) else {}
    gains = adaptive.get("gains") if isinstance(adaptive.get("gains"), Mapping) else {}
    learned_entry = gains.get(key) if isinstance(gains.get(key), Mapping) else {}

    try:
        learned_gain = float(learned_entry.get("ema"))
    except (TypeError, ValueError):
        learned_gain = 0.0
    try:
        observations = int(learned_entry.get("observations") or 0)
    except (TypeError, ValueError):
        observations = 0
    if learned_gain <= 0 or observations <= 0:
        return value

    retention_ema = _coerce_ratio(adaptive.get("retention_ema"))
    wave_score_ema = _coerce_ratio(adaptive.get("wave_score_ema"))
    weight = min(1.0, observations / 6.0)
    if retention_ema is not None:
        weight *= max(0.25, retention_ema)
    if wave_score_ema is not None:
        weight *= max(0.35, 1.0 - min(0.65, wave_score_ema))
    effective = value * (1.0 - weight) + learned_gain * weight
    if phase_key == "tank_recirc" and kind == "ec":
        # Recirculation must stay conservative: learned EC gain may only
        # increase confidence, but it must not reduce the authoritative
        # process-calibration gain and inflate the next pulse.
        effective = max(value, effective)
    return max(value * 0.25, min(value * 4.0, effective))


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
            "current_zone": "dead",
        }
    if ec_lo <= current_ec <= ec_hi and "ec" in pid_state:
        updates["ec"] = {
            "integral": 0.0,
            "prev_error": 0.0,
            "prev_derivative": 0.0,
            "last_measurement_at": now,
            "current_zone": "dead",
        }
    return updates


def _dose_ml_to_ms(
    dose_ml: float,
    calibration: Mapping[str, Any],
    correction_config: Mapping[str, Any],
) -> tuple[int, str, Mapping[str, Any]]:
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
        return (0, "", {})
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
        return (
            0,
            "below_min_dose_ms",
            {
                "computed_duration_ms": duration_ms,
                "min_dose_ms": min_dose_ms,
                "dose_ml": round(dose_ml, 4),
                "ml_per_sec": ml_per_sec,
            },
        )
    return (duration_ms, "", {})


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


def _coerce_ratio(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return max(0.0, min(1.0, value))
