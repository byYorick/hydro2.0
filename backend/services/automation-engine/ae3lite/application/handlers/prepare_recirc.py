"""PrepareRecircCheckHandler: target'ы, дедлайн и вход в коррекцию."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from common.db import create_zone_event

_logger = logging.getLogger(__name__)


class PrepareRecircCheckHandler(BaseStageHandler):
    """Обрабатывает ``prepare_recirculation_check``: probe, target'ы и коррекцию.

    Исходы:
    1. Target'ы достигнуты → ``prepare_recirculation_stop_to_ready``
    2. Target'ы не достигнуты → вход в цикл коррекции
    3. Дедлайн превышен → ``prepare_recirculation_window_exhausted``
    4. Раствор закончился (solution_min) → ``prepare_recirculation_solution_low_stop`` → startup
    """

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        command_gateway: Any,
        task_repository: Any = None,
        pid_state_repository: Any = None,
        live_reload_enabled: bool = False,
    ) -> None:
        super().__init__(
            runtime_monitor=runtime_monitor,
            command_gateway=command_gateway,
            task_repository=task_repository,
            live_reload_enabled=live_reload_enabled,
        )
        self._pid_state_repository = pid_state_repository

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
        solution_min_guard_enabled = bool(fail_safe_guards.recirculation_stop_on_solution_min)

        # Fail-fast перед новой probe-командой. Иначе stage, у которого уже
        # закончилось время, может опубликовать новый storage_state request и упасть
        # на command polling вместо перехода по ожидаемому path window_exhausted.
        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            _logger.info(
                "prepare_recirculation_check: дедлайн превышен, окно исчерпывается zone_id=%s retry_count=%s",
                task.zone_id, task.workflow.stage_retry_count,
            )
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=task.workflow.stage_retry_count,
            )
        if self._deadline_too_close_for_irr_probe(now=now, deadline=deadline, runtime=runtime):
            _logger.info(
                "prepare_recirculation_check: оставшееся время stage меньше бюджета IRR probe, "
                "окно исчерпывается zone_id=%s retry_count=%s",
                task.zone_id,
                task.workflow.stage_retry_count,
            )
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=task.workflow.stage_retry_count,
            )

        recent_storage_event = await self._read_recent_storage_event(
            task=task,
            event_types=("RECIRCULATION_SOLUTION_LOW", "EMERGENCY_STOP_ACTIVATED"),
            max_age_sec=86400,  # config-literal: one-day storage-event replay window
        )
        recent_event_type = str((recent_storage_event or {}).get("event_type") or "").strip().upper()
        if recent_event_type == "RECIRCULATION_SOLUTION_LOW" and solution_min_guard_enabled:
            return await self._solution_low_to_setup_outcome(
                task=task,
                source="node_event",
            )
        if recent_event_type == "EMERGENCY_STOP_ACTIVATED":
            await self._reconcile_recent_emergency_stop(
                task=task,
                plan=plan,
                now=now,
                expected={
                    "valve_solution_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            )

        # solution_min ДО IRR probe: при depleted нода failsafe гасит клапаны,
        # иначе probe падает irr_state_mismatch раньше path → startup.
        if solution_min_guard_enabled:
            solution_min = await self._read_solution_min_level(task=task, runtime=runtime)
            if not solution_min["is_triggered"]:
                return await self._solution_low_to_setup_outcome(
                    task=task,
                    source="sensor",
                )

        try:
            probe_outcome = await self._probe_irr_state_with_backoff(
                task=task, plan=plan, now=now,
                expected={
                    "valve_solution_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
                poll_delay_sec=int(runtime.level_poll_interval_sec),
                exhausted_outcome=StageOutcome(
                    kind="transition",
                    next_stage="prepare_recirculation_window_exhausted",
                    stage_retry_count=task.workflow.stage_retry_count,
                ),
            )
        except TaskExecutionError as exc:
            # Race: solution_min упал во время probe → клапана OFF → mismatch.
            if (
                solution_min_guard_enabled
                and exc.code == "irr_state_mismatch"
            ):
                solution_min = await self._read_solution_min_level(task=task, runtime=runtime)
                if not solution_min["is_triggered"]:
                    _logger.info(
                        "prepare_recirculation_check: irr_state_mismatch при depleted solution_min "
                        "→ setup zone_id=%s task_id=%s",
                        task.zone_id,
                        getattr(task, "id", None),
                    )
                    return await self._solution_low_to_setup_outcome(
                        task=task,
                        source="sensor_after_irr_mismatch",
                    )
            raise
        if probe_outcome is not None:
            return probe_outcome

        if pending_manual_step == "prepare_recirculation_stop":
            _logger.info("prepare_recirculation_check: запрошена ручная остановка zone_id=%s", task.zone_id)
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_stop_to_ready",
            )
        flow_hold = await self._handle_control_mode_flow_path_interrupt(
            task=task,
            plan=plan,
            now=now,
            control_mode=control_mode,
        )
        if flow_hold is not None:
            return flow_hold

        if await self._finish_ready_or_irrigation_short_circuit(
            task=task, plan=plan, now=now, runtime=runtime,
        ):
            _logger.info(
                "prepare_recirculation_check: цели достигнуты (prepare-band или irrigation short-circuit) "
                "zone_id=%s",
                task.zone_id,
            )
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_stop_to_ready",
            )

        # Target'ы не достигнуты: вход в коррекцию.
        _logger.info("prepare_recirculation_check: цели не достигнуты, переход в correction zone_id=%s", task.zone_id)
        # Сенсоры уже активны: их включил prepare_recirculation_start → sensor_mode_activate.
        corr = await self._enter_recirc_pipeline_correction(
            task=task,
            runtime=runtime,
            return_stage_success=stage_def.on_corr_success or "prepare_recirculation_stop_to_ready",
            return_stage_fail=stage_def.on_corr_fail or "prepare_recirculation_window_exhausted",
        )
        return StageOutcome(kind="enter_correction", correction=corr, task_override=task)

    async def _solution_low_to_setup_outcome(
        self,
        *,
        task: Any,
        source: str,
    ) -> StageOutcome:
        """Остановка recirc + сброс no-effect block → startup (обычная подготовка раствора)."""
        self._observe_fail_safe_transition(
            task=task,
            reason="recirculation_solution_low",
            source=source,
            next_stage="prepare_recirculation_solution_low_stop",
        )
        await self._clear_correction_blocks(task=task, reason="recirculation_solution_low_to_setup")
        try:
            await create_zone_event(
                int(task.zone_id),
                "RECIRCULATION_SOLUTION_LOW_TO_SETUP",
                {
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "stage": "prepare_recirculation_check",
                    "source": source,
                    "next_stage": "prepare_recirculation_solution_low_stop",
                    "setup_stage": "startup",
                },
            )
        except Exception:
            _logger.warning(
                "prepare_recirculation_check: не удалось записать RECIRCULATION_SOLUTION_LOW_TO_SETUP "
                "zone_id=%s task_id=%s",
                getattr(task, "zone_id", None),
                getattr(task, "id", None),
                exc_info=True,
            )
        _logger.info(
            "prepare_recirculation_check: раствор закончился (source=%s) → stop + startup setup zone_id=%s",
            source,
            task.zone_id,
        )
        return StageOutcome(kind="transition", next_stage="prepare_recirculation_solution_low_stop")

    async def _read_solution_min_level(self, *, task: Any, runtime: Any) -> dict[str, Any]:
        return await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime.solution_min_sensor_labels,
            threshold=runtime.level_switch_on_threshold,
            telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
            unavailable_error="two_tank_solution_min_level_unavailable",
            stale_error="two_tank_solution_min_level_stale",
            prefer_probe_snapshot=False,
        )

    async def _clear_correction_blocks(self, *, task: Any, reason: str) -> None:
        if self._pid_state_repository is None:
            return
        zone_id = int(task.zone_id)
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                await self._pid_state_repository.reset_no_effect_counts(zone_id=zone_id)
                _logger.info(
                    "prepare_recirculation_check: сброшен no_effect block zone_id=%s reason=%s",
                    zone_id,
                    reason,
                )
                return
            except Exception as exc:
                last_exc = exc
                _logger.warning(
                    "prepare_recirculation_check: не удалось сбросить no_effect_count "
                    "zone_id=%s attempt=%s",
                    zone_id,
                    attempt,
                    exc_info=True,
                )
        from ae3lite.infrastructure.metrics import CORRECTION_NO_EFFECT_RESET_FAILED

        CORRECTION_NO_EFFECT_RESET_FAILED.inc()
        raise TaskExecutionError(
            "corr_no_effect_reset_failed",
            f"Не удалось сбросить no_effect_count для зоны {zone_id} ({reason}): {last_exc}",
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
        per_pid_attempt_limit = max(ec_max_attempts, ph_max_attempts)
        overall_attempt_limit = self._required_correction_int(
            correction_cfg=correction_cfg,
            key="prepare_recirculation_max_correction_attempts",
        )
        corr = CorrectionState.build_default(
            corr_step="corr_check" if sensors_already_active else "corr_activate",
            max_attempts=min(overall_attempt_limit, per_pid_attempt_limit),
            ec_max_attempts=ec_max_attempts,
            ph_max_attempts=ph_max_attempts,
            activated_here=not sensors_already_active,
            stabilization_sec=self._required_correction_int(
                correction_cfg=correction_cfg,
                key="stabilization_sec",
            ),
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
        )
        return replace(corr, **self._probe_snapshot_correction_fields(task=task))

    async def _enter_recirc_pipeline_correction(
        self,
        *,
        task: Any,
        runtime: Any,
        return_stage_success: str,
        return_stage_fail: str,
    ) -> CorrectionState:
        """Open prepare pipeline at recirc_ca with baseline targets from DB or fail-closed."""
        import json

        from ae3lite.domain.errors import ErrorCodes, TaskExecutionError
        from ae3lite.domain.services.nutrient_pipeline import (
            ComponentTargets,
            compute_component_targets,
            pipeline_phase_for_index,
        )
        from ae3lite.infrastructure.repositories.prepare_baseline_repository import (
            PgPrepareBaselineRepository,
        )

        corr = self._build_correction_state(
            task=task,
            runtime=runtime,
            sensors_already_active=True,
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
        )
        targets: ComponentTargets | None = None
        baseline_id = None
        try:
            repo = PgPrepareBaselineRepository()
            row = await repo.fetch_latest_baseline(
                zone_id=int(task.zone_id),
                ae_task_id=int(getattr(task, "id", 0) or 0) or None,
            )
            if row is None:
                row = await repo.fetch_latest_baseline(zone_id=int(task.zone_id))
            if row is not None:
                baseline_id = int(row["id"]) if row.get("id") is not None else None
                raw_targets = row.get("component_targets_json")
                if isinstance(raw_targets, str):
                    raw_targets = json.loads(raw_targets)
                if isinstance(raw_targets, dict) and "T_ca" in raw_targets:
                    targets = ComponentTargets.from_mapping(raw_targets)
                else:
                    ratios = row.get("ratios_json")
                    if isinstance(ratios, str):
                        ratios = json.loads(ratios)
                    targets = compute_component_targets(
                        water_ec=float(row["water_ec"]),
                        water_ph=float(row.get("water_ph") or 0.0),
                        target_ec=float(row["target_ec"]),
                        ratios=ratios if isinstance(ratios, dict) else {},
                    )
        except Exception:
            _logger.warning(
                "prepare_recirc: не удалось загрузить baseline zone_id=%s",
                task.zone_id,
                exc_info=True,
            )
        if targets is None:
            raise TaskExecutionError(
                ErrorCodes.AE3_WATER_BASELINE_INVALID,
                "Для prepare_recirculation отсутствует water baseline (zone_prepare_baselines)",
            )
        phase0 = pipeline_phase_for_index(0)
        return replace(
            corr,
            pipeline_phase=phase0,
            active_component="calcium",
            water_ec=targets.water_ec,
            water_ph=targets.water_ph,
            nutrient_budget=targets.nutrient_budget,
            component_targets_json=targets.to_json(),
            baseline_id=baseline_id,
            ec_pid_frozen=False,
            dilute_attempts=0,
        )