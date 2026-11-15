"""SolutionFillCheckHandler correction: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.domain.entities.workflow_state import CorrectionState


@dataclass(frozen=True)
class SolutionFillCorrectionPorts:
    load_existing_fill_baseline: Callable[..., Awaitable[Any]]
    probe_snapshot_correction_fields: Callable[[], Any]
    read_target_metric_window: Callable[[], Any]
    runtime_config: Callable[[], Any]
    global_logger: Callable[..., Any]


class SolutionFillCorrection:
    def __init__(self, ports: SolutionFillCorrectionPorts) -> None:
        self._ports = ports

    def build_correction_state(
        self,
        *,
        task: Any,
        runtime: Any,
        sensors_already_active: bool,
        return_stage_success: str,
        return_stage_fail: str,
    ) -> CorrectionState:
        correction_cfg = self._ports.runtime_config().correction_config_for_task(task=task, runtime=runtime)
        ec_max_attempts = self._ports.runtime_config().required_correction_int(
            correction_cfg=correction_cfg,
            key="max_ec_correction_attempts",
        )
        ph_max_attempts = self._ports.runtime_config().required_correction_int(
            correction_cfg=correction_cfg,
            key="max_ph_correction_attempts",
        )
        corr = CorrectionState.build_default(
            corr_step="corr_check" if sensors_already_active else "corr_activate",
            max_attempts=max(ec_max_attempts, ph_max_attempts),
            ec_max_attempts=ec_max_attempts,
            ph_max_attempts=0,  # no pH on fill
            activated_here=not sensors_already_active,
            stabilization_sec=self._ports.runtime_config().required_correction_int(
                correction_cfg=correction_cfg,
                key="stabilization_sec",
            ),
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
        )
        return replace(corr, **self._ports.probe_snapshot_correction_fields()(task=task))

    async def enter_fill_calcium_correction(
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

        corr = self.build_correction_state(
            task=task,
            runtime=runtime,
            sensors_already_active=True,
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
        )

        existing = await self._ports.load_existing_fill_baseline(task=task)
        if existing is not None:
            targets, baseline_id = existing
            self._ports.global_logger().info(
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
        correction_cfg = self._ports.runtime_config().correction_config_for_task(task=task, runtime=runtime)
        process_cfg = self._ports.runtime_config().process_cfg_for_task(task=task, runtime=runtime)
        ph_win = await self._ports.read_target_metric_window()(
            zone_id=task.zone_id,
            sensor_type="PH",
            telemetry_max_age_sec=max_age,
            config=self._ports.runtime_config().observation_config(
                kind="ph", correction_cfg=correction_cfg, process_cfg=process_cfg
            ),
            unavailable_error="two_tank_prepare_targets_unavailable",
            stale_error="two_tank_prepare_targets_stale",
            now=now,
        )
        ec_win = await self._ports.read_target_metric_window()(
            zone_id=task.zone_id,
            sensor_type="EC",
            telemetry_max_age_sec=max_age,
            config=self._ports.runtime_config().observation_config(
                kind="ec", correction_cfg=correction_cfg, process_cfg=process_cfg
            ),
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
        target_ec = float(self._ports.runtime_config().irrigation_ec_target(runtime=runtime))
        # Cumulative T_* must use FULL recipe ratios (tank_recirc), not the
        # fill-phase calcium-only map. Calcium-only → T_ca==T_full and breaks
        # dilute-on-overshoot (seed above T_ca never exceeds T_full*(1+pct)).
        ratios = self._ports.runtime_config().full_ec_component_ratios(runtime=runtime, correction_cfg=correction_cfg)
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
            self._ports.global_logger().warning(
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
            self._ports.global_logger().warning(
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
