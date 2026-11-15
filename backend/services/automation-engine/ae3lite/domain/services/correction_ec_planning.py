"""Pure EC dose planning for one normalized measurement/config snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError
from ae3lite.domain.services.correction_actuator_selection import (
    _assert_distinct_parallel_actuators,
    _find_ec_component_actuator,
    _resolve_ec_actuator,
)
from ae3lite.domain.services.correction_calibration import _absorb_dual_calibration_mismatches, _resolve_dose_duration
from ae3lite.domain.services.correction_dose_plan import EcDoseStep
from ae3lite.domain.services.correction_math_defaults import _DEFAULT_MAX_EC_DOSE_ML
from ae3lite.domain.services.correction_pid_math import (
    _compute_amount_ml,
    _dose_output_saturated,
    _next_pid_state,
    _retry_after,
    _with_frozen_integral,
)
from ae3lite.domain.services.correction_primitives import _pid_entry, _positive_float, _positive_int
from ae3lite.domain.services.correction_process_gain import _ec_component_process_gain


@dataclass(frozen=True)
class ECDosePlanningResult:
    ec_dosing_mode: str
    ec_amount_ml: float
    ec_channel: str
    ec_clamped_details: Mapping[str, Any]
    ec_clamped_reason: str
    ec_component_name: str
    ec_discarded_details: Mapping[str, Any]
    ec_discarded_reason: str
    ec_dose_sequence: tuple[EcDoseStep, ...]
    ec_duration_ms: int
    ec_needs: bool
    ec_node_uid: str
    ec_requested_ml: float
    ec_retry_after: Optional[int]
    pid_updates: dict[str, Any]
    dual_mismatch_collector: list[dict[str, Any]]


def plan_ec_dose(
    *,
    controller_ec: Mapping[str, Any],
    correction_config: Mapping[str, Any],
    current_ec: float,
    dual_mismatch_collector: list[dict[str, Any]],
    ec_actuator: Optional[Mapping[str, Any]],
    ec_actuators: Optional[Mapping[str, Any]],
    ec_amount_ml: float,
    ec_channel: str,
    ec_component_policy: Optional[Mapping[str, Any]],
    ec_controller_cfg: Mapping[str, Any],
    ec_discarded_details: Mapping[str, Any],
    ec_dose_sequence: tuple[EcDoseStep, ...],
    ec_duration_ms: int,
    ec_gap: float,
    ec_lo: float,
    ec_needs: bool,
    ec_node_uid: str,
    ec_pid_zone: str,
    ec_retry_after: Optional[int],
    now: Optional[datetime],
    phase_key: str,
    pid_state: Optional[Mapping[str, Any]],
    pid_updates: dict[str, Any],
    process_cfg: Mapping[str, Any],
    ec_clamped_details: Mapping[str, Any],
    ec_clamped_reason: str,
    ec_component_name: str,
    ec_discarded_reason: str,
    ec_requested_ml: float,
) -> ECDosePlanningResult:
    ec_dosing_mode = "single"
    pid_updates = dict(pid_updates)
    dual_mismatch_collector = list(dual_mismatch_collector)
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
        multi_fail_closed = is_multi and "npk" in excluded_set and phase_key == "irrigation"
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
            ec_integral_before = float(ec_pid_entry.get("integral") or 0.0)
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
                    "Режим EC multi_sequential исключает NPK, но активные EC-компоненты не настроены"
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
                multi_saturated = False
                contract_max = _positive_float(correction_config.get("max_ec_dose_ml"), _DEFAULT_MAX_EC_DOSE_ML)
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
                    uncapped_component_ml = dose_ml
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
                            multi_saturated = True
                            continue
                    dose_ml = round(max(0.0, dose_ml), 4)
                    if _dose_output_saturated(uncapped_ml=uncapped_component_ml, capped_ml=dose_ml):
                        multi_saturated = True

                    requested_ml = dose_ml
                    effective_ml, requested_ml, duration_ms, reason, details = _resolve_dose_duration(
                        requested_ml=requested_ml,
                        calibration=calibration,
                        correction_config=correction_config,
                    )
                    _absorb_dual_calibration_mismatches(dual_mismatch_collector, details)
                    dose_ml = effective_ml
                    if reason == "clamped_to_max_dose_ms":
                        multi_saturated = True
                    if duration_ms <= 0 and requested_ml > 0:
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
                            requested_ml=requested_ml if requested_ml != dose_ml else None,
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
                    ec_requested_ml = round(
                        sum((step.requested_ml if step.requested_ml is not None else step.amount_ml) for step in seq),
                        4,
                    )
                    ec_duration_ms = int(total_ms)
                    if ec_pid_update:
                        if multi_saturated:
                            ec_pid_update = _with_frozen_integral(
                                pid_update=ec_pid_update,
                                integral_before=ec_integral_before,
                                controller_cfg=ec_controller_cfg,
                            )
                        if ec_pid_zone:
                            ec_pid_update = {**ec_pid_update, "current_zone": ec_pid_zone}
                        pid_updates["ec"] = ec_pid_update
                    ec_discarded_reason = "multi_component_partial" if discarded else ""
                    ec_discarded_details = {"discarded": discarded} if discarded else {}
                    ec_needs = ec_duration_ms > 0
                else:
                    ec_discarded_reason = "ec_multi_component_no_effective_pulses"
                    ec_discarded_details = {"discarded": discarded}
                    ec_needs = False

        # Fail-closed: если включён multi_sequential и NPK исключён во время полива,
        # нельзя откатываться к single-dose (legacy-default для dose_ec_channel запрещён).
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
                f"Режим EC {ec_dosing_mode} не дал безопасных non-NPK доз во время полива "
                f"(отброшено={discarded_components})"
            )
        if not ec_dose_sequence and not multi_fail_closed:
            forced = str(correction_config.get("ec_forced_component") or "").strip().lower()
            if forced and isinstance(ec_actuators, Mapping):
                resolved_ec = _find_ec_component_actuator(
                    ec_actuators=ec_actuators,
                    component=forced,
                )
                if resolved_ec is None:
                    raise PlannerConfigurationError(
                        f"Не найден actuator для EC component={forced}",
                        code=ErrorCodes.AE3_EC_ACTUATOR_COMPONENT_UNRESOLVED,
                    )
                resolved_component = forced
            else:
                resolved_component, resolved_ec = _resolve_ec_actuator(
                    ec_actuator=ec_actuator,
                    ec_actuators=ec_actuators,
                    ec_component_policy=ec_component_policy,
                    phase_key=phase_key,
                    default_channel=str(correction_config.get("dose_ec_channel") or "").strip().lower(),
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
                pid_entry=_pid_entry(pid_state, "ec"),
                now=now,
            )
            ec_integral_before = float(_pid_entry(pid_state, "ec").get("integral") or 0.0)
            if ec_pid_update:
                if ec_pid_zone:
                    ec_pid_update = {**ec_pid_update, "current_zone": ec_pid_zone}
                pid_updates["ec"] = ec_pid_update
            ec_requested_ml = ec_amount_ml
            ec_amount_ml, ec_requested_ml, ec_duration_ms, ec_duration_reason, ec_duration_details = (
                _resolve_dose_duration(
                    requested_ml=ec_amount_ml,
                    calibration=calibration,
                    correction_config=correction_config,
                )
            )
            _absorb_dual_calibration_mismatches(dual_mismatch_collector, ec_duration_details)
            if ec_duration_reason == "clamped_to_max_dose_ms" and isinstance(ec_pid_update, Mapping) and ec_pid_update:
                ec_pid_update = _with_frozen_integral(
                    pid_update=ec_pid_update,
                    integral_before=ec_integral_before,
                    controller_cfg=ec_controller_cfg,
                )
                if ec_pid_zone:
                    ec_pid_update = {**ec_pid_update, "current_zone": ec_pid_zone}
                pid_updates["ec"] = ec_pid_update
            # Planner-level discard (min_effective exceeds gap cap) takes precedence.
            # Clamp is NOT a discard — dose still proceeds (separate dose_clamped_*).
            if ec_planner_discard_reason:
                ec_discarded_reason = ec_planner_discard_reason
                ec_discarded_details = ec_planner_discard_details
            elif ec_duration_reason == "clamped_to_max_dose_ms":
                ec_clamped_reason = ec_duration_reason
                ec_clamped_details = ec_duration_details
            elif ec_duration_reason:
                ec_discarded_reason = ec_duration_reason
                ec_discarded_details = ec_duration_details
            ec_needs = ec_duration_ms > 0
    else:
        ec_needs = False
    return ECDosePlanningResult(
        ec_dosing_mode=ec_dosing_mode,
        ec_amount_ml=ec_amount_ml,
        ec_channel=ec_channel,
        ec_clamped_details=ec_clamped_details,
        ec_clamped_reason=ec_clamped_reason,
        ec_component_name=ec_component_name,
        ec_discarded_details=ec_discarded_details,
        ec_discarded_reason=ec_discarded_reason,
        ec_dose_sequence=ec_dose_sequence,
        ec_duration_ms=ec_duration_ms,
        ec_needs=ec_needs,
        ec_node_uid=ec_node_uid,
        ec_requested_ml=ec_requested_ml,
        ec_retry_after=ec_retry_after,
        pid_updates=pid_updates,
        dual_mismatch_collector=dual_mismatch_collector,
    )
