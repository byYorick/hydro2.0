"""SolutionFillCheckHandler: in-flow correction во время заполнения бака раствора."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import STAGE_DEADLINE_EXCEEDED
from common.biz_alerts import send_biz_alert

_logger = logging.getLogger(__name__)


class SolutionFillCheckHandler(BaseStageHandler):
    """Обрабатывает ``solution_fill_check``: окно заполнения и in-flow correction.

    Исходы:
    1. Бак полон и target'ы достигнуты → ``solution_fill_stop_to_ready``
    2. Бак полон, но target'ы не достигнуты → ``solution_fill_stop_to_prepare``
    3. Бак ещё заполняется и target'ы не достигнуты → коррекция внутри ``solution_fill_check``
    4. Бак ещё заполняется и target'ы достигнуты → ``poll``
    5. Дедлайн превышен → ``solution_fill_timeout_stop``
    """

    _STALE_RECHECK_DELAY_SEC = 0.25

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        plan = await self._checkpoint(task=task, plan=plan, now=now)
        runtime = self._require_runtime_plan(plan=plan)
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "")
        fail_safe_guards = runtime.fail_safe_guards
        recent_storage_event = await self._read_recent_storage_event(
            task=task,
            event_types=(
                "SOLUTION_FILL_SOURCE_EMPTY",
                "SOLUTION_FILL_LEAK_DETECTED",
                "SOLUTION_FILL_COMPLETED",
                "EMERGENCY_STOP_ACTIVATED",
            ),
            max_age_sec=86400,  # config-literal: one-day storage-event replay window
        )
        recent_event_type = str((recent_storage_event or {}).get("event_type") or "").strip().upper()
        if recent_event_type == "SOLUTION_FILL_SOURCE_EMPTY":
            self._observe_fail_safe_transition(
                task=task,
                reason="solution_fill_source_empty",
                source="node_event",
                next_stage="solution_fill_source_empty_stop",
            )
            return StageOutcome(kind="transition", next_stage="solution_fill_source_empty_stop")
        if recent_event_type == "SOLUTION_FILL_LEAK_DETECTED":
            self._observe_fail_safe_transition(
                task=task,
                reason="solution_fill_leak_detected",
                source="node_event",
                next_stage="solution_fill_leak_stop",
            )
            return StageOutcome(kind="transition", next_stage="solution_fill_leak_stop")
        if recent_event_type == "EMERGENCY_STOP_ACTIVATED":
            await self._reconcile_recent_emergency_stop(
                task=task,
                plan=plan,
                now=now,
                expected={
                    "valve_clean_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            )
        if recent_event_type == "SOLUTION_FILL_COMPLETED":
            return await self._completed_outcome(task=task, plan=plan, now=now, runtime=runtime)

        try:
            await self._probe_irr_state(
                task=task, plan=plan, now=now,
                expected={
                    "valve_clean_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            )
        except TaskExecutionError as exc:
            if exc.code == "irr_state_mismatch":
                raced_completion_event = await self._read_recent_storage_event(
                    task=task,
                    event_types=("SOLUTION_FILL_COMPLETED",),
                    max_age_sec=86400,  # config-literal: one-day completion-event replay window
                )
                raced_event_type = str((raced_completion_event or {}).get("event_type") or "").strip().upper()
                if raced_event_type == "SOLUTION_FILL_COMPLETED":
                    _logger.info(
                        "solution_fill_check: probe увидел уже выключенный fill-state, но node успела опубликовать completion; завершаем штатно zone_id=%s task_id=%s",
                        task.zone_id,
                        getattr(task, "id", None),
                    )
                    return await self._completed_outcome(task=task, plan=plan, now=now, runtime=runtime)
            raise

        if pending_manual_step == "solution_fill_stop":
            if str(getattr(task, "task_type", "") or "").strip().lower() == "solution_change":
                return StageOutcome(kind="transition", next_stage="solution_fill_stop_to_refill_confirm")
            if await self._should_finish_to_ready(task=task, plan=plan, now=now, runtime=runtime):
                return StageOutcome(kind="transition", next_stage="solution_fill_stop_to_ready")
            return StageOutcome(kind="transition", next_stage="solution_fill_stop_to_prepare")
        flow_hold = await self._handle_control_mode_flow_path_interrupt(
            task=task,
            plan=plan,
            now=now,
            control_mode=control_mode,
        )
        if flow_hold is not None:
            return flow_hold

        clean_min_check_delay_ms = int(fail_safe_guards.solution_fill_clean_min_check_delay_ms)
        if self._stage_elapsed_ms(task=task, now=now) >= max(0, clean_min_check_delay_ms):
            clean_min = await self._read_level(
                task=task,
                zone_id=task.zone_id,
                labels=runtime.clean_min_sensor_labels,
                threshold=runtime.level_switch_on_threshold,
                telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
                unavailable_error="two_tank_clean_min_level_unavailable",
                stale_error="two_tank_clean_min_level_stale",
                stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
                prefer_probe_snapshot=True,
            )
            if not clean_min["is_triggered"]:
                self._observe_fail_safe_transition(
                    task=task,
                    reason="solution_fill_source_empty",
                    source="sensor",
                    next_stage="solution_fill_source_empty_stop",
                )
                return StageOutcome(kind="transition", next_stage="solution_fill_source_empty_stop")

        solution_min_check_delay_ms = int(fail_safe_guards.solution_fill_solution_min_check_delay_ms)
        if self._stage_elapsed_ms(task=task, now=now) >= max(0, solution_min_check_delay_ms):
            solution_min = await self._read_level(
                task=task,
                zone_id=task.zone_id,
                labels=runtime.solution_min_sensor_labels,
                threshold=runtime.level_switch_on_threshold,
                telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
                unavailable_error="two_tank_solution_min_level_unavailable",
                stale_error="two_tank_solution_min_level_stale",
                stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
                prefer_probe_snapshot=True,
            )
            if not solution_min["is_triggered"]:
                self._observe_fail_safe_transition(
                    task=task,
                    reason="solution_fill_leak_detected",
                    source="sensor",
                    next_stage="solution_fill_leak_stop",
                )
                return StageOutcome(kind="transition", next_stage="solution_fill_leak_stop")

        solution_max = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime.solution_max_sensor_labels,
            threshold=runtime.level_switch_on_threshold,
            telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
            unavailable_error="two_tank_solution_level_unavailable",
            stale_error="two_tank_solution_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )

        if solution_max["is_triggered"]:
            return await self._completed_outcome(task=task, plan=plan, now=now, runtime=runtime)

        # Проверка дедлайна
        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            _logger.warning("solution_fill_check: дедлайн превышен, заполнение останавливается zone_id=%s", task.zone_id)
            STAGE_DEADLINE_EXCEEDED.labels(
                topology=str(getattr(task, "topology", "") or ""),
                stage="solution_fill_check",
            ).inc()
            try:
                await send_biz_alert(
                    code="biz_solution_fill_timeout",
                    alert_type="AE3 Solution Fill Timeout",
                    message="Превышено время заполнения бака раствором до завершения этапа.",
                    severity="warning",
                    zone_id=int(task.zone_id),
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "topology": str(getattr(task, "topology", "") or ""),
                        "stage": "solution_fill_check",
                        "component": "handler:solution_fill_check",
                        "message": "Превышено время заполнения бака раствором; проверьте клапан подачи раствора и насос.",
                    },
                    scope_parts=("stage:solution_fill_check",),
                )
            except Exception:
                # Audit F9: include full exception context so downstream debugging
                # of failed alert delivery isn't blocked by a message without
                # zone/task identification.
                _logger.warning(
                    "Не удалось отправить alert biz_solution_fill_timeout "
                    "zone_id=%s task_id=%s",
                    task.zone_id,
                    getattr(task, "id", None),
                    exc_info=True,
                )
            return StageOutcome(kind="transition", next_stage="solution_fill_timeout_stop")

        # Fill doses calcium only → gate is EC-only to T_ca (skip pH).
        if await self._fill_ec_target_reached(task=task, plan=plan, now=now, runtime=runtime):
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.level_poll_interval_sec),
            )

        if int(getattr(task.workflow, "stage_retry_count", 0) or 0) > 0:
            _logger.info(
                "solution_fill_check: in-flow correction уже исчерпана, заполнение продолжается без новой коррекции zone_id=%s retry_count=%s",
                task.zone_id,
                getattr(task.workflow, "stage_retry_count", 0),
            )
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.level_poll_interval_sec),
            )

        _logger.info(
            "solution_fill_check: заполнение продолжается, цели не достигнуты; вход в in-flow correction zone_id=%s",
            task.zone_id,
        )
        corr = await self._enter_fill_calcium_correction(
            task=task,
            plan=plan,
            runtime=runtime,
            now=now,
            return_stage_success=stage_def.on_corr_success or "solution_fill_check",
            return_stage_fail=stage_def.on_corr_fail or "solution_fill_check",
        )
        return StageOutcome(kind="enter_correction", correction=corr, task_override=task)

    async def _should_finish_to_ready(
        self, *, task: Any, plan: Any, now: datetime, runtime: Any = None,
    ) -> bool:
        if runtime is None:
            runtime = plan.runtime
        solution_max = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime.solution_max_sensor_labels,
            threshold=runtime.level_switch_on_threshold,
            telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
            unavailable_error="two_tank_solution_level_unavailable",
            stale_error="two_tank_solution_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )
        if not solution_max["is_triggered"]:
            return False

        await self._check_sensor_consistency(
            task=task,
            runtime=runtime,
            min_labels_key="solution_min_sensor_labels",
            min_unavailable_error="two_tank_solution_min_level_unavailable",
            min_stale_error="two_tank_solution_min_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )
        return await self._finish_ready_or_irrigation_short_circuit(
            task=task, plan=plan, now=now, runtime=runtime,
        )

    async def _completed_outcome(
        self, *, task: Any, plan: Any, now: datetime, runtime: Any = None,
    ) -> StageOutcome:
        if runtime is None:
            runtime = plan.runtime
        await self._check_sensor_consistency(
            task=task,
            runtime=runtime,
            min_labels_key="solution_min_sensor_labels",
            min_unavailable_error="two_tank_solution_min_level_unavailable",
            min_stale_error="two_tank_solution_min_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )

        if str(getattr(task, "task_type", "") or "").strip().lower() == "solution_change":
            _logger.info(
                "solution_fill_check: refill завершён, ожидание operator confirm (G2) zone_id=%s",
                task.zone_id,
            )
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_stop_to_refill_confirm",
            )

        if await self._finish_ready_or_irrigation_short_circuit(
            task=task, plan=plan, now=now, runtime=runtime,
        ):
            _logger.info(
                "solution_fill_check: бак полон и раствор в prepare-band или irrigation short-circuit → ready "
                "zone_id=%s",
                task.zone_id,
            )
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_stop_to_ready",
            )

        _logger.info(
            "solution_fill_check: бак заполнен, но цели не достигнуты; переход в prepare recirculation zone_id=%s",
            task.zone_id,
        )
        return StageOutcome(
            kind="transition",
            next_stage="solution_fill_stop_to_prepare",
        )

    def _build_correction_state(
        self,
        *,
        task: Any,
        runtime: Any,
        sensors_already_active: bool,
        return_stage_success: str,
        return_stage_fail: str,
    ) -> CorrectionState:
        correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
        ec_max_attempts = self._required_correction_int(
            correction_cfg=correction_cfg,
            key="max_ec_correction_attempts",
        )
        ph_max_attempts = self._required_correction_int(
            correction_cfg=correction_cfg,
            key="max_ph_correction_attempts",
        )
        corr = CorrectionState.build_default(
            corr_step="corr_check" if sensors_already_active else "corr_activate",
            max_attempts=max(ec_max_attempts, ph_max_attempts),
            ec_max_attempts=ec_max_attempts,
            ph_max_attempts=0,  # no pH on fill
            activated_here=not sensors_already_active,
            stabilization_sec=self._required_correction_int(
                correction_cfg=correction_cfg,
                key="stabilization_sec",
            ),
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
        )
        return replace(corr, **self._probe_snapshot_correction_fields(task=task))

    async def _fill_ec_target_reached(
        self, *, task: Any, plan: Any, now: datetime, runtime: Any = None,
    ) -> bool:
        """EC-only gate for solution_fill: compare to T_ca when known, skip pH."""
        if runtime is None:
            runtime = self._require_runtime_plan(plan=plan)
        max_age = int(runtime.telemetry_max_age_sec)
        correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
        process_cfg = self._process_cfg_for_task(task=task, runtime=runtime)
        ec = await self._read_target_metric_window(
            zone_id=task.zone_id,
            sensor_type="EC",
            telemetry_max_age_sec=max_age,
            config=self._observation_config(kind="ec", correction_cfg=correction_cfg, process_cfg=process_cfg),
            unavailable_error="two_tank_prepare_targets_unavailable",
            stale_error="two_tank_prepare_targets_stale",
            now=now,
        )
        if not ec.get("ready"):
            return False
        ec_target = await self._resolve_fill_ec_target(task=task, runtime=runtime)
        tolerance = self._prepare_tolerance_for_task(task=task, runtime=runtime)
        ec_tol = abs(ec_target) * (
            self._required_prepare_tolerance_pct(tolerance=tolerance, key="ec_pct") / 100.0
        )
        current_ec = float(ec["value"])
        return (ec_target - ec_tol) <= current_ec <= (ec_target + ec_tol)

    async def _resolve_fill_ec_target(self, *, task: Any, runtime: Any) -> float:
        """Prefer T_ca from existing fill baseline; else effective/prepare EC."""
        from ae3lite.domain.services.nutrient_pipeline import (
            ComponentTargets,
            active_ec_target_for_corr,
        )

        existing = await self._load_existing_fill_baseline(task=task)
        if existing is not None:
            targets, _baseline_id = existing
            return active_ec_target_for_corr(
                pipeline_phase="fill_ca",
                active_component="calcium",
                targets=targets,
                fallback_target_ec=float(self._irrigation_ec_target(runtime=runtime)),
            )
        corr = getattr(task, "correction", None)
        if corr is not None:
            targets = ComponentTargets.from_json(getattr(corr, "component_targets_json", None))
            if targets is not None:
                return active_ec_target_for_corr(
                    pipeline_phase=getattr(corr, "pipeline_phase", None) or "fill_ca",
                    active_component=getattr(corr, "active_component", None) or "calcium",
                    targets=targets,
                    fallback_target_ec=float(self._irrigation_ec_target(runtime=runtime)),
                )
        return float(self._effective_ec_target(task=task, runtime=runtime))

    @staticmethod
    def _corr_has_fill_baseline(corr: Any) -> bool:
        if corr is None:
            return False
        if getattr(corr, "baseline_id", None) is not None:
            return True
        if getattr(corr, "water_ec", None) is not None:
            return True
        phase = str(getattr(corr, "pipeline_phase", "") or "").strip().lower()
        targets_json = getattr(corr, "component_targets_json", None)
        if phase in {"fill_ca", "fill_calcium"} and targets_json:
            return True
        return False

    async def _load_existing_fill_baseline(
        self, *, task: Any,
    ) -> tuple[Any, int | None] | None:
        """Return (ComponentTargets, baseline_id) from task.corr or DB, else None."""
        import json

        from ae3lite.domain.services.nutrient_pipeline import (
            ComponentTargets,
            compute_component_targets,
        )
        from ae3lite.infrastructure.repositories.prepare_baseline_repository import (
            PgPrepareBaselineRepository,
        )

        corr = getattr(task, "correction", None)
        if self._corr_has_fill_baseline(corr):
            targets = ComponentTargets.from_json(getattr(corr, "component_targets_json", None))
            if targets is None and getattr(corr, "water_ec", None) is not None:
                # Minimal reconstruct is not possible without ratios/target; treat as present
                # only when component_targets_json is available.
                pass
            if targets is not None:
                baseline_id = getattr(corr, "baseline_id", None)
                return targets, int(baseline_id) if baseline_id is not None else None

        try:
            repo = PgPrepareBaselineRepository()
            task_id = int(getattr(task, "id", 0) or 0) or None
            # Only reuse baseline for THIS task. Zone-wide fallback skips
            # WATER_BASELINE_CAPTURED on a new task and reuses stale water_ec
            # from prior cycles (breaks E118 live and dilute math).
            row = None
            if task_id is not None:
                row = await repo.fetch_latest_baseline(
                    zone_id=int(task.zone_id),
                    ae_task_id=task_id,
                )
            if row is None:
                return None
            baseline_id = int(row["id"]) if row.get("id") is not None else None
            raw_targets = row.get("component_targets_json")
            if isinstance(raw_targets, str):
                raw_targets = json.loads(raw_targets)
            if isinstance(raw_targets, dict) and "T_ca" in raw_targets:
                targets = ComponentTargets.from_mapping(raw_targets)
                return targets, baseline_id
            ratios = row.get("ratios_json")
            if isinstance(ratios, str):
                ratios = json.loads(ratios)
            targets = compute_component_targets(
                water_ec=float(row["water_ec"]),
                water_ph=float(row.get("water_ph") or 0.0),
                target_ec=float(row["target_ec"]),
                ratios=ratios if isinstance(ratios, dict) else {},
            )
            return targets, baseline_id
        except Exception:
            _logger.warning(
                "solution_fill: не удалось загрузить existing baseline zone_id=%s",
                getattr(task, "zone_id", None),
                exc_info=True,
            )
            return None

    async def _enter_fill_calcium_correction(
        self,
        *,
        task: Any,
        plan: Any,
        runtime: Any,
        now: datetime,
        return_stage_success: str,
        return_stage_fail: str,
    ) -> CorrectionState:
        """Capture water baseline once, persist, open calcium-only correction to T_ca.

        Re-enter after Ca doses must NOT recapture water_ec (budget would shrink).
        """
        from ae3lite.domain.errors import ErrorCodes, TaskExecutionError
        from ae3lite.domain.services.nutrient_pipeline import (
            PIPELINE_PHASE_FILL_CA,
            compute_component_targets,
        )
        from ae3lite.infrastructure.repositories.prepare_baseline_repository import (
            PgPrepareBaselineRepository,
        )
        from common.db import create_zone_event

        corr = self._build_correction_state(
            task=task,
            runtime=runtime,
            sensors_already_active=True,
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
        )

        existing = await self._load_existing_fill_baseline(task=task)
        if existing is not None:
            targets, baseline_id = existing
            _logger.info(
                "solution_fill: reuse existing water baseline zone_id=%s baseline_id=%s water_ec=%s",
                task.zone_id,
                baseline_id,
                targets.water_ec,
            )
            return replace(
                corr,
                pipeline_phase=PIPELINE_PHASE_FILL_CA,
                active_component="calcium",
                water_ec=targets.water_ec,
                water_ph=targets.water_ph,
                nutrient_budget=targets.nutrient_budget,
                component_targets_json=targets.to_json(),
                baseline_id=baseline_id,
                ec_pid_frozen=False,
                dilute_attempts=0,
            )

        # First entry only: capture + persist + WATER_BASELINE_CAPTURED
        max_age = int(runtime.telemetry_max_age_sec)
        correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
        process_cfg = self._process_cfg_for_task(task=task, runtime=runtime)
        ph_win = await self._read_target_metric_window(
            zone_id=task.zone_id,
            sensor_type="PH",
            telemetry_max_age_sec=max_age,
            config=self._observation_config(kind="ph", correction_cfg=correction_cfg, process_cfg=process_cfg),
            unavailable_error="two_tank_prepare_targets_unavailable",
            stale_error="two_tank_prepare_targets_stale",
            now=now,
        )
        ec_win = await self._read_target_metric_window(
            zone_id=task.zone_id,
            sensor_type="EC",
            telemetry_max_age_sec=max_age,
            config=self._observation_config(kind="ec", correction_cfg=correction_cfg, process_cfg=process_cfg),
            unavailable_error="two_tank_prepare_targets_unavailable",
            stale_error="two_tank_prepare_targets_stale",
            now=now,
        )
        if not ph_win.get("ready") or not ec_win.get("ready"):
            raise TaskExecutionError(
                ErrorCodes.AE3_WATER_BASELINE_INVALID,
                "Не удалось снять стабильный water baseline EC/pH для solution_fill",
            )
        current_ec = float(ec_win["value"])
        current_ph = float(ph_win["value"])
        # Prefer full recipe target_ec (not T_step) for budget math
        target_ec = float(self._irrigation_ec_target(runtime=runtime))
        # Cumulative T_* must use FULL recipe ratios (tank_recirc), not the
        # fill-phase calcium-only map. Calcium-only → T_ca==T_full and breaks
        # dilute-on-overshoot (seed above T_ca never exceeds T_full*(1+pct)).
        ratios = self._full_ec_component_ratios(runtime=runtime, correction_cfg=correction_cfg)
        targets = compute_component_targets(
            water_ec=float(current_ec),
            water_ph=float(current_ph),
            target_ec=target_ec,
            ratios=ratios,
        )
        baseline_id = None
        try:
            repo = PgPrepareBaselineRepository()
            baseline_id = await repo.insert_baseline(
                zone_id=int(task.zone_id),
                water_ec=targets.water_ec,
                water_ph=targets.water_ph,
                target_ec=targets.target_ec,
                nutrient_budget=targets.nutrient_budget,
                ratios=targets.ratios,
                component_targets=targets.as_dict(),
                ae_task_id=int(getattr(task, "id", 0) or 0) or None,
                grow_cycle_id=getattr(runtime, "grow_cycle_id", None),
                captured_at=now,
            )
        except Exception:
            _logger.warning(
                "solution_fill: не удалось persist baseline zone_id=%s",
                task.zone_id,
                exc_info=True,
            )
        try:
            await create_zone_event(
                int(task.zone_id),
                "WATER_BASELINE_CAPTURED",
                {
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "water_ec": targets.water_ec,
                    "water_ph": targets.water_ph,
                    "target_ec": targets.target_ec,
                    "nutrient_budget": targets.nutrient_budget,
                    "T_ca": targets.T_ca,
                    "baseline_id": baseline_id,
                },
            )
        except Exception:
            _logger.warning(
                "solution_fill: WATER_BASELINE_CAPTURED event failed zone_id=%s",
                task.zone_id,
                exc_info=True,
            )
        return replace(
            corr,
            pipeline_phase=PIPELINE_PHASE_FILL_CA,
            active_component="calcium",
            water_ec=targets.water_ec,
            water_ph=targets.water_ph,
            nutrient_budget=targets.nutrient_budget,
            component_targets_json=targets.to_json(),
            baseline_id=baseline_id,
            ec_pid_frozen=False,
            dilute_attempts=0,
        )