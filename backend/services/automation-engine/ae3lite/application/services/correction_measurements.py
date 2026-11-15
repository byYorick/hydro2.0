"""Correction measurements: explicit collaborators, per-call task context."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.level_monitor import (
    coarse_solution_tank_level_percent,
    solution_tank_has_solution,
)
from ae3lite.application.services.correction_event_logger import CorrectionEventLogger
from ae3lite.application.services.correction_shared import (
    _STALE_RECHECK_DELAY_SEC,
    _logger,
    _MeasurementSnapshot,
    _pid_entry_or_none,
)
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.metric_window_validator import (
    SENSOR_OUT_OF_BOUNDS_REASON,
)
from ae3lite.infrastructure.metrics import (
    CORRECTION_OBSERVE_OUT_OF_BOUNDS,
)


@dataclass(frozen=True)
class CorrectionMeasurementsPorts:
    correction_retry_delay_sec: Callable[..., Any]
    decision_window_reader: Callable[[], Any]
    enter_correction_after_delay_or_interrupt: Callable[..., Any]
    freeze_pid_integral_clock: Callable[..., Awaitable[Any]]
    log_correction_event: Callable[..., Awaitable[Any]]
    maybe_reactivate_sensor_mode_after_empty_window: Callable[..., Awaitable[Any]]
    normalize_timestamp: Callable[..., Any]
    observe_fail_safe_transition: Callable[[], Any]
    pid_state: Callable[[], Any]
    read_level: Callable[[], Any]
    runtime_config: Callable[[], Any]
    serialize_metric_ts: Callable[..., Any]
    stage_elapsed_ms: Callable[[], Any]
    workflow_ready_values_match: Callable[[], Any]


class CorrectionMeasurements:
    def __init__(self, ports: CorrectionMeasurementsPorts) -> None:
        self._ports = ports

    async def read_measurements_or_interrupt(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        runtime: Mapping[str, Any],
        correction_cfg: Mapping[str, Any],
        process_cfg: Mapping[str, Any],
        pid_state: Mapping[str, Any],
        target_ph: float,
        target_ec: float,
        max_age: int,
    ) -> _MeasurementSnapshot | StageOutcome:
        """Read current pH/EC and validate the window, or return an interrupt.

        Pipeline steps (any one of them can short-circuit with a StageOutcome):
          1. ``wait_until`` cooldown — if the previous step scheduled a wait
             that has not elapsed yet, go back to sleep.
          2. Read PH and EC decision windows via ``DecisionWindowReader``.
             Stale telemetry becomes a ``CORRECTION_SKIPPED_FRESHNESS`` event
             + retry; non-ready window becomes ``CORRECTION_SKIPPED_WINDOW_NOT_READY``
             (or a sensor-mode reactivation via ``SensorModeController``).
          3. Guard against non-finite values (sensor glitch → retry).
          4. Read the solution-min level sensor and bail if the tank is empty
             (``CORRECTION_SKIPPED_WATER_LEVEL``).

        Returns a ``_MeasurementSnapshot`` if all checks pass, otherwise a
        ``StageOutcome`` the handler returns directly.
        """
        corr_wait_until = self._ports.normalize_timestamp(corr.wait_until)
        normalized_now = self._ports.normalize_timestamp(now)
        if corr_wait_until is not None and normalized_now < corr_wait_until:
            return self._ports.enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=max(1.0, (corr_wait_until - normalized_now).total_seconds()),
            )

        ph_cfg = self._ports.runtime_config().observation_config(
            kind="ph",
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_entry=_pid_entry_or_none(pid_state, "ph"),
        )
        ec_cfg = self._ports.runtime_config().observation_config(
            kind="ec",
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_entry=_pid_entry_or_none(pid_state, "ec"),
        )
        try:
            ph = await self._ports.decision_window_reader().read(
                zone_id=task.zone_id,
                sensor_type="PH",
                telemetry_max_age_sec=max_age,
                config=ph_cfg,
                now=now,
            )
            ec = await self._ports.decision_window_reader().read(
                zone_id=task.zone_id,
                sensor_type="EC",
                telemetry_max_age_sec=max_age,
                config=ec_cfg,
                now=now,
            )
        except TaskExecutionError as exc:
            if exc.code != "corr_telemetry_stale":
                raise
            retry_delay_sec = self._ports.correction_retry_delay_sec(
                correction_cfg=correction_cfg,
                key="telemetry_stale_retry_sec",
            )
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_FRESHNESS",
                task=task,
                corr=corr,
                payload={
                    "sensor_scope": "decision_window",
                    "reason": str(exc),
                    "retry_after_sec": retry_delay_sec,
                    "telemetry_max_age_sec": max_age,
                },
            )
            _logger.warning(
                "zone %s: телеметрия устарела во время correction check; повтор через %.1f с "
                "(task_id=%s correction_window_id=%s)",
                task.zone_id,
                retry_delay_sec,
                getattr(task, "id", None),
                CorrectionEventLogger.correction_window_id(task=task),
            )
            await self._ports.freeze_pid_integral_clock(task=task, pid_state=pid_state, now=now)
            return self._ports.enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=retry_delay_sec,
            )
        if not ph.ready or not ec.ready:
            reactivation_outcome = await self._ports.maybe_reactivate_sensor_mode_after_empty_window(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                ph=ph,
                ec=ec,
            )
            if reactivation_outcome is not None:
                return reactivation_outcome
            if ph.reason == SENSOR_OUT_OF_BOUNDS_REASON or ec.reason == SENSOR_OUT_OF_BOUNDS_REASON:
                CORRECTION_OBSERVE_OUT_OF_BOUNDS.inc()
            msg = self._ports.decision_window_reader().format_error(ph=ph, ec=ec)
            retry_delay_sec = self._ports.decision_window_reader().retry_delay_sec(
                correction_cfg=correction_cfg,
                ph=ph,
                ec=ec,
            )
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_WINDOW_NOT_READY",
                task=task,
                corr=corr,
                payload={
                    "sensor_scope": "decision_window",
                    "reason": msg,
                    "retry_after_sec": retry_delay_sec,
                    "ph_reason": ph.reason,
                    "ph_sample_count": ph.sample_count,
                    "ph_slope": ph.slope,
                    "ph_window_min_samples": ph.window_min_samples,
                    "ph_telemetry_period_sec": ph.telemetry_period_sec,
                    "ph_decision_window_sec": ph.decision_window_sec,
                    "ph_window_span_sec": ph.window_span_sec,
                    "ph_latest_sample_ts": self._ports.serialize_metric_ts(ph.latest_sample_ts),
                    "ph_since_ts": self._ports.serialize_metric_ts(ph.since_ts),
                    "ec_reason": ec.reason,
                    "ec_sample_count": ec.sample_count,
                    "ec_slope": ec.slope,
                    "ec_window_min_samples": ec.window_min_samples,
                    "ec_telemetry_period_sec": ec.telemetry_period_sec,
                    "ec_decision_window_sec": ec.decision_window_sec,
                    "ec_window_span_sec": ec.window_span_sec,
                    "ec_latest_sample_ts": self._ports.serialize_metric_ts(ec.latest_sample_ts),
                    "ec_since_ts": self._ports.serialize_metric_ts(ec.since_ts),
                },
            )
            _logger.warning(
                "zone %s: %s, повтор через %.1f с (task_id=%s correction_window_id=%s)",
                task.zone_id,
                msg,
                retry_delay_sec,
                getattr(task, "id", None),
                CorrectionEventLogger.correction_window_id(task=task),
            )
            await self._ports.freeze_pid_integral_clock(task=task, pid_state=pid_state, now=now)
            return self._ports.enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=retry_delay_sec,
            )

        current_ph = float(ph.value)
        current_ec = float(ec.value)
        workflow_ready = self._ports.workflow_ready_values_match()(
            task=task,
            runtime=runtime,
            current_ph=current_ph,
            current_ec=current_ec,
        )
        current_stage = str(getattr(task, "current_stage", "") or "").strip().lower()

        if not math.isfinite(current_ph) or not math.isfinite(current_ec):
            retry_delay_sec = self._ports.correction_retry_delay_sec(
                correction_cfg=correction_cfg,
                key="decision_window_retry_sec",
            )
            _logger.warning(
                "zone %s: некорректное telemetry value (ph=%s, ec=%s); повтор через %.1f с "
                "(task_id=%s correction_window_id=%s)",
                task.zone_id,
                current_ph,
                current_ec,
                retry_delay_sec,
                getattr(task, "id", None),
                CorrectionEventLogger.correction_window_id(task=task),
            )
            return self._ports.enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=retry_delay_sec,
            )

        solution_min = await self._ports.read_level()(
            task=task,
            zone_id=task.zone_id,
            labels=runtime.solution_min_sensor_labels,
            threshold=runtime.level_switch_on_threshold,
            telemetry_max_age_sec=max_age,
            unavailable_error="two_tank_solution_min_level_unavailable",
            stale_error="two_tank_solution_min_level_stale",
            stale_recheck_delay_sec=_STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )
        if not solution_tank_has_solution(solution_min):
            current_stage = str(getattr(task, "current_stage", "") or "").strip().lower()
            # Во время prepare_recirc опустошение бака → setup (fill), не бесконечный corr retry.
            if current_stage == "solution_fill_check":
                delay_ms = int(
                    getattr(
                        getattr(runtime, "fail_safe_guards", None),
                        "solution_fill_solution_min_check_delay_ms",
                        0,
                    )
                    or 0
                )
                # До guard-delay min ещё может быть выключен: бак только набирается.
                # После delay выключенный min — утечка, насос нельзя оставлять в fill.
                if self._ports.stage_elapsed_ms()(task=task, now=now) >= max(0, delay_ms):
                    await self._ports.log_correction_event(
                        zone_id=task.zone_id,
                        event_type="CORRECTION_INTERRUPTED_SOLUTION_LOW",
                        task=task,
                        corr=corr,
                        payload={
                            "reason": "solution_fill_leak_to_stop",
                            "next_stage": "solution_fill_leak_stop",
                            "current_ph": current_ph,
                            "current_ec": current_ec,
                        },
                    )
                    self._ports.observe_fail_safe_transition()(
                        task=task,
                        reason="solution_fill_leak",
                        source="correction",
                        next_stage="solution_fill_leak_stop",
                    )
                    return StageOutcome(
                        kind="transition",
                        next_stage="solution_fill_leak_stop",
                    )
            if current_stage == "prepare_recirculation_check":
                await self._ports.log_correction_event(
                    zone_id=task.zone_id,
                    event_type="CORRECTION_INTERRUPTED_SOLUTION_LOW",
                    task=task,
                    corr=corr,
                    payload={
                        "reason": "recirculation_solution_low_to_setup",
                        "next_stage": "prepare_recirculation_solution_low_stop",
                        "current_ph": current_ph,
                        "current_ec": current_ec,
                    },
                )
                await self._ports.pid_state().reset_no_effect_counts(
                    task=task,
                    corr=corr,
                    context="CORRECTION_INTERRUPTED_SOLUTION_LOW",
                )
                self._ports.observe_fail_safe_transition()(
                    task=task,
                    reason="recirculation_solution_low",
                    source="correction",
                    next_stage="prepare_recirculation_solution_low_stop",
                )
                return StageOutcome(
                    kind="transition",
                    next_stage="prepare_recirculation_solution_low_stop",
                )
            retry_delay_sec = self._ports.correction_retry_delay_sec(
                correction_cfg=correction_cfg,
                key="low_water_retry_sec",
            )
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_WATER_LEVEL",
                task=task,
                corr=corr,
                payload={
                    "water_level_pct": float(
                        coarse_solution_tank_level_percent(
                            solution_max_triggered=None,
                            solution_min_triggered=bool(solution_min.get("is_triggered")),
                        )
                        or 0
                    ),
                    "retry_after_sec": retry_delay_sec,
                    "current_ph": current_ph,
                    "current_ec": current_ec,
                    "target_ph": target_ph,
                    "target_ec": target_ec,
                    "target_ph_min": runtime.target_ph_min,
                    "target_ph_max": runtime.target_ph_max,
                    "target_ec_min": self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime),
                    "target_ec_max": self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime),
                },
            )
            _logger.warning(
                "zone %s: water level %.0f%% is below threshold; skipping correction for %.1fs",
                task.zone_id,
                float(
                    coarse_solution_tank_level_percent(
                        solution_max_triggered=None,
                        solution_min_triggered=bool(solution_min.get("is_triggered")),
                    )
                    or 0
                ),
                retry_delay_sec,
            )
            return self._ports.enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=retry_delay_sec,
            )

        return _MeasurementSnapshot(
            current_ph=current_ph,
            current_ec=current_ec,
            workflow_ready=workflow_ready,
            current_stage=current_stage,
        )
