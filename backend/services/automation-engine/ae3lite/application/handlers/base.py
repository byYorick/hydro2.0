"""Base handler with shared sensor/level/probe operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.domain.errors import TaskExecutionError


def _naive_dt(dt: datetime) -> datetime:
    """Return datetime with tzinfo stripped (naive). Works on both aware and naive inputs."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


class BaseStageHandler:
    """Provides reusable sensor-reading helpers shared by check-type handlers.

    Subclasses implement ``run()`` and return :class:`StageOutcome`.
    """

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        command_gateway: Any,
    ) -> None:
        self._runtime_monitor = runtime_monitor
        self._command_gateway = command_gateway

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        raise NotImplementedError

    # ── Probe IRR state (hardware safety check) ─────────────────────

    async def _probe_irr_state(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        expected: Mapping[str, bool],
    ) -> None:
        """Send probe command and assert hardware state matches expectations."""
        probe_cmds = plan.named_plans.get("irr_state_probe", ())
        if not probe_cmds:
            return
        result = await self._command_gateway.run_batch(
            task=task, commands=probe_cmds, now=now,
        )
        if not result["success"]:
            raise TaskExecutionError(
                str(result["error_code"]), str(result["error_message"]),
            )
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        state = await self._runtime_monitor.read_latest_irr_state(
            zone_id=task.zone_id,
            max_age_sec=int(runtime.get("irr_state_max_age_sec") or 60),
        )
        if not state["has_snapshot"]:
            raise TaskExecutionError(
                "irr_state_unavailable", "IRR state snapshot unavailable",
            )
        if state["is_stale"]:
            raise TaskExecutionError(
                "irr_state_stale", "IRR state snapshot stale",
            )
        snapshot = state["snapshot"] if isinstance(state["snapshot"], Mapping) else {}
        for key, value in expected.items():
            if bool(snapshot.get(key)) != bool(value):
                raise TaskExecutionError(
                    "irr_state_mismatch",
                    f"IRR state mismatch for {key}: expected={value}, got={snapshot.get(key)}",
                )

    # ── Level switch reading ────────────────────────────────────────

    async def _read_level(
        self,
        *,
        task: Any,
        zone_id: int,
        labels: Sequence[str],
        threshold: float,
        telemetry_max_age_sec: int,
        unavailable_error: str,
        stale_error: str,
    ) -> Mapping[str, Any]:
        level = await self._runtime_monitor.read_level_switch(
            zone_id=zone_id,
            sensor_labels=labels,
            threshold=threshold,
            telemetry_max_age_sec=telemetry_max_age_sec,
        )
        if not level["has_level"]:
            raise TaskExecutionError(
                unavailable_error, f"Level sensor unavailable: {labels}",
            )
        if level["is_stale"]:
            raise TaskExecutionError(
                stale_error, f"Level sensor stale: {labels}",
            )
        return level

    # ── PH/EC target evaluation ─────────────────────────────────────

    async def _targets_reached(self, *, task: Any, plan: Any) -> bool:
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        max_age = int(runtime.get("telemetry_max_age_sec") or 300)
        ph = await self._runtime_monitor.read_metric(
            zone_id=task.zone_id, sensor_type="PH", telemetry_max_age_sec=max_age,
        )
        ec = await self._runtime_monitor.read_metric(
            zone_id=task.zone_id, sensor_type="EC", telemetry_max_age_sec=max_age,
        )
        if not ph["has_value"] or not ec["has_value"]:
            raise TaskExecutionError(
                "two_tank_prepare_targets_unavailable",
                "PH/EC telemetry unavailable for target evaluation",
            )
        if ph["is_stale"] or ec["is_stale"]:
            raise TaskExecutionError(
                "two_tank_prepare_targets_stale",
                "PH/EC telemetry stale for target evaluation",
            )
        tolerance = runtime.get("prepare_tolerance") if isinstance(runtime.get("prepare_tolerance"), Mapping) else {}
        ph_target = float(runtime["target_ph"])
        ec_target = float(runtime["target_ec"])
        return (
            abs(float(ph["value"]) - ph_target) <= abs(ph_target) * (float(tolerance.get("ph_pct", 15)) / 100.0)
            and abs(float(ec["value"]) - ec_target) <= abs(ec_target) * (float(tolerance.get("ec_pct", 25)) / 100.0)
        )

    # ── Sensor consistency check (max=1, min=0 → error) ────────────

    async def _check_sensor_consistency(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        min_labels_key: str,
        min_unavailable_error: str,
        min_stale_error: str,
    ) -> None:
        """Read min-level sensor and assert it's triggered (consistency with max)."""
        level = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime[min_labels_key],
            threshold=runtime["level_switch_on_threshold"],
            telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
            unavailable_error=min_unavailable_error,
            stale_error=min_stale_error,
        )
        if not level["is_triggered"]:
            raise TaskExecutionError(
                "sensor_state_inconsistent",
                f"Tank sensors inconsistent: max=1 min=0 ({min_labels_key})",
            )
