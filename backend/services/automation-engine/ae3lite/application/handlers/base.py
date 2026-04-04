"""Base handler with shared sensor/level/probe operations."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from statistics import median
from time import monotonic
from typing import Any, Mapping, Optional, Sequence

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.domain.errors import TaskExecutionError
from common.db import create_zone_event


_logger = logging.getLogger(__name__)


def _utc_naive_dt(dt: datetime) -> datetime:
    """Normalize datetimes to UTC-naive before comparisons."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo is not None else dt


class BaseStageHandler:
    """Provides reusable sensor-reading helpers shared by check-type handlers.

    Subclasses implement ``run()`` and return :class:`StageOutcome`.
    """

    _IRR_STATE_PROBE_RETRY_COUNT = 1
    _IRR_STATE_PROBE_RETRY_DELAY_SEC = 0.5

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
        return _utc_naive_dt(now) >= _utc_naive_dt(deadline)

    def _remaining_stage_time_sec(self, *, now: datetime, deadline: datetime | None) -> float | None:
        if deadline is None:
            return None
        remaining = (_utc_naive_dt(deadline) - _utc_naive_dt(now)).total_seconds()
        return max(0.0, remaining)

    def _irr_probe_deadline_budget_sec(self, *, runtime: Mapping[str, Any]) -> float:
        # Real test-node command/state roundtrip can legitimately take a few seconds.
        # If we start a fresh IRR probe too close to the stage deadline, the command
        # can fail in polling after deadline instead of taking the intended stage path.
        wait_timeout = self._coerce_float(runtime.get("irr_state_wait_timeout_sec"))
        attempts = 1 + self._IRR_STATE_PROBE_RETRY_COUNT
        # Budget must cover both the storage_state command roundtrip and the follow-up
        # snapshot wait. On real hardware the combined path can easily exceed 5s,
        # and a single republish is allowed for transient MQTT probe loss.
        single_attempt_budget = (wait_timeout if wait_timeout is not None else 0.0) + 2.0
        base_budget = (single_attempt_budget * attempts) + (
            self._IRR_STATE_PROBE_RETRY_DELAY_SEC * self._IRR_STATE_PROBE_RETRY_COUNT
        )
        return max(8.0, base_budget)

    def _deadline_too_close_for_irr_probe(
        self,
        *,
        now: datetime,
        deadline: datetime | None,
        runtime: Mapping[str, Any],
    ) -> bool:
        remaining = self._remaining_stage_time_sec(now=now, deadline=deadline)
        if remaining is None:
            return False
        return remaining <= self._irr_probe_deadline_budget_sec(runtime=runtime)

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
            raise TaskExecutionError(
                "irr_state_probe_plan_missing",
                f"IRR state probe command plan is missing for stage={getattr(task, 'current_stage', None)}",
            )
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        last_state: Mapping[str, Any] = {}
        last_probe_cmd_id: str | None = None
        total_attempts = 1 + self._IRR_STATE_PROBE_RETRY_COUNT

        for attempt_index in range(total_attempts):
            result = await self._command_gateway.run_batch(
                task=task,
                commands=probe_cmds,
                now=now,
                track_task_state=False,
            )
            if not result["success"]:
                raise TaskExecutionError(
                    str(result["error_code"]), str(result["error_message"]),
                )
            probe_cmd_id = self._extract_probe_cmd_id(result=result)
            state = await self._read_probe_state_with_retry(
                task=task,
                runtime=runtime,
                expected=expected,
                expected_cmd_id=probe_cmd_id,
            )
            last_state = state
            last_probe_cmd_id = probe_cmd_id
            if not self._probe_state_needs_retry(
                state=state,
                expected=expected,
                expected_cmd_id=probe_cmd_id,
            ):
                return
            if attempt_index + 1 < total_attempts:
                await asyncio.sleep(self._IRR_STATE_PROBE_RETRY_DELAY_SEC)

        reason = self._classify_probe_failure_reason(
            state=last_state,
            expected=expected,
            expected_cmd_id=last_probe_cmd_id,
        )
        await self._log_probe_failure_event(
            task=task,
            expected=expected,
            expected_cmd_id=last_probe_cmd_id,
            state=last_state,
            reason=reason,
        )
        if reason == "stale":
            raise TaskExecutionError(
                "irr_state_stale", "IRR state snapshot stale",
            )
        if reason == "mismatch":
            snapshot = last_state["snapshot"] if isinstance(last_state["snapshot"], Mapping) else {}
            for key, value in expected.items():
                if bool(snapshot.get(key)) != bool(value):
                    raise TaskExecutionError(
                        "irr_state_mismatch",
                        f"IRR state mismatch for {key}: expected={value}, got={snapshot.get(key)}",
                    )
        raise TaskExecutionError(
            "irr_state_unavailable", "IRR state snapshot unavailable",
        )

    def _classify_probe_failure_reason(
        self,
        *,
        state: Mapping[str, Any],
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> str:
        if not state.get("has_snapshot"):
            return "unavailable"
        if state.get("is_stale"):
            return "stale"
        if expected_cmd_id is not None and str(state.get("cmd_id") or "").strip() != expected_cmd_id:
            return "cmd_id_mismatch"
        snapshot = state.get("snapshot")
        if not isinstance(snapshot, Mapping):
            return "unavailable"
        for key, value in expected.items():
            if bool(snapshot.get(key)) != bool(value):
                return "mismatch"
        return "unavailable"

    async def _read_probe_state_with_retry(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> Mapping[str, Any]:
        max_age_sec = int(runtime.get("irr_state_max_age_sec") or 60)
        wait_timeout = self._coerce_float(runtime.get("irr_state_wait_timeout_sec"))
        poll_interval = self._coerce_float(runtime.get("irr_state_wait_poll_interval_sec"))
        timeout_sec = max(0.0, wait_timeout if wait_timeout is not None else 5.0)
        interval_sec = max(0.05, poll_interval if poll_interval is not None else 0.5)

        state = await self._runtime_monitor.read_latest_irr_state(
            zone_id=task.zone_id,
            max_age_sec=max_age_sec,
            expected_cmd_id=expected_cmd_id,
        )
        if not self._probe_state_needs_retry(
            state=state,
            expected=expected,
            expected_cmd_id=expected_cmd_id,
        ) or timeout_sec <= 0.0:
            return state

        deadline = monotonic() + timeout_sec
        while monotonic() < deadline:
            await asyncio.sleep(min(interval_sec, max(0.0, deadline - monotonic())))
            state = await self._runtime_monitor.read_latest_irr_state(
                zone_id=task.zone_id,
                max_age_sec=max_age_sec,
                expected_cmd_id=expected_cmd_id,
            )
            if not self._probe_state_needs_retry(
                state=state,
                expected=expected,
                expected_cmd_id=expected_cmd_id,
            ):
                return state
        return state

    def _probe_state_needs_retry(
        self,
        *,
        state: Mapping[str, Any],
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> bool:
        if not state.get("has_snapshot") or state.get("is_stale"):
            return True
        if expected_cmd_id is not None and str(state.get("cmd_id") or "").strip() != expected_cmd_id:
            return True
        snapshot = state.get("snapshot")
        if not isinstance(snapshot, Mapping):
            return True
        for key, value in expected.items():
            if bool(snapshot.get(key)) != bool(value):
                return True
        return False

    def _extract_probe_cmd_id(self, *, result: Mapping[str, Any]) -> str | None:
        statuses = result.get("command_statuses")
        if not isinstance(statuses, Sequence):
            return None
        for item in reversed(statuses):
            if not isinstance(item, Mapping):
                continue
            probe_cmd_id = str(item.get("legacy_cmd_id") or "").strip()
            if probe_cmd_id:
                return probe_cmd_id
        return None

    async def _log_probe_failure_event(
        self,
        *,
        task: Any,
        expected: Mapping[str, bool],
        expected_cmd_id: str | None,
        state: Mapping[str, Any],
        reason: str,
    ) -> None:
        snapshot = state.get("snapshot") if isinstance(state.get("snapshot"), Mapping) else {}
        try:
            await create_zone_event(
                int(task.zone_id),
                "IRR_STATE_PROBE_FAILED",
                {
                    "stage": str(getattr(task, "current_stage", "") or ""),
                    "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
                    "reason": str(reason or ""),
                    "expected": dict(expected),
                    "expected_cmd_id": expected_cmd_id,
                    "has_snapshot": bool(state.get("has_snapshot")),
                    "is_stale": bool(state.get("is_stale")),
                    "cmd_id": state.get("cmd_id"),
                    "snapshot": dict(snapshot) if isinstance(snapshot, Mapping) else {},
                },
            )
        except Exception:
            _logger.warning(
                "AE3 failed to log IRR_STATE_PROBE_FAILED zone_id=%s task_id=%s stage=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                str(getattr(task, "current_stage", "") or ""),
                exc_info=True,
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

    async def _targets_reached(self, *, task: Any, plan: Any, now: datetime) -> bool:
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        max_age = int(runtime.get("telemetry_max_age_sec") or 300)
        correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
        process_cfg = self._process_cfg_for_task(task=task, runtime=runtime)
        ph = await self._read_target_metric_window(
            zone_id=task.zone_id,
            sensor_type="PH",
            telemetry_max_age_sec=max_age,
            config=self._observation_config(kind="ph", correction_cfg=correction_cfg, process_cfg=process_cfg),
            unavailable_error="two_tank_prepare_targets_unavailable",
            stale_error="two_tank_prepare_targets_stale",
            now=now,
        )
        ec = await self._read_target_metric_window(
            zone_id=task.zone_id,
            sensor_type="EC",
            telemetry_max_age_sec=max_age,
            config=self._observation_config(kind="ec", correction_cfg=correction_cfg, process_cfg=process_cfg),
            unavailable_error="two_tank_prepare_targets_unavailable",
            stale_error="two_tank_prepare_targets_stale",
            now=now,
        )
        if not ph["ready"] or not ec["ready"]:
            return False
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

    async def _read_target_metric_window(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        telemetry_max_age_sec: int,
        config: Mapping[str, Any],
        unavailable_error: str,
        stale_error: str,
        now: datetime,
    ) -> Mapping[str, Any]:
        since_ts = self._decision_window_since_ts(now=now, config=config)
        window = await self._runtime_monitor.read_metric_window(
            zone_id=zone_id,
            sensor_type=sensor_type,
            since_ts=since_ts,
            telemetry_max_age_sec=telemetry_max_age_sec,
        )
        if not window["has_sensor"]:
            raise TaskExecutionError(
                unavailable_error,
                f"{sensor_type} telemetry unavailable for target evaluation",
            )
        if window["is_stale"]:
            raise TaskExecutionError(
                stale_error,
                f"{sensor_type} telemetry stale for target evaluation",
            )
        summary = self._summarize_metric_window(
            samples=window["samples"],
            window_min_samples=int(config["window_min_samples"]),
            stability_max_slope=float(config["stability_max_slope"]),
        )
        if not summary["ready"]:
            return {"ready": False, "reason": summary.get("reason")}
        return {
            "ready": True,
            "value": summary["value"],
            "sample_count": summary["sample_count"],
            "slope": summary["slope"],
        }

    def _decision_window_since_ts(self, *, now: datetime, config: Mapping[str, Any]) -> datetime:
        # Include one telemetry period of slack so a late but still-fresh sample
        # does not collapse a 3-sample window into 2 samples on real hardware.
        lookback_sec = int(config["decision_window_sec"]) + int(config.get("telemetry_period_sec", 0) or 0)
        return now - timedelta(seconds=max(1, lookback_sec))

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

    def _process_cfg_for_task(self, *, task: Any, runtime: Mapping[str, Any]) -> Mapping[str, Any]:
        process_calibrations = runtime.get("process_calibrations")
        if not isinstance(process_calibrations, Mapping):
            return {}
        phase_key = self._runtime_phase_key(task=task)
        process_cfg = process_calibrations.get(phase_key)
        if isinstance(process_cfg, Mapping):
            return process_cfg
        generic_cfg = process_calibrations.get("generic")
        if isinstance(generic_cfg, Mapping):
            return generic_cfg
        if phase_key == "irrigation":
            solution_fill_cfg = process_calibrations.get("solution_fill")
            if isinstance(solution_fill_cfg, Mapping):
                return solution_fill_cfg
        return {}

    def _observation_config(
        self,
        *,
        kind: str,
        correction_cfg: Mapping[str, Any],
        process_cfg: Mapping[str, Any],
        pid_entry: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        controllers = correction_cfg.get("controllers") if isinstance(correction_cfg.get("controllers"), Mapping) else {}
        controller_cfg = controllers.get(kind) if isinstance(controllers.get(kind), Mapping) else {}
        controller_observe_cfg = (
            controller_cfg.get("observe") if isinstance(controller_cfg.get("observe"), Mapping) else {}
        )
        process_meta = process_cfg.get("meta") if isinstance(process_cfg.get("meta"), Mapping) else {}
        observe_cfg = process_meta.get("observe") if isinstance(process_meta.get("observe"), Mapping) else {}

        telemetry_period_sec = max(
            1,
            int(
                observe_cfg.get("telemetry_period_sec")
                or controller_observe_cfg.get("telemetry_period_sec")
                or controller_cfg.get("telemetry_period_sec")
                or 2
            ),
        )
        window_min_samples = max(
            2,
            int(
                observe_cfg.get("window_min_samples")
                or controller_observe_cfg.get("window_min_samples")
                or controller_cfg.get("window_min_samples")
                or 3
            ),
        )
        decision_window_sec = max(
            telemetry_period_sec * window_min_samples,
            int(
                observe_cfg.get("decision_window_sec")
                or controller_observe_cfg.get("decision_window_sec")
                or controller_cfg.get("decision_window_sec")
                or 0
            ),
        )
        transport_delay_sec = int(
            process_cfg.get("transport_delay_sec")
            or controller_observe_cfg.get("transport_delay_sec")
            or controller_cfg.get("transport_delay_sec")
            or 0
        )
        settle_sec = int(
            process_cfg.get("settle_sec")
            or controller_observe_cfg.get("settle_sec")
            or controller_cfg.get("settle_sec")
            or 0
        )
        if transport_delay_sec <= 0 or settle_sec <= 0:
            raise TaskExecutionError(
                "corr_process_calibration_missing",
                f"Process calibration transport_delay_sec/settle_sec is required for {kind}",
            )

        adaptive_timing = self._adaptive_observation_timing(pid_entry=pid_entry)
        learned_transport = adaptive_timing.get("transport_delay_sec")
        learned_settle = adaptive_timing.get("settle_sec")
        if learned_transport is not None:
            transport_delay_sec = max(transport_delay_sec, learned_transport)
        if learned_settle is not None:
            settle_sec = max(settle_sec, learned_settle)
        return {
            "transport_delay_sec": transport_delay_sec,
            "settle_sec": settle_sec,
            "hold_window_sec": transport_delay_sec + settle_sec,
            "telemetry_period_sec": telemetry_period_sec,
            "window_min_samples": window_min_samples,
            "decision_window_sec": decision_window_sec,
            "observe_poll_sec": max(
                1,
                int(
                    observe_cfg.get("observe_poll_sec")
                    or controller_observe_cfg.get("observe_poll_sec")
                    or controller_cfg.get("observe_poll_sec")
                    or telemetry_period_sec
                ),
            ),
            "min_effect_fraction": max(
                0.01,
                float(
                    observe_cfg.get("min_effect_fraction")
                    or controller_observe_cfg.get("min_effect_fraction")
                    or controller_cfg.get("min_effect_fraction")
                    or 0.25
                ),
            ),
            "stability_max_slope": max(
                0.0001,
                float(
                    observe_cfg.get("stability_max_slope")
                    or controller_observe_cfg.get("stability_max_slope")
                    or controller_cfg.get("stability_max_slope")
                    or (0.02 if kind == "ph" else 0.05)
                ),
            ),
            "no_effect_limit": max(
                1,
                int(
                    observe_cfg.get("no_effect_consecutive_limit")
                    or controller_observe_cfg.get("no_effect_consecutive_limit")
                    or controller_cfg.get("no_effect_consecutive_limit")
                    or 3
                ),
            ),
        }

    def _adaptive_observation_timing(self, *, pid_entry: Mapping[str, Any] | None) -> dict[str, int]:
        if not isinstance(pid_entry, Mapping):
            return {}
        stats = pid_entry.get("stats")
        if not isinstance(stats, Mapping):
            return {}
        adaptive = stats.get("adaptive")
        if not isinstance(adaptive, Mapping):
            return {}
        timing = adaptive.get("timing")
        if not isinstance(timing, Mapping):
            return {}
        try:
            observations = int(timing.get("observations") or adaptive.get("observations") or 0)
        except (TypeError, ValueError):
            observations = 0
        if observations < 3:
            return {}

        result: dict[str, int] = {}
        for key in ("transport_delay_sec", "settle_sec"):
            raw = timing.get(f"{key}_ema")
            try:
                value = int(round(float(raw)))
            except (TypeError, ValueError):
                continue
            if value > 0:
                result[key] = value
        return result

    def _summarize_metric_window(
        self,
        *,
        samples: Any,
        window_min_samples: int,
        stability_max_slope: float,
    ) -> dict[str, Any]:
        sample_list = list(samples) if isinstance(samples, (list, tuple)) else []
        if len(sample_list) < window_min_samples:
            return {"ready": False, "reason": "insufficient_samples"}
        values = [float(item["value"]) for item in sample_list if item.get("value") is not None]
        if len(values) < window_min_samples:
            return {"ready": False, "reason": "insufficient_values"}
        first_ts = sample_list[0].get("ts")
        last_ts = sample_list[-1].get("ts")
        slope = 0.0
        if isinstance(first_ts, datetime) and isinstance(last_ts, datetime) and last_ts > first_ts:
            dt = max(1.0, (last_ts - first_ts).total_seconds())
            slope = (float(sample_list[-1]["value"]) - float(sample_list[0]["value"])) / dt
        if abs(slope) > stability_max_slope:
            return {"ready": False, "reason": "unstable", "slope": slope}
        return {
            "ready": True,
            "value": float(median(values)),
            "sample_count": len(values),
            "slope": slope,
        }

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
