"""SolutionFillCheckHandler ec baseline: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class SolutionFillEcBaselinePorts:
    load_existing_fill_baseline: Callable[..., Awaitable[Any]]
    read_target_metric_window: Callable[[], Any]
    require_runtime_plan: Callable[[], Any]
    runtime_config: Callable[[], Any]
    global_logger: Callable[..., Any]


class SolutionFillEcBaseline:
    def __init__(self, ports: SolutionFillEcBaselinePorts) -> None:
        self._ports = ports

    async def fill_ec_target_reached(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        """EC-only gate for solution_fill: compare to T_ca when known, skip pH."""
        if runtime is None:
            runtime = self._ports.require_runtime_plan()(plan=plan)
        max_age = int(runtime.telemetry_max_age_sec)
        correction_cfg = self._ports.runtime_config().correction_config_for_task(task=task, runtime=runtime)
        process_cfg = self._ports.runtime_config().process_cfg_for_task(task=task, runtime=runtime)
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
        if not ec.get("ready"):
            return False
        ec_target = await self.resolve_fill_ec_target(task=task, runtime=runtime)
        tolerance = self._ports.runtime_config().prepare_tolerance_for_task(task=task, runtime=runtime)
        ec_tol = abs(ec_target) * (
            self._ports.runtime_config().required_prepare_tolerance_pct(tolerance=tolerance, key="ec_pct") / 100.0
        )
        current_ec = float(ec["value"])
        return (ec_target - ec_tol) <= current_ec <= (ec_target + ec_tol)

    async def resolve_fill_ec_target(self, *, task: Any, runtime: Any) -> float:
        """Prefer T_ca from existing fill baseline; else effective/prepare EC."""
        from ae3lite.domain.services.nutrient_pipeline import (
            ComponentTargets,
            active_ec_target_for_corr,
        )

        existing = await self._ports.load_existing_fill_baseline(task=task)
        if existing is not None:
            targets, _baseline_id = existing
            return active_ec_target_for_corr(
                pipeline_phase="fill_ca",
                active_component="calcium",
                targets=targets,
                fallback_target_ec=float(self._ports.runtime_config().irrigation_ec_target(runtime=runtime)),
            )
        corr = getattr(task, "correction", None)
        if corr is not None:
            targets = ComponentTargets.from_json(getattr(corr, "component_targets_json", None))
            if targets is not None:
                return active_ec_target_for_corr(
                    pipeline_phase=getattr(corr, "pipeline_phase", None) or "fill_ca",
                    active_component=getattr(corr, "active_component", None) or "calcium",
                    targets=targets,
                    fallback_target_ec=float(self._ports.runtime_config().irrigation_ec_target(runtime=runtime)),
                )
        return float(self._ports.runtime_config().effective_ec_target(task=task, runtime=runtime))

    @staticmethod
    def corr_has_fill_baseline(corr: Any) -> bool:
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

    async def load_existing_fill_baseline(
        self,
        *,
        task: Any,
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
        if self.corr_has_fill_baseline(corr):
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
            self._ports.global_logger().warning(
                "solution_fill: не удалось загрузить existing baseline zone_id=%s",
                getattr(task, "zone_id", None),
                exc_info=True,
            )
            return None
