"""IrrigationCheckHandler nutrient baseline: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class IrrigationCheckNutrientBaselinePorts:
    global_logger: Callable[..., Any]


class IrrigationCheckNutrientBaseline:
    def __init__(self, ports: IrrigationCheckNutrientBaselinePorts) -> None:
        self._ports = ports

    async def load_irrigation_nutrient_baseline(
        self,
        *,
        task: Any,
    ) -> tuple[str | None, int | None, float | None, float | None, float | None]:
        """Load latest zone prepare baseline for irrigation Ca/NPK T_step.

        Irrigation top-up may reuse zone-wide latest baseline (unlike prepare_recirc,
        which is fail-closed per task). Missing baseline → targets_json=None and
        planner falls back to runtime target_ec.
        """
        try:
            from ae3lite.infrastructure.repositories.prepare_baseline_repository import (
                PgPrepareBaselineRepository,
            )

            row = await PgPrepareBaselineRepository().fetch_latest_baseline(
                zone_id=int(task.zone_id),
            )
            if row is None:
                return None, None, None, None, None
            baseline_id = int(row["id"]) if row.get("id") is not None else None
            raw_targets = row.get("component_targets_json")
            if isinstance(raw_targets, str) and raw_targets.strip():
                targets_json = raw_targets
            elif isinstance(raw_targets, Mapping):
                import json

                targets_json = json.dumps(raw_targets, separators=(",", ":"), sort_keys=True)
            else:
                targets_json = None
            water_ec = float(row["water_ec"]) if row.get("water_ec") is not None else None
            water_ph = float(row["water_ph"]) if row.get("water_ph") is not None else None
            nutrient_budget = None
            if water_ec is not None and row.get("target_ec") is not None:
                nutrient_budget = round(float(row["target_ec"]) - float(water_ec), 6)
            return targets_json, baseline_id, water_ec, water_ph, nutrient_budget
        except Exception:
            self._ports.global_logger().warning(
                "irrigation_check: не удалось загрузить baseline zone_id=%s",
                getattr(task, "zone_id", None),
                exc_info=True,
            )
            return None, None, None, None, None
