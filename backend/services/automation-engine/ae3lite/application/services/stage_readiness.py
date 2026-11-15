"""Stage component: readiness. Explicit ports; no handler dependency."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.services.correction_pipeline import irrigation_component_budget_guard
from ae3lite.domain.services.correction_planner import CorrectionPlanner

_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageReadinessPorts:
    read_target_metric_window: Callable[..., Awaitable[Any]]
    require_runtime_plan: Callable[..., Any]
    runtime_config: Callable[[], Any]


class StageReadiness:
    def __init__(self, ports: StageReadinessPorts) -> None:
        self._ports = ports

    async def targets_reached(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        snapshot = await self.target_outcome_snapshot(
            task=task,
            plan=plan,
            now=now,
            runtime=runtime,
        )
        return snapshot["chemistry_outcome"] == "targets_achieved"

    async def target_outcome_snapshot(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> Mapping[str, Any]:
        # Phase 5: accept hot-swapped runtime override.
        if runtime is None:
            runtime = self._ports.require_runtime_plan(plan=plan)
        max_age = int(runtime.telemetry_max_age_sec)
        correction_cfg = self._ports.runtime_config().correction_config_for_task(task=task, runtime=runtime)
        process_cfg = self._ports.runtime_config().process_cfg_for_task(task=task, runtime=runtime)
        ph = await self._ports.read_target_metric_window(
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
        tolerance = self._ports.runtime_config().prepare_tolerance_for_task(task=task, runtime=runtime)
        ph_target = self._ports.runtime_config().effective_ph_target(task=task, runtime=runtime)
        ec_target = self._ports.runtime_config().effective_ec_target(task=task, runtime=runtime)
        execution = runtime.irrigation_execution
        ec_component = str(getattr(execution, "irrigation_ec_component", None) or "none").strip().lower()
        corr = getattr(task, "correction", None)
        # none — операторский pH-only. calcium/npk остаётся целью даже если
        # доза заморожена: frozen не вычёркивает измерение из outcome.
        ec_enabled = ec_component in {"calcium", "npk"}
        allow_ec = ec_enabled
        allow_ph = True
        ec: Mapping[str, Any] = {"ready": True, "value": ec_target, "reason": "contour_disabled"}
        if allow_ec:
            ec = await self._ports.read_target_metric_window(
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
        block_reason = None
        if ec_enabled and bool(getattr(corr, "ec_pid_frozen", False)):
            measured_ec = ec.get("value") if bool(ec.get("ready")) else None
            block_reason = self.irrigation_ec_dosing_block_reason(
                corr=corr,
                ec_component=ec_component,
                current_ec=float(measured_ec) if measured_ec is not None else None,
                full_target_ec=float(ec_target),
                correction_cfg=correction_cfg,
                pid_configs=getattr(runtime, "pid_configs", {}),
            )
        if not ph["ready"] or not ec["ready"]:
            reasons = [
                str(metric.get("reason") or "window_not_ready") for metric in (ph, ec) if not bool(metric.get("ready"))
            ]
            return self.apply_ec_dosing_block(
                {
                    "chemistry_outcome": "unknown",
                    "targets_reached": None,
                    "reason": ",".join(reasons) or "target_window_not_ready",
                    "current_ph": ph.get("value"),
                    "current_ec": ec.get("value") if allow_ec else None,
                    "target_ph": ph_target,
                    "target_ec": ec_target,
                    "allow_ph": allow_ph,
                    "allow_ec": allow_ec,
                    "irrigation_ec_component": ec_component,
                },
                block_reason,
            )
        current_ph = float(ph["value"])
        current_ec = float(ec["value"])
        planner = CorrectionPlanner()
        deadbands = planner.resolve_deadbands(
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=ph_target,
            target_ec=ec_target,
            correction_config=correction_cfg,
            pid_configs=getattr(runtime, "pid_configs", {}),
            allow_ec=allow_ec,
            allow_ph=allow_ph,
        )
        targets_reached = planner.is_within_tolerance(
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=ph_target,
            target_ec=ec_target,
            ph_tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                tolerance=tolerance,
                key="ph_pct",
            ),
            ec_tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                tolerance=tolerance,
                key="ec_pct",
            ),
            correction_config=correction_cfg,
            pid_configs=getattr(runtime, "pid_configs", {}),
            allow_ec=allow_ec,
            allow_ph=allow_ph,
        )
        return self.apply_ec_dosing_block(
            {
                "chemistry_outcome": ("targets_achieved" if targets_reached else "targets_not_achieved"),
                "targets_reached": targets_reached,
                "reason": "within_pid_deadband" if targets_reached else "outside_pid_deadband",
                "current_ph": current_ph,
                "current_ec": current_ec if allow_ec else None,
                "target_ph": ph_target,
                "target_ec": ec_target,
                "ph_deadband": float(deadbands["ph"]),
                "ec_deadband": float(deadbands["ec"]) if allow_ec else None,
                "allow_ph": allow_ph,
                "allow_ec": allow_ec,
                "irrigation_ec_component": ec_component,
            },
            block_reason,
        )

    def irrigation_ec_dosing_block_reason(
        self,
        *,
        corr: Any,
        ec_component: str,
        current_ec: float | None,
        full_target_ec: float,
        correction_cfg: Mapping[str, Any],
        pid_configs: Mapping[str, Any],
    ) -> str | None:
        """Диагностическая причина запрета дозирования включённого EC.

        ``irrigation_ec_component=none`` сюда не попадает. Заморозка сама по
        себе не причина: её подтверждает budget guard (нет baseline, baseline
        устарел или бюджет компонента исчерпан).
        """
        if corr is None:
            return "component_budget_unavailable"
        probe_ec = float(current_ec) if current_ec is not None else float(full_target_ec) - 1_000_000.0
        deadbands = CorrectionPlanner().resolve_deadbands(
            current_ph=0.0,
            current_ec=probe_ec,
            target_ph=0.0,
            target_ec=float(full_target_ec),
            correction_config=correction_cfg,
            pid_configs=pid_configs,
            allow_ec=True,
            allow_ph=False,
        )
        guard = irrigation_component_budget_guard(
            corr=replace(corr, pipeline_phase=f"irrigation_{ec_component}"),
            current_ec=probe_ec,
            full_target_ec=float(full_target_ec),
            ec_deadband=float(deadbands["ec"]),
        )
        if bool(guard.get("allowed", True)):
            return None
        reason = str(guard.get("reason") or "").strip()
        return reason or "ec_dosing_blocked"

    @staticmethod
    def apply_ec_dosing_block(
        snapshot: Mapping[str, Any],
        block_reason: str | None,
    ) -> dict[str, Any]:
        """Не превращать запрет дозы включённого EC в targets_achieved."""
        updated = dict(snapshot)
        if not block_reason:
            return updated
        updated["ec_dosing_blocked"] = True
        updated["ec_dosing_block_reason"] = block_reason
        outcome = str(updated.get("chemistry_outcome") or "")
        prior = str(updated.get("reason") or "").strip()
        if outcome != "targets_achieved":
            updated["reason"] = block_reason if not prior else f"{block_reason},{prior}"
        # Dosing permission cannot override fresh measurements in either
        # direction: a frozen loop may already be within the full deadband.
        return updated

    async def workflow_ready_reached(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        # Phase 5: accept hot-swapped runtime from handler. Falls back to
        # plan.runtime when caller didn't opt into live-mode reassignment.
        if runtime is None:
            runtime = self._ports.require_runtime_plan(plan=plan)
        max_age = int(runtime.telemetry_max_age_sec)
        correction_cfg = self._ports.runtime_config().correction_config_for_task(task=task, runtime=runtime)
        process_cfg = self._ports.runtime_config().process_cfg_for_task(task=task, runtime=runtime)
        ph = await self._ports.read_target_metric_window(
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
        ec = await self._ports.read_target_metric_window(
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
            return False
        return self.workflow_ready_values_match(
            task=task,
            runtime=runtime,
            current_ph=float(ph["value"]),
            current_ec=float(ec["value"]),
        )

    def recirc_pipeline_open(self, task: Any) -> bool:
        """True, пока sequential recirc (Ca→pH→Mg→…→T_full) не завершён.

        Prepare-share band в этот момент — цель текущего шага, не готовность рецепта.
        """
        corr = getattr(task, "correction", None)
        phase = str(getattr(corr, "pipeline_phase", None) or "").strip().lower()
        return phase.startswith("recirc_")

    def workflow_ready_values_match(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
    ) -> bool:
        if self.recirc_pipeline_open(task):
            return self.irrigation_band_values_match(
                task=task,
                runtime=runtime,
                current_ph=current_ph,
                current_ec=current_ec,
            )
        return self.phase_ready_values_match(
            task=task,
            runtime=runtime,
            current_ph=current_ph,
            current_ec=current_ec,
        )

    def phase_ready_values_match(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
    ) -> bool:
        """Ready по phase-effective targets (prepare EC в solution_fill/tank_recirc)."""
        tolerance = self._ports.runtime_config().prepare_tolerance_for_task(task=task, runtime=runtime)
        ph_target = self._ports.runtime_config().effective_ph_target(task=task, runtime=runtime)
        ec_target = self._ports.runtime_config().effective_ec_target(task=task, runtime=runtime)
        ph_ok = self.value_matches_ready_band(
            current=current_ph,
            target=ph_target,
            tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                tolerance=tolerance, key="ph_pct"
            ),
            explicit_min=self._ports.runtime_config().effective_ph_min(task=task, runtime=runtime),
            explicit_max=self._ports.runtime_config().effective_ph_max(task=task, runtime=runtime),
        )
        ec_ok = self.value_matches_ready_band(
            current=current_ec,
            target=ec_target,
            tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                tolerance=tolerance, key="ec_pct"
            ),
            explicit_min=self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime),
            explicit_max=self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime),
        )
        return ph_ok and ec_ok

    def irrigation_band_values_match(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
    ) -> bool:
        """Ready по полному irrigation EC/pH band (без prepare NPK-share)."""
        tolerance = self._ports.runtime_config().prepare_tolerance_for_task(task=task, runtime=runtime)
        ph_ok = self.value_matches_ready_band(
            current=current_ph,
            target=self._ports.runtime_config().effective_ph_target(task=task, runtime=runtime),
            tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                tolerance=tolerance, key="ph_pct"
            ),
            explicit_min=self._ports.runtime_config().effective_ph_min(task=task, runtime=runtime),
            explicit_max=self._ports.runtime_config().effective_ph_max(task=task, runtime=runtime),
        )
        ec_ok = self.value_matches_ready_band(
            current=current_ec,
            target=self._ports.runtime_config().irrigation_ec_target(runtime=runtime),
            tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                tolerance=tolerance, key="ec_pct"
            ),
            explicit_min=self._ports.runtime_config().irrigation_ec_min(runtime=runtime),
            explicit_max=self._ports.runtime_config().irrigation_ec_max(runtime=runtime),
        )
        return ph_ok and ec_ok

    def irrigation_ready_short_circuit(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
    ) -> bool:
        """Skip prepare when раствор уже в irrigation-band и EC выше prepare-target.

        Post-irrigation / DIAGNOSTICS re-entry: prepare NPK-band уже пройден (EC
        planner не дозирует вниз). Не срабатывает при EC ниже prepare — первый setup
        по-прежнему идёт в prepare. Не подменяет ``workflow_ready`` phase-band.
        """
        phase = self._ports.runtime_config().runtime_phase_key(task=task)
        if phase not in {"solution_fill", "tank_recirc"}:
            return False
        if not self.irrigation_band_values_match(
            task=task,
            runtime=runtime,
            current_ph=current_ph,
            current_ec=current_ec,
        ):
            return False
        prepare_ec = float(self._ports.runtime_config().effective_ec_target(task=task, runtime=runtime))
        return math.isfinite(prepare_ec) and current_ec > prepare_ec

    async def finish_ready_or_irrigation_short_circuit(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        """True если phase-ready **или** irrigation short-circuit (fresh telemetry)."""
        if runtime is None:
            runtime = self._ports.require_runtime_plan(plan=plan)
        max_age = int(runtime.telemetry_max_age_sec)
        correction_cfg = self._ports.runtime_config().correction_config_for_task(task=task, runtime=runtime)
        process_cfg = self._ports.runtime_config().process_cfg_for_task(task=task, runtime=runtime)
        ph = await self._ports.read_target_metric_window(
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
        ec = await self._ports.read_target_metric_window(
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
            return False
        current_ph = float(ph["value"])
        current_ec = float(ec["value"])
        tolerance = self._ports.runtime_config().prepare_tolerance_for_task(task=task, runtime=runtime)
        target_reached = CorrectionPlanner().is_within_tolerance(
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=self._ports.runtime_config().effective_ph_target(task=task, runtime=runtime),
            target_ec=self._ports.runtime_config().effective_ec_target(task=task, runtime=runtime),
            ph_tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                tolerance=tolerance,
                key="ph_pct",
            ),
            ec_tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                tolerance=tolerance,
                key="ec_pct",
            ),
            correction_config=correction_cfg,
            pid_configs=getattr(runtime, "pid_configs", {}),
        )
        # Открытый recirc-pipeline нельзя закрыть кальциевой prepare-band:
        # pH в фазовом окне и EC ≈ T_ca иначе завершают рецепт до Mg/NPK/micro.
        if target_reached and not self.recirc_pipeline_open(task):
            return True
        return self.irrigation_ready_short_circuit(
            task=task,
            runtime=runtime,
            current_ph=current_ph,
            current_ec=current_ec,
        )

    def value_matches_ready_band(
        self,
        *,
        current: float,
        target: float,
        tolerance_pct: float,
        explicit_min: float | None,
        explicit_max: float | None,
    ) -> bool:
        if (
            explicit_min is not None
            and explicit_max is not None
            and math.isfinite(explicit_min)
            and math.isfinite(explicit_max)
            and explicit_min <= explicit_max
        ):
            return explicit_min <= current <= explicit_max
        tolerance = abs(target) * (float(tolerance_pct) / 100.0)
        return (target - tolerance) <= current <= (target + tolerance)
