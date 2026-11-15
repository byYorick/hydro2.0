"""Correction dose stages: explicit collaborators, per-call task context."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.application.services.correction_ec_dose_executor import (
    parse_ec_dose_sequence,
)
from ae3lite.application.services.correction_shared import _logger, _pid_entry_or_none
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import (
    CORRECTION_ATTEMPT,
)


@dataclass(frozen=True)
class CorrectionDoseStagesPorts:
    completion_anchored_window: Callable[..., Any]
    correction_config: Callable[..., Any]
    dose_accounting_context: Callable[..., Any]
    ec_dose_executor: Callable[[], Any]
    ensure_sensor_mode_active_for_dosing: Callable[..., Awaitable[Any]]
    enter_correction_after_delay_or_interrupt: Callable[..., Any]
    interrupt_for_control_mode_dosing: Callable[..., Awaitable[Any]]
    log_correction_event: Callable[..., Awaitable[Any]]
    mark_accounted_dose_commands: Callable[..., Awaitable[Any]]
    ml_per_sec_for_actuator: Callable[..., Any]
    ml_per_sec_for_ec_item: Callable[..., Any]
    observation_analyzer: Callable[[], Any]
    observe_seq: Callable[..., Any]
    pid_state: Callable[[], Any]
    require_runtime_plan: Callable[[], Any]
    resolve_actuators: Callable[..., Any]
    resolve_dose_outcome: Callable[..., Any]
    run_command_batch_checked: Callable[[], Any]
    runtime_config: Callable[[], Any]
    create_zone_event: Callable[..., Awaitable[Any]]


class CorrectionDoseStages:
    def __init__(self, ports: CorrectionDoseStagesPorts) -> None:
        self._ports = ports

    async def run_dose_ec(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        flow_hold = await self._ports.interrupt_for_control_mode_dosing(
            task=task,
            plan=plan,
            now=now,
        )
        if flow_hold is not None:
            return flow_hold

        sequence = parse_ec_dose_sequence(corr)
        seq = sequence.items
        ec_single_meta = sequence.single_meta
        CORRECTION_ATTEMPT.labels(topology=task.topology, corr_step="corr_dose_ec").inc()
        current_task = await self._ports.ensure_sensor_mode_active_for_dosing(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            failed_node_uid=corr.ec_node_uid,
            failed_channel=corr.ec_channel,
            retry_cmd="dose",
        )
        is_parallel = str(getattr(corr, "ec_component", "") or "").strip().lower() == "multi_parallel"
        actuators = self._ports.resolve_actuators(
            runtime=self._ports.require_runtime_plan()(plan=plan), task=task, plan=plan
        )
        dose_context = self._ports.dose_accounting_context(task=task, plan=plan, corr=corr, pid_type="ec")
        execution = await self._ports.ec_dose_executor().execute(
            task=task,
            current_task=current_task,
            plan=plan,
            corr=corr,
            now=now,
            seq=seq,
            is_parallel=is_parallel,
            actuators=actuators,
            dose_context=dose_context,
        )
        if isinstance(execution, StageOutcome):
            return execution
        corr = execution.correction
        current_task = execution.task
        result = execution.batch_result

        effective_ml = float(corr.ec_amount_ml or 0.0)
        actual_duration_ms = int(corr.ec_duration_ms or 0)
        if seq and is_parallel:
            effective_ml = 0.0
            actual_duration_ms = 0
            for idx, item in enumerate(seq):
                planned_ml = float(item.get("amount_ml") or 0.0)
                planned_ms = int(item.get("duration_ms") or 0)
                ml_per_sec = self._ports.ml_per_sec_for_ec_item(actuators=actuators, item=item)
                item_ml, item_ms, _ = self._ports.resolve_dose_outcome(
                    planned_ml=planned_ml,
                    planned_duration_ms=planned_ms,
                    ml_per_sec=ml_per_sec,
                    batch_result=result,
                    status_index=idx,
                )
                effective_ml += item_ml
                actual_duration_ms = max(actual_duration_ms, item_ms)
            effective_ml = round(effective_ml, 4)
        elif not seq:
            ml_per_sec = self._ports.ml_per_sec_for_actuator(actuators.get("ec"))
            effective_ml, actual_duration_ms, _ = self._ports.resolve_dose_outcome(
                planned_ml=effective_ml,
                planned_duration_ms=actual_duration_ms,
                ml_per_sec=ml_per_sec,
                batch_result=result,
            )
        # Все режимы, включая parallel, наблюдают подтверждённый объём.
        corr = replace(corr, ec_amount_ml=round(float(effective_ml), 4))
        requested_ml = effective_ml
        if ec_single_meta is not None:
            requested_ml = float(ec_single_meta.get("requested_ml") or effective_ml)
        elif seq:
            requested_ml = round(
                sum(float(item.get("requested_ml") or item.get("amount_ml") or 0.0) for item in seq),
                4,
            )
        runtime = self._ports.require_runtime_plan()(plan=plan)
        # Read last_measured_value from DB (written by _persist_pid_state_updates in _run_check)
        # to avoid using the stale plan.runtime pid_state snapshot.
        current_ec = await self._ports.pid_state().read_measurement_for_event(
            zone_id=task.zone_id,
            pid_type="ec",
        )
        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="EC_DOSING",
            task=task,
            corr=replace(corr, ec_attempt=corr.ec_attempt + 1),
            payload={
                "node_uid": corr.ec_node_uid,
                "channel": corr.ec_channel,
                "duration_ms": actual_duration_ms,
                "planned_duration_ms": corr.ec_duration_ms,
                "amount_ml": effective_ml,
                "effective_ml": effective_ml,
                "requested_ml": requested_ml,
                "dose_sequence": seq or None,
                "seq_index": int(getattr(corr, "ec_current_seq_index", 0) or 0) if seq else None,
                "observe_seq": self._ports.observe_seq(corr=corr, pid_type="ec", after_dose=True),
                "ec_component": corr.ec_component,
                "current_ec": current_ec,
                "target_ec": self._ports.runtime_config().effective_ec_target(task=task, runtime=runtime),
                "target_ec_min": self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime),
                "target_ec_max": self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime),
                "source": "correction_handler",
            },
        )
        if seq and str(getattr(task.workflow, "workflow_phase", "") or "").strip().lower() == "irrigating":
            try:
                await self._ports.create_zone_event(
                    int(task.zone_id),
                    "IRRIGATION_EC_MULTI_DOSE",
                    with_runtime_event_contract(
                        {
                            "task_id": int(getattr(task, "id", 0) or 0),
                            "stage": "irrigation_check",
                            "topology": str(getattr(task, "topology", "") or ""),
                            "dose_sequence": seq,
                        }
                    ),
                )
            except Exception:
                _logger.debug("Не удалось создать zone event IRRIGATION_EC_MULTI_DOSE", exc_info=True)

        runtime = self._ports.require_runtime_plan()(plan=plan)
        process_cfg = self._ports.runtime_config().process_cfg_for_task(task=task, runtime=runtime)
        correction_cfg = self._ports.correction_config(plan=plan, task=task)
        observe_cfg = self._ports.runtime_config().observation_config(
            kind="ec",
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_entry=_pid_entry_or_none(runtime.pid_state, "ec"),
        )
        dose_completed_at, wait_until, hold_delay_sec = self._ports.completion_anchored_window(
            now=now,
            wait_sec=int(observe_cfg["hold_window_sec"]),
        )
        await self._ports.pid_state().persist(
            zone_id=task.zone_id,
            now=dose_completed_at,
            updates={
                "ec": {
                    "hold_until": wait_until,
                    "last_output_ms": actual_duration_ms,
                    "last_correction_kind": "ec",
                    "last_dose_at": dose_completed_at,
                },
                "ph": {
                    "hold_until": wait_until,
                    "feedforward_bias": float(self.expected_cross_coupling_ph(corr=corr, process_cfg=process_cfg)),
                    "last_correction_kind": "ec",
                },
            },
        )
        await self._ports.mark_accounted_dose_commands(batch_result=result, now=dose_completed_at)
        next_corr = replace(
            corr,
            corr_step="corr_wait_ec",
            ec_attempt=corr.ec_attempt + 1,
            wait_until=wait_until,
        )
        return self._ports.enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=hold_delay_sec,
            task_override=current_task if current_task is not task else None,
        )

    async def run_dose_ph(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        flow_hold = await self._ports.interrupt_for_control_mode_dosing(
            task=task,
            plan=plan,
            now=now,
        )
        if flow_hold is not None:
            return flow_hold

        if (
            not corr.ph_node_uid
            or not corr.ph_channel
            or not corr.ph_duration_ms
            or corr.ph_amount_ml is None
            or corr.ph_amount_ml <= 0.0
        ):
            raise TaskExecutionError(
                "corr_dose_ph_missing_plan",
                (
                    "Отсутствует план дозирования pH "
                    f"(node={corr.ph_node_uid}, ch={corr.ph_channel}, ms={corr.ph_duration_ms}, "
                    f"ml={corr.ph_amount_ml})"
                ),
            )
        ph_step = "corr_dose_ph_up" if corr.needs_ph_up else "corr_dose_ph_down"
        CORRECTION_ATTEMPT.labels(topology=task.topology, corr_step=ph_step).inc()
        ph_requested_ml = float(corr.ph_amount_ml or 0.0)
        if corr.ec_dose_sequence_json:
            try:
                raw_meta = json.loads(corr.ec_dose_sequence_json)
                if isinstance(raw_meta, dict) and raw_meta.get("_kind") == "ph_dose_meta":
                    ph_requested_ml = float(raw_meta.get("requested_ml") or ph_requested_ml)
            except Exception:
                _logger.debug("Не удалось прочитать ph_dose_meta из ec_dose_sequence_json", exc_info=True)
        current_task = await self._ports.ensure_sensor_mode_active_for_dosing(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            failed_node_uid=corr.ph_node_uid,
            failed_channel=corr.ph_channel,
            retry_cmd="dose",
        )
        cmd = PlannedCommand(
            step_no=1,
            node_uid=corr.ph_node_uid,
            channel=corr.ph_channel,
            payload={
                "cmd": "dose",
                "_ae3_dose_context": self._ports.dose_accounting_context(
                    task=task,
                    plan=plan,
                    corr=corr,
                    pid_type="ph",
                ),
                "params": {
                    "ml": corr.ph_amount_ml,
                    "duration_ms": int(corr.ph_duration_ms or 0),
                },
            },
        )
        result = await self._ports.run_command_batch_checked()(
            task=current_task,
            commands=(cmd,),
            now=now,
        )
        current_task = result.get("task") or current_task

        runtime = self._ports.require_runtime_plan()(plan=plan)
        actuators = self._ports.resolve_actuators(runtime=runtime, task=task, plan=plan)
        ph_actuator = actuators.get("ph_up") if corr.needs_ph_up else actuators.get("ph_down")
        ml_per_sec = self._ports.ml_per_sec_for_actuator(ph_actuator)
        planned_ml = float(corr.ph_amount_ml or 0.0)
        planned_ms = int(corr.ph_duration_ms or 0)
        effective_ml, actual_duration_ms, _ = self._ports.resolve_dose_outcome(
            planned_ml=planned_ml,
            planned_duration_ms=planned_ms,
            ml_per_sec=ml_per_sec,
            batch_result=result,
        )
        corr = replace(corr, ph_amount_ml=round(float(effective_ml), 4))
        # Read last_measured_value from DB (written by _persist_pid_state_updates in _run_check)
        # to avoid using the stale plan.runtime pid_state snapshot.
        current_ph = await self._ports.pid_state().read_measurement_for_event(
            zone_id=task.zone_id,
            pid_type="ph",
        )
        ph_direction = "up" if corr.needs_ph_up else "down"
        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="PH_CORRECTED",
            task=task,
            corr=replace(corr, ph_attempt=corr.ph_attempt + 1),
            payload={
                "node_uid": corr.ph_node_uid,
                "channel": corr.ph_channel,
                "duration_ms": actual_duration_ms,
                "planned_duration_ms": corr.ph_duration_ms,
                "amount_ml": effective_ml,
                "effective_ml": effective_ml,
                "requested_ml": ph_requested_ml,
                "observe_seq": self._ports.observe_seq(corr=corr, pid_type="ph", after_dose=True),
                "direction": ph_direction,
                "current_ph": current_ph,
                "target_ph": runtime.target_ph,
                "target_ph_min": runtime.target_ph_min,
                "target_ph_max": runtime.target_ph_max,
                "source": "correction_handler",
            },
        )

        runtime = self._ports.require_runtime_plan()(plan=plan)
        process_cfg = self._ports.runtime_config().process_cfg_for_task(task=task, runtime=runtime)
        correction_cfg = self._ports.correction_config(plan=plan, task=task)
        observe_cfg = self._ports.runtime_config().observation_config(
            kind="ph",
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_entry=_pid_entry_or_none(runtime.pid_state, "ph"),
        )
        dose_completed_at, wait_until, hold_delay_sec = self._ports.completion_anchored_window(
            now=now,
            wait_sec=int(observe_cfg["hold_window_sec"]),
        )
        # Audit B5 fix: explicitly zero out the cross-coupling feedforward_bias
        # the previous EC dose may have left in this pH row. Without this
        # reset the bias would linger until the next EC observation clears
        # it, and the planner's simplified "bias != 0" predicate would
        # incorrectly apply a stale EC→pH correction to the next pH tick.
        await self._ports.pid_state().persist(
            zone_id=task.zone_id,
            now=dose_completed_at,
            updates={
                "ph": {
                    "hold_until": wait_until,
                    "last_output_ms": actual_duration_ms,
                    "last_correction_kind": "ph_up" if corr.needs_ph_up else "ph_down",
                    "feedforward_bias": 0.0,
                    "last_dose_at": dose_completed_at,
                },
            },
        )
        await self._ports.mark_accounted_dose_commands(batch_result=result, now=dose_completed_at)
        next_corr = replace(corr, corr_step="corr_wait_ph", ph_attempt=corr.ph_attempt + 1, wait_until=wait_until)
        return self._ports.enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=hold_delay_sec,
            task_override=current_task if current_task is not task else None,
        )

    def expected_cross_coupling_ph(self, *, corr: CorrectionState, process_cfg: Mapping[str, Any]) -> float:
        return self._ports.observation_analyzer().expected_cross_coupling_ph(
            corr=corr,
            process_cfg=process_cfg,
        )
