"""Чистый доменный сервис планирования доз коррекции для AE3-Lite."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
import math
from typing import Any, Mapping, Optional

from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.phase_utils import normalize_phase_key

_logger = logging.getLogger(__name__)

# ── Значения по умолчанию для расчёта доз (5.1: именованные константы вместо magic numbers) ──

#: Объём бака раствора по умолчанию, если он не задан в correction_config.
_DEFAULT_SOLUTION_VOLUME_L: float = 100.0

#: Жёсткий верхний предел для одной EC-дозы, если correction_config.max_ec_dose_ml отсутствует.
_DEFAULT_MAX_EC_DOSE_ML: float = 50.0

#: Жёсткий верхний предел для одной pH-дозы, если correction_config.max_ph_dose_ml отсутствует.
_DEFAULT_MAX_PH_DOSE_ML: float = 20.0

# ── Порядок fallback-выбора EC-компонентов (5.3) ──────────────────────────────

#: Предпочтительный порядок EC-компонентов, когда ec_component_policy не настроен.
#: Компоненты вне этого списка добавляются после перечисленных в алфавитном порядке.
_EC_COMPONENT_DEFAULT_ORDER: tuple[str, ...] = ("npk", "a", "b", "calcium", "magnesium", "micro", "trace")
_EC_COMPONENT_LEGACY_ALIAS_MAP: dict[str, str] = {
    "a": "npk",
    "b": "calcium",
    "c": "magnesium",
    "d": "micro",
}


@dataclass(frozen=True)
class EcDoseStep:
    component: str
    node_uid: str
    channel: str
    amount_ml: float
    duration_ms: int


@dataclass(frozen=True)
class DosePlan:
    """Разрешённые действия коррекции для текущего snapshot измерений."""

    needs_ec: bool = False
    ec_component: str = ""
    ec_node_uid: str = ""
    ec_channel: str = ""
    ec_amount_ml: float = 0.0
    ec_duration_ms: int = 0
    ec_retry_after_sec: Optional[int] = None
    ec_dose_sequence: tuple[EcDoseStep, ...] = ()
    ec_dosing_mode: str = "single"

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
    """Доменный planner импульсов дозирования EC/pH."""

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
        # Correction success is defined by proximity to the canonical target.
        # Explicit min/max windows are recipe bounds and observability metadata,
        # not an early-success shortcut at the lower edge of the window.
        ph_lo, ph_hi = _resolve_target_tolerance_bounds(
            target=target_ph,
            tolerance_pct=ph_tolerance_pct,
        )
        ec_lo, ec_hi = _resolve_target_tolerance_bounds(
            target=target_ec,
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

        ph_lo, ph_hi = _resolve_target_tolerance_bounds(
            target=target_ph,
            tolerance_pct=ph_tolerance_pct,
        )
        ec_lo, ec_hi = _resolve_target_tolerance_bounds(
            target=target_ec,
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

        # Audit B4 fix: a single pH controller serves both ph_up and ph_down
        # directions via ``max(0, target-current)`` / ``max(0, current-target)``
        # gaps. Without an explicit reset on direction switch, integral
        # accumulated while chasing ph_up would linger and distort the first
        # ph_down dose after an overshoot (and vice versa). We detect the
        # direction switch by comparing the last measured pH against the
        # current one across the target setpoint and reset the integrator.
        # If ``_reset_pid_state_if_inside_bounds`` already scheduled a ph
        # reset (inside tolerance window), its keys are kept — both resets
        # converge on the same zeroed state.
        #
        # Crucially we ALSO patch the local ``pid_state`` view so the
        # downstream ``_next_pid_state`` call consumed by ``_compute_amount_ml``
        # starts from the zeroed integral; otherwise the reset would only
        # land in the persisted update dict but the current tick's dose
        # computation would still see the stale integrator value.
        if "ph" not in pid_updates:
            ph_switch_updates = _reset_pid_state_if_ph_direction_switched(
                predicted_ph=predicted_ph,
                target_ph=target_ph,
                pid_state=pid_state,
                now=now,
            )
            if ph_switch_updates:
                pid_updates.update(ph_switch_updates)
                pid_state = {
                    **pid_state,
                    "ph": {
                        **(pid_state.get("ph") if isinstance(pid_state.get("ph"), Mapping) else {}),
                        **ph_switch_updates["ph"],
                    },
                }

        controller_ec = _controller_cfg(correction_config, "ec")
        controller_ph = _controller_cfg(correction_config, "ph")
        solution_volume_l = _positive_float(correction_config.get("solution_volume_l"), _DEFAULT_SOLUTION_VOLUME_L)

        ec_gap = max(0.0, target_ec - current_ec)
        ph_up_gap = max(0.0, target_ph - predicted_ph)
        ph_down_gap = max(0.0, predicted_ph - target_ph)

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

        ec_needs = ec_gap > ec_deadband
        ph_needs_up = ph_up_gap > ph_deadband
        ph_needs_down = ph_down_gap > ph_deadband

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
                # Используем нормализованный phase_key (irrigating|irrigation|irrig_recirc → irrigation),
                # а не сырой workflow_phase, чтобы fail-closed логика совпадала с normalize_phase_key
                # и мы не откатывались к NPK из-за опечатки.
                is_multi = ec_dosing_mode in ("multi_sequential", "multi_parallel")
                multi_fail_closed = (
                    is_multi
                    and "npk" in excluded_set
                    and phase_key == "irrigation"
                )
                if is_multi and isinstance(ec_actuators, Mapping):
                    # В режиме multi_parallel все компоненты дозируются
                    # одновременно. Если два компонента указывают на один
                    # (node_uid, channel), pump получит суперпозицию команд
                    # и распределение потока между компонентами будет
                    # непредсказуемым → неверные дозы. Fail-closed на такой
                    # конфиг (для sequential режима проблемы нет — насосы
                    # работают по очереди).
                    if ec_dosing_mode == "multi_parallel":
                        _assert_distinct_parallel_actuators(ec_actuators)
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
                    if multi_fail_closed and active_sum <= 0:
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
                                    f"Для насоса дозирования EC требуется calibration (channel={channel}, node={node_uid})"
                                )

                            gain = _ec_component_process_gain(
                                component=component,
                                process_cfg=process_cfg,
                                pid_entry=ec_pid_entry,
                                phase_key=phase_key,
                            )
                            if gain is None or gain <= 0:
                                raise PlannerConfigurationError(
                                    f"Для ec component {component} в режиме multi_sequential требуется process gain"
                                )

                            dose_ml = output_units * active_ratio / gain
                            dose_ml = min(dose_ml, component_gap / gain if component_gap > 0 else 0.0)
                            dose_ml = min(dose_ml, max_ml * active_ratio)

                            min_effective_ml = max(0.0, float(calibration.get("min_effective_ml") or 0.0))
                            if dose_ml > 0 and min_effective_ml > 0:
                                dose_ml = max(dose_ml, min_effective_ml)
                                # Повторно применить ограничения после min_effective bump,
                                # чтобы не превысить лимиты PID/контракта.
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
                            ec_component_name = ec_dosing_mode
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

                # Fail-closed: если включён multi_sequential и NPK исключён во время полива,
                # нельзя откатываться к single-dose, который по умолчанию выберет ec_npk_pump.
                if multi_fail_closed and not ec_dose_sequence:
                    discarded_names = ()
                    if isinstance(ec_discarded_details, Mapping):
                        raw_discarded = ec_discarded_details.get("discarded")
                        if isinstance(raw_discarded, list):
                            discarded_names = tuple(
                                str(item.get("component") or "").strip().lower()
                                for item in raw_discarded
                                if isinstance(item, Mapping)
                            )
                    discarded_components = ", ".join(sorted({name for name in discarded_names if name})) or "none"
                    raise PlannerConfigurationError(
                        f"EC {ec_dosing_mode} produced no safe non-NPK doses during irrigation "
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
                            f"Для насоса дозирования EC требуется calibration (channel={ec_channel}, node={ec_node_uid})"
                        )
                    (
                        ec_amount_ml,
                        ec_pid_update,
                        ec_planner_discard_reason,
                        ec_planner_discard_details,
                    ) = _compute_amount_ml(
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
                    ec_duration_ms, ec_duration_reason, ec_duration_details = _dose_ml_to_ms(
                        ec_amount_ml, calibration, correction_config,
                    )
                    # Planner-level discard (min_effective exceeds gap cap) takes precedence
                    # over duration-level discard so the reason reflects the root cause.
                    if ec_planner_discard_reason:
                        ec_discarded_reason = ec_planner_discard_reason
                        ec_discarded_details = ec_planner_discard_details
                    else:
                        ec_discarded_reason = ec_duration_reason
                        ec_discarded_details = ec_duration_details
                    ec_needs = ec_duration_ms > 0
                    # Phantom-dose guard: _compute_amount_ml stamps last_dose_at=now
                    # as soon as dose_ml > 0, but _dose_ml_to_ms may still reject the
                    # pulse (e.g. computed duration below pump min_dose_ms). Leaving
                    # the phantom last_dose_at would trigger min_interval_sec cooldown
                    # on a dose that was never actually commanded and silently starve
                    # correction until the cooldown elapses.
                    if not ec_needs:
                        _strip_last_dose_at(pid_updates, "ec")
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
                        f"Для насоса дозирования PH требуется calibration (channel={ph_channel}, node={ph_node_uid})"
                    )
                ph_gap = ph_up_gap if ph_needs_up else ph_down_gap
                (
                    ph_amount_ml,
                    ph_pid_update,
                    ph_planner_discard_reason,
                    ph_planner_discard_details,
                ) = _compute_amount_ml(
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
                ph_duration_ms, ph_duration_reason, ph_duration_details = _dose_ml_to_ms(
                    ph_amount_ml, calibration, correction_config,
                )
                if ph_planner_discard_reason:
                    ph_discarded_reason = ph_planner_discard_reason
                    ph_discarded_details = ph_planner_discard_details
                else:
                    ph_discarded_reason = ph_duration_reason
                    ph_discarded_details = ph_duration_details
                ph_needs_up = ph_needs_up and ph_duration_ms > 0
                ph_needs_down = ph_needs_down and ph_duration_ms > 0
                # Phantom-dose guard: same rationale as for EC — if the dose was
                # rejected by _dose_ml_to_ms (below min_dose_ms) drop last_dose_at
                # so min_interval_sec cooldown is not triggered on a phantom pulse.
                if not (ph_needs_up or ph_needs_down):
                    _strip_last_dose_at(pid_updates, "ph")
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
            ec_dosing_mode=ec_dosing_mode if ec_dose_sequence else "single",
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


def _resolve_target_tolerance_bounds(
    *,
    target: float,
    tolerance_pct: float,
) -> tuple[float, float]:
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


def _assert_distinct_parallel_actuators(ec_actuators: Mapping[str, Any]) -> None:
    """Fail-closed: в multi_parallel каждый компонент должен быть на своём канале.

    Если два компонента (calcium/magnesium/micro/npk) делят один (node_uid,
    channel), parallel-команды для них вызовут суперпозицию на pump'е —
    реальный поток распределится непредсказуемо → неверные дозы. В
    sequential режиме это допустимо (насосы работают по очереди).
    """
    seen: dict[tuple[str, str], tuple[str, str]] = {}
    for name, actuator in ec_actuators.items():
        if not isinstance(actuator, Mapping):
            continue
        node_uid = str(actuator.get("node_uid") or "").strip().lower()
        channel = str(actuator.get("channel") or "").strip().lower()
        if not node_uid or not channel:
            continue
        identity = _ec_actuator_identity(name=name, actuator=actuator)
        key = (node_uid, channel)
        if key in seen:
            seen_identity, seen_name = seen[key]
            if identity == seen_identity:
                continue
            raise PlannerConfigurationError(
                f"multi_parallel ec dosing requires distinct (node_uid, channel) per "
                f"component, but '{name}' and '{seen_name}' share ({node_uid}, {channel})"
            )
        seen[key] = (identity, str(name))


def _ec_actuator_identity(*, name: str, actuator: Mapping[str, Any]) -> str:
    calibration = actuator.get("calibration")
    component = ""
    if isinstance(calibration, Mapping):
        component = _normalize_ec_component_alias(calibration.get("component"))
    if component:
        return component
    return _normalize_ec_component_alias(name) or str(name).strip().lower()


def _normalize_ec_component_alias(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return ""
    if value.startswith("ec_"):
        return _normalize_ec_component_alias(value.removeprefix("ec_").removesuffix("_pump"))
    if value.startswith("dose_ec_"):
        suffix = value.removeprefix("dose_ec_")
        return _EC_COMPONENT_LEGACY_ALIAS_MAP.get(suffix, _normalize_ec_component_alias(suffix))
    if value.startswith("pump_"):
        suffix = value.removeprefix("pump_")
        return _EC_COMPONENT_LEGACY_ALIAS_MAP.get(suffix, value)
    return _EC_COMPONENT_LEGACY_ALIAS_MAP.get(value, value)


def _find_ec_component_actuator(
    *,
    ec_actuators: Mapping[str, Any],
    component: str,
) -> Mapping[str, Any] | None:
    """Пытается найти actuator EC-компонента по нормализованному имени."""
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
    """Разрешает EC-gain для конкретного компонента с fallback на общий `ec_gain_per_ml`."""
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
            # Пока не применяем adaptive EMA: per-component gain остаётся авторитетным.
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
            # Использовать _EC_COMPONENT_DEFAULT_ORDER для детерминированного
            # и агрономически осмысленного выбора.
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
    """Shift current pH prediction by the EC→pH cross-coupling bias, if active.

    Audit B5 simplification: previously the predicate also required
    ``last_correction_kind == "ec"`` in the pH pid_state row — a semantic
    overload of a field that otherwise stored the last pH correction side
    ("ph_up"/"ph_down"). That check is now redundant: the bias is authored
    *only* by ``_run_dose_ec`` (which sets ``feedforward_bias + hold_until``)
    and cleared by the EC observe step and by ``_run_dose_ph`` (explicit
    zero-out). So the single source of truth for "bias active?" is
    ``feedforward_bias != 0 AND hold_until > now``.
    """
    hold_until = pid_entry.get("hold_until")
    if not isinstance(hold_until, datetime):
        return current_value
    if _to_utc_naive(hold_until) <= _to_utc_naive(now):
        return current_value
    bias = float(pid_entry.get("feedforward_bias") or 0.0)
    if bias == 0.0:
        return current_value
    return current_value + bias


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
) -> tuple[float, Mapping[str, Any], str, Mapping[str, Any]]:
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
            f"Для {kind} в режиме observation-driven correction требуется process gain"
        )

    if gain is not None and gap > 0:
        # A single pulse must not exceed the modelled dose required to reach the
        # nearest allowed bound/target. Without this cap, kp>1 PI output can
        # command a dose that overshoots the window in one step and causes
        # acid/base ping-pong during recirculation.
        dose_ml = min(dose_ml, gap / gain)

    gap_cap_ml = (gap / gain) if (gain is not None and gain > 0 and gap > 0) else None
    min_effective_ml = max(0.0, float(calibration.get("min_effective_ml") or 0.0))
    discard_reason = ""
    discard_details: Mapping[str, Any] = {}
    if dose_ml > 0 and min_effective_ml > 0:
        dose_ml = max(dose_ml, min_effective_ml)
        # Symmetric safety: re-apply gap/gain cap so the min_effective_ml bump
        # cannot push a single pulse past the target window. Mirrors the
        # multi_sequential branch; without it, single-dose could overshoot and
        # cause ping-pong around the setpoint.
        if gap_cap_ml is not None:
            dose_ml = min(dose_ml, gap_cap_ml)
        if dose_ml > 0 and dose_ml < min_effective_ml:
            discard_reason = f"{kind}_min_effective_exceeds_cap"
            discard_details = {
                "kind": kind,
                "min_effective_ml": round(min_effective_ml, 6),
                "gap_cap_ml": round(gap_cap_ml, 6) if gap_cap_ml is not None else None,
                "capped_ml": round(float(dose_ml), 6),
            }
            dose_ml = 0.0

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
    return dose_ml, pid_update, discard_reason, discard_details


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
        # В recirculation режим должен оставаться консервативным:
        # learned EC gain может повышать уверенность, но не должен уменьшать
        # авторитетный gain из process calibration и раздувать следующий импульс.
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
            # Сбросить last_measurement_at, чтобы следующий out-of-bounds tick
            # считал dt от текущего момента, а не от устаревшей отметки времени,
            # иначе при повторном входе можно получить всплеск интеграла.
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


def _reset_pid_state_if_ph_direction_switched(
    *,
    predicted_ph: float,
    target_ph: float,
    pid_state: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Reset pH integral when the PID crosses its target into the opposite direction.

    Audit fix (B4): a single ``pid_state["ph"]`` row serves both ph_up and
    ph_down directions via non-negative gaps. The integrator accumulates
    ``gap * dt`` regardless of which direction owns the gap, so residual
    integral from chasing ph_up would linger after an overshoot and cause
    the first ph_down dose to be skewed (and symmetrically for down→up).

    Detection: we compare the previous ``last_measured_value`` against the
    current predicted pH, both expressed as signed offset from the target
    (``value - target``). A sign flip means the controller crossed the
    setpoint and is now in the opposite-direction regime — reset.

    Returns an empty dict when the row is absent, the last measurement is
    unknown, one side is exactly at the setpoint, or the direction did not
    change. Caller merges the result into ``pid_updates`` *after*
    ``_reset_pid_state_if_inside_bounds`` so the inside-bounds branch keeps
    priority (it leads to the same zeroed state).
    """
    ph_entry = pid_state.get("ph") if isinstance(pid_state.get("ph"), Mapping) else None
    if not ph_entry:
        return {}
    last_measured = ph_entry.get("last_measured_value")
    if last_measured is None:
        return {}
    try:
        prev_signed = float(last_measured) - float(target_ph)
        curr_signed = float(predicted_ph) - float(target_ph)
    except (TypeError, ValueError):
        return {}
    # Sign flip strictly required: same-sign or at-setpoint → no switch.
    if prev_signed * curr_signed >= 0:
        return {}
    return {
        "ph": {
            "integral": 0.0,
            "prev_error": 0.0,
            "prev_derivative": 0.0,
            "last_measurement_at": now,
            "current_zone": "direction_switch",
        }
    }


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
    # Hard-cap на максимальную длительность одной дозы. Защищает от runaway
    # pump при ненормально медленной калибровке (ml_per_sec близко к нулю) или
    # вне-граничных dose_ml. Источник cap: pump_calibration.max_dose_ms либо
    # дефолт 300_000 мс (5 минут — соответствует sanity guard history-logger
    # `_MAX_DURATION_MS_SANITY`). Для зон с медленными насосами/большими дозами
    # (solution_fill, tank_recirc) можно задать явно больший cap в
    # pump_calibration.max_dose_ms.
    max_dose_ms = _positive_int(pump_calibration.get("max_dose_ms"), 300_000)
    if min_dose_ms <= 0 or ml_min <= 0 or ml_max <= 0 or ml_max < ml_min:
        raise PlannerConfigurationError(
            "pump_calibration config is invalid; expected min_dose_ms/ml_per_sec_min/ml_per_sec_max"
        )
    if max_dose_ms <= 0 or max_dose_ms < min_dose_ms:
        raise PlannerConfigurationError(
            f"pump_calibration.max_dose_ms={max_dose_ms} must be positive and >= min_dose_ms={min_dose_ms}"
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
    if duration_ms > max_dose_ms:
        # Runaway-guard: clamp на max_dose_ms, но сохраняем информацию об
        # исходной требуемой длительности для observability. Дальнейший dose
        # tuning (снизить dose_ml) сделает следующая итерация коррекции по
        # измерениям — мы не пропускаем ход, просто предотвращаем одноразовый
        # рейд насоса на часы.
        _logger.warning(
            "Dose duration clamped to max_dose_ms: computed %dms > max %dms "
            "(dose_ml=%.4f, ml_per_sec=%.4f). Possible calibration drift or "
            "oversized dose command.",
            duration_ms,
            max_dose_ms,
            dose_ml,
            ml_per_sec,
        )
        return (
            max_dose_ms,
            "clamped_to_max_dose_ms",
            {
                "computed_duration_ms": duration_ms,
                "max_dose_ms": max_dose_ms,
                "dose_ml": round(dose_ml, 4),
                "ml_per_sec": ml_per_sec,
            },
        )
    return (duration_ms, "", {})


def _strip_last_dose_at(pid_updates: dict[str, Any], key: str) -> None:
    """Drop last_dose_at from a pending pid_state update for the given PID kind.

    Used to undo the speculative stamp applied inside ``_compute_amount_ml`` when
    the dose is later rejected (e.g. by ``_dose_ml_to_ms`` below min_dose_ms).
    Writing a phantom last_dose_at would misfire ``min_interval_sec`` cooldown.
    """
    entry = pid_updates.get(key)
    if not isinstance(entry, Mapping) or "last_dose_at" not in entry:
        return
    pid_updates[key] = {k: v for k, v in entry.items() if k != "last_dose_at"}


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
