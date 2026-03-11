"""Base handler with shared sensor/level/probe operations."""

from __future__ import annotations

import asyncio
from datetime import datetime
from time import monotonic
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

    def _deadline_reached(self, *, now: datetime, deadline: datetime | None) -> bool:
        if deadline is None:
            return False
        return _naive_dt(now) >= _naive_dt(deadline)

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
        state = await self._read_probe_state_with_retry(
            task=task,
            runtime=runtime,
            expected=expected,
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

    async def _read_probe_state_with_retry(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        expected: Mapping[str, bool],
    ) -> Mapping[str, Any]:
        max_age_sec = int(runtime.get("irr_state_max_age_sec") or 60)
        wait_timeout = self._coerce_float(runtime.get("irr_state_wait_timeout_sec"))
        poll_interval = self._coerce_float(runtime.get("irr_state_wait_poll_interval_sec"))
        timeout_sec = max(0.0, wait_timeout if wait_timeout is not None else 5.0)
        interval_sec = max(0.05, poll_interval if poll_interval is not None else 0.5)

        state = await self._runtime_monitor.read_latest_irr_state(
            zone_id=task.zone_id,
            max_age_sec=max_age_sec,
        )
        if not self._probe_state_needs_retry(state=state, expected=expected) or timeout_sec <= 0.0:
            return state

        deadline = monotonic() + timeout_sec
        while monotonic() < deadline:
            await asyncio.sleep(min(interval_sec, max(0.0, deadline - monotonic())))
            state = await self._runtime_monitor.read_latest_irr_state(
                zone_id=task.zone_id,
                max_age_sec=max_age_sec,
            )
            if not self._probe_state_needs_retry(state=state, expected=expected):
                return state
        return state

    def _probe_state_needs_retry(
        self,
        *,
        state: Mapping[str, Any],
        expected: Mapping[str, bool],
    ) -> bool:
        if not state.get("has_snapshot") or state.get("is_stale"):
            return True
        snapshot = state.get("snapshot")
        if not isinstance(snapshot, Mapping):
            return True
        for key, value in expected.items():
            if bool(snapshot.get(key)) != bool(value):
                return True
        return False

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
        tolerance = self._prepare_tolerance_for_task(task=task, runtime=runtime)
        ph_target = float(runtime["target_ph"])
        ec_target = float(runtime["target_ec"])
        ph_min = self._coerce_float(runtime.get("target_ph_min"))
        ph_max = self._coerce_float(runtime.get("target_ph_max"))
        ec_min = self._coerce_float(runtime.get("target_ec_min"))
        ec_max = self._coerce_float(runtime.get("target_ec_max"))
        current_ph = float(ph["value"])
        current_ec = float(ec["value"])
        if ph_min is None or ph_max is None:
            ph_tol = abs(ph_target) * (float(tolerance.get("ph_pct", 15)) / 100.0)
            ph_min = ph_target - ph_tol
            ph_max = ph_target + ph_tol
        if ec_min is None or ec_max is None:
            ec_tol = abs(ec_target) * (float(tolerance.get("ec_pct", 25)) / 100.0)
            ec_min = ec_target - ec_tol
            ec_max = ec_target + ec_tol
        return ph_min <= current_ph <= ph_max and ec_min <= current_ec <= ec_max

    def _prepare_tolerance_for_task(self, *, task: Any, runtime: Mapping[str, Any]) -> Mapping[str, Any]:
        tolerance_by_phase = runtime.get("prepare_tolerance_by_phase")
        if isinstance(tolerance_by_phase, Mapping):
            phase_key = self._runtime_phase_key(task=task)
            phase_cfg = tolerance_by_phase.get(phase_key)
            if isinstance(phase_cfg, Mapping):
                return phase_cfg
            generic_cfg = tolerance_by_phase.get("generic")
            if isinstance(generic_cfg, Mapping):
                return generic_cfg
        tolerance = runtime.get("prepare_tolerance")
        return tolerance if isinstance(tolerance, Mapping) else {}

    def _correction_config_for_task(self, *, task: Any, runtime: Mapping[str, Any]) -> Mapping[str, Any]:
        correction_by_phase = runtime.get("correction_by_phase")
        if isinstance(correction_by_phase, Mapping):
            phase_key = self._runtime_phase_key(task=task)
            phase_cfg = correction_by_phase.get(phase_key)
            if isinstance(phase_cfg, Mapping):
                return phase_cfg
            generic_cfg = correction_by_phase.get("generic")
            if isinstance(generic_cfg, Mapping):
                return generic_cfg
        correction = runtime.get("correction")
        return correction if isinstance(correction, Mapping) else {}

    def _runtime_phase_key(self, *, task: Any) -> str:
        workflow = getattr(task, "workflow", None)
        workflow_phase = getattr(workflow, "workflow_phase", None)
        phase = str(workflow_phase or getattr(task, "workflow_phase", "") or "").strip().lower()
        if phase in {"tank_filling", "solution_fill"}:
            return "solution_fill"
        if phase in {"tank_recirc", "prepare_recirculation"}:
            return "tank_recirc"
        if phase in {"irrigating", "irrigation", "irrig_recirc"}:
            return "irrigation"
        stage = str(getattr(task, "current_stage", "") or "").strip().lower()
        if stage.startswith("solution_fill"):
            return "solution_fill"
        if stage.startswith("prepare_recirculation"):
            return "tank_recirc"
        return "generic"

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

    def _coerce_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
