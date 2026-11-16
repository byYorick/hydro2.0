"""CreateTaskFromIntentUseCase irrigation decision: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from ae3lite.domain.errors import ErrorCodes, TaskCreateError, PlannerConfigurationError
from ae3lite.config.runtime_plan_irrigation import resolve_irrigation_decision_config
from ae3lite.infrastructure.read_models.active_grow_cycle_order_sql import SQL_ACTIVE_GROW_CYCLE_ORDER_BY


@dataclass(frozen=True)
class IntentTaskIrrigationDecisionPorts:
    pass


class IntentTaskIrrigationDecision:
    def __init__(self, ports: IntentTaskIrrigationDecisionPorts) -> None:
        self._ports = ports

    async def resolve_irrigation_decision_snapshot(
        self,
        *,
        zone_id: int,
        meta: Any,
        conn: Any,
    ) -> dict[str, Any]:
        if str(getattr(meta, "task_type", "") or "").strip().lower() != "irrigation_start":
            return {}

        grow_cycle_row = await conn.fetchrow(
            f"""
            SELECT
                gc.id AS grow_cycle_id,
                gc.settings AS cycle_settings
            FROM grow_cycles gc
            WHERE gc.zone_id = $1
              AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
            {SQL_ACTIVE_GROW_CYCLE_ORDER_BY.strip()}
            LIMIT 1
            """,
            zone_id,
        )
        if grow_cycle_row is None:
            return {}

        cycle_settings = grow_cycle_row.get("cycle_settings")
        cycle_settings = cycle_settings if isinstance(cycle_settings, Mapping) else {}
        expected_bundle_revision = str(cycle_settings.get("bundle_revision") or "").strip()
        grow_cycle_id = int(grow_cycle_row.get("grow_cycle_id") or 0)
        if grow_cycle_id <= 0:
            return {}

        bundle_row = await conn.fetchrow(
            """
            SELECT bundle_revision, config
            FROM automation_effective_bundles
            WHERE scope_type = 'grow_cycle'
              AND scope_id = $1
            LIMIT 1
            """,
            grow_cycle_id,
        )
        if bundle_row is None:
            return {}

        actual_bundle_revision = str(bundle_row.get("bundle_revision") or "").strip()
        if expected_bundle_revision and actual_bundle_revision and expected_bundle_revision != actual_bundle_revision:
            raise TaskCreateError(
                ErrorCodes.AE3_SNAPSHOT_BUNDLE_INVALID,
                (
                    f"Несовпадение bundle_revision для grow_cycle_id={grow_cycle_id}: "
                    f"expected={expected_bundle_revision} actual={actual_bundle_revision}"
                ),
                details={
                    "zone_id": zone_id,
                    "grow_cycle_id": grow_cycle_id,
                    "expected_bundle_revision": expected_bundle_revision,
                    "actual_bundle_revision": actual_bundle_revision,
                },
            )

        bundle_config = bundle_row.get("config")
        if not isinstance(bundle_config, Mapping):
            return {}

        zone_bundle = bundle_config.get("zone")
        if not isinstance(zone_bundle, Mapping):
            return {}

        logic_profile = zone_bundle.get("logic_profile")
        if not isinstance(logic_profile, Mapping):
            return {}

        active_profile = logic_profile.get("active_profile")
        if not isinstance(active_profile, Mapping):
            return {}

        subsystems = active_profile.get("subsystems")
        if not isinstance(subsystems, Mapping):
            return {}

        irrigation = subsystems.get("irrigation")
        if not isinstance(irrigation, Mapping):
            return {}

        decision = irrigation.get("decision")
        if not isinstance(decision, Mapping):
            decision = {}

        strategy = str(decision.get("strategy") or "task").strip().lower() or "task"
        config = decision.get("config")
        try:
            config_mapping = resolve_irrigation_decision_config(config if isinstance(config, Mapping) else {})
        except PlannerConfigurationError as exc:
            raise TaskCreateError(ErrorCodes.AE3_SNAPSHOT_BUNDLE_INVALID, str(exc)) from exc
        return {
            "irrigation_decision_strategy": strategy,
            "irrigation_decision_config": config_mapping or None,
            "irrigation_bundle_revision": actual_bundle_revision or expected_bundle_revision or None,
        }

    def normalize_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
