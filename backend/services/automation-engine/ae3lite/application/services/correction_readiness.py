"""Correction readiness: explicit collaborators, per-call task context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ae3lite.application.services.correction_pipeline import (
    pipeline_dose_flags,
)


@dataclass(frozen=True)
class CorrectionReadinessPorts:
    irrigation_ready_short_circuit: Callable[[], Any]
    planner: Callable[[], Any]
    read_target_metric_window: Callable[[], Any]
    require_runtime_plan: Callable[[], Any]
    runtime_config: Callable[[], Any]
    workflow_ready_values_match: Callable[[], Any]


class CorrectionReadiness:
    def __init__(self, ports: CorrectionReadinessPorts) -> None:
        self._ports = ports

    @staticmethod
    def readiness_event_payload(
        *,
        targets_in_tolerance: bool,
        workflow_ready: bool,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "targets_in_tolerance": targets_in_tolerance,
            "workflow_ready": workflow_ready,
            # Legacy alias: downstream routing for solution_fill used workflow_ready.
            "targets_reached": workflow_ready,
            **extra,
        }

    async def resolve_correction_readiness_flags(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> tuple[bool, bool] | None:
        if runtime is None:
            runtime = self._ports.require_runtime_plan()(plan=plan)
        max_age = int(runtime.telemetry_max_age_sec)
        correction_cfg = self._ports.runtime_config().correction_config_for_task(task=task, runtime=runtime)
        process_cfg = self._ports.runtime_config().process_cfg_for_task(task=task, runtime=runtime)
        ph = await self._ports.read_target_metric_window()(
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
        ec = await self._ports.read_target_metric_window()(
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
        if not ph["ready"] or not ec["ready"]:
            return None
        current_ph = float(ph["value"])
        current_ec = float(ec["value"])
        tolerance = self._ports.runtime_config().prepare_tolerance_for_task(task=task, runtime=runtime)
        target_ph = self._ports.runtime_config().effective_ph_target(task=task, runtime=runtime)
        target_ec = self._ports.runtime_config().effective_ec_target(task=task, runtime=runtime)
        dose_flags = pipeline_dose_flags(getattr(task, "correction", None))
        targets_in_tolerance = self._ports.planner().is_within_tolerance(
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            ph_tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                tolerance=tolerance, key="ph_pct"
            ),
            ec_tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                tolerance=tolerance, key="ec_pct"
            ),
            ph_min=self._ports.runtime_config().effective_ph_min(task=task, runtime=runtime),
            ph_max=self._ports.runtime_config().effective_ph_max(task=task, runtime=runtime),
            ec_min=self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime),
            ec_max=self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime),
            correction_config=correction_cfg,
            pid_configs=getattr(runtime, "pid_configs", {}),
            allow_ec=bool(dose_flags.get("allow_ec", True)),
            allow_ph=bool(dose_flags.get("allow_ph", True)),
        )
        workflow_ready = self._ports.workflow_ready_values_match()(
            task=task,
            runtime=runtime,
            current_ph=current_ph,
            current_ec=current_ec,
        )
        if not workflow_ready and self._ports.irrigation_ready_short_circuit()(
            task=task,
            runtime=runtime,
            current_ph=current_ph,
            current_ec=current_ec,
        ):
            workflow_ready = True
        return targets_in_tolerance, workflow_ready
