"""GetZoneAutomationStateUseCase observability: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Optional

from ae3lite.application.services.automation_observability import build_automation_observability


@dataclass(frozen=True)
class ZoneStateObservabilityPorts:
    latest_irrigation_task: Callable[..., Awaitable[Any]]
    now: Callable[..., Any]


class ZoneStateObservability:
    def __init__(self, ports: ZoneStateObservabilityPorts) -> None:
        self._ports = ports

    async def attach_observability(
        self,
        payload: dict[str, Any],
        *,
        zone_id: int,
        task: Optional[Any],
        workflow_state: Optional[Any],
        telemetry: Mapping[str, Any],
        telemetry_fetch_ok: bool,
        node_rows: list[dict[str, Any]] | None,
        observability_thresholds: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        irrigation_task = await self._ports.latest_irrigation_task(zone_id=zone_id, task=task)
        observability = build_automation_observability(
            zone_id=zone_id,
            task=task,
            workflow_state=workflow_state,
            telemetry=telemetry,
            telemetry_fetch_ok=telemetry_fetch_ok,
            now=self._ports.now(),
            node_rows=node_rows or [],
            thresholds=observability_thresholds,
            irrigation_task=irrigation_task,
        )
        payload["observability"] = observability
        return payload

    def normalize_solution_tank_guard(self, guard_result: Any) -> dict[str, Any] | None:
        if not isinstance(guard_result, Mapping):
            return None
        level = guard_result.get("level")
        normalized_level = level if isinstance(level, Mapping) else {}
        sensor_label = (
            guard_result.get("sensor_label")
            or normalized_level.get("sensor_label")
            or guard_result.get("guard_sensor_label")
        )
        sample_ts = (
            guard_result.get("sample_ts") or normalized_level.get("sample_ts") or guard_result.get("guard_sample_ts")
        )
        normalized_sample_ts = sample_ts.isoformat() if hasattr(sample_ts, "isoformat") else sample_ts
        return {
            "checked": True,
            "reset": bool(guard_result.get("reset")),
            "reason": guard_result.get("reason"),
            "sensor_label": sensor_label,
            "sample_ts": normalized_sample_ts,
        }

    def solution_tank_guard_from_payload(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        reason = payload.get("guard_reason")
        sensor_label = payload.get("guard_sensor_label")
        sample_ts = payload.get("guard_sample_ts")
        if reason is None and sensor_label is None and sample_ts is None:
            return None
        return {
            "checked": True,
            "reset": True,
            "reason": reason,
            "sensor_label": sensor_label,
            "sample_ts": sample_ts,
        }

    def build_decision(self, task: Any) -> dict[str, Any] | None:
        outcome = getattr(task, "irrigation_decision_outcome", None)
        reason_code = getattr(task, "irrigation_decision_reason_code", None)
        strategy = getattr(task, "irrigation_decision_strategy", None)
        config = getattr(task, "irrigation_decision_config", None)
        bundle_revision = getattr(task, "irrigation_bundle_revision", None)
        degraded = getattr(task, "irrigation_decision_degraded", None)

        if (
            outcome is None
            and reason_code is None
            and strategy is None
            and config is None
            and bundle_revision is None
            and degraded is None
        ):
            return None

        return {
            "outcome": str(outcome).strip().lower() if outcome is not None else None,
            "reason_code": str(reason_code).strip() if reason_code is not None else None,
            "strategy": str(strategy).strip().lower() if strategy is not None else None,
            "config": dict(config) if isinstance(config, Mapping) else None,
            "bundle_revision": str(bundle_revision).strip() if bundle_revision is not None else None,
            "degraded": bool(degraded) if degraded is not None else None,
        }
