"""SensorModeController — управление sensor mode в correction cycle.

Extracted from ``CorrectionHandler`` as part of the God-Object decomposition
(audit finding B1). Owns the "activate/deactivate sensor mode" pipeline that
was scattered across ``_build_sensor_mode_commands``,
``_ensure_sensor_mode_active_for_dosing``,
``_maybe_reactivate_sensor_mode_after_empty_window``,
``_window_empty_for_sensor_reactivation`` and
``_stage_keeps_sensor_mode_active``.

Responsibilities:
  * Compile sensor mode activation/deactivation ``PlannedCommand`` batches
    from ``plan.named_plans``.
  * Dispatch those batches through the injected ``command_gateway``.
  * Log ``CORRECTION_SENSOR_MODE_REACTIVATED`` events via the shared
    ``CorrectionEventLogger`` so handler tests that monkeypatch
    ``create_zone_event`` still observe the write.
  * Decide whether a reactivation is warranted (empty window, non-owned
    stages, stage type).

The controller does **not** own FSM routing — it returns ``None`` or a
``StageOutcome`` that the handler applies.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.correction_event_logger import CorrectionEventLogger
from ae3lite.application.services.decision_window_reader import DecisionWindowResult
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError

_logger = logging.getLogger(__name__)

#: Stages that keep their sensors hot outside correction windows and must
#: NOT be re-activated by correction. Irrigation keeps sensors active for
#: real-time monitoring; recovery reads an already-active fleet.
_STAGES_WITH_PERSISTENT_SENSOR_MODE: frozenset[str] = frozenset({
    "irrigation_check",
    "irrigation_recovery_check",
})


class SensorModeController:
    """Dispatches sensor mode commands and decides reactivation transitions."""

    def __init__(
        self,
        *,
        command_gateway: Any,
        event_logger: CorrectionEventLogger,
    ) -> None:
        self._command_gateway = command_gateway
        self._event_logger = event_logger

    # ── Public API used by the handler ──────────────────────────────

    def build_commands(
        self,
        *,
        plan: Any,
        cmd: str,
        params: Mapping[str, Any],
    ) -> tuple[PlannedCommand, ...]:
        """Render activation/deactivation batch from ``plan.named_plans`` templates.

        Returns an empty tuple if the plan does not declare a matching source
        key — callers are expected to treat this as "nothing to dispatch".
        """
        raw_named = getattr(plan, "named_plans", None)
        named = raw_named if isinstance(raw_named, Mapping) else {}
        source_key = (
            "sensor_mode_activate"
            if cmd == "activate_sensor_mode"
            else "sensor_mode_deactivate"
        )
        templates = named.get(source_key, ())
        return tuple(
            PlannedCommand(
                step_no=t.step_no,
                node_uid=t.node_uid,
                channel=t.channel,
                payload={"cmd": cmd, "params": dict(params)},
            )
            for t in templates
        )

    async def ensure_active_for_dosing(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        failed_node_uid: str | None,
        failed_channel: str | None,
        retry_cmd: str,
    ) -> Any:
        """Re-activate sensor mode right before issuing a dose.

        Returns the (possibly updated) task. No-op and returns the original
        task if the plan has no activation template. Logs
        ``CORRECTION_SENSOR_MODE_REACTIVATED`` with ``reason=pre_dose_reactivation``.
        """
        sensor_cmds = self.build_commands(
            plan=plan,
            cmd="activate_sensor_mode",
            params={"stabilization_time_sec": corr.stabilization_sec},
        )
        if not sensor_cmds:
            return task
        current_task = await self._dispatch(
            task=task, commands=sensor_cmds, now=now,
        )
        await self._event_logger.log(
            zone_id=task.zone_id,
            event_type="CORRECTION_SENSOR_MODE_REACTIVATED",
            task=task,
            corr=corr,
            payload={
                "reason": "pre_dose_reactivation",
                "failed_node_uid": failed_node_uid,
                "failed_channel": failed_channel,
                "retry_cmd": retry_cmd,
                "stabilization_sec": corr.stabilization_sec,
            },
        )
        return current_task

    async def maybe_reactivate_after_empty_window(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        ph: DecisionWindowResult,
        ec: DecisionWindowResult,
    ) -> StageOutcome | None:
        """Re-activate sensors when the decision window came up empty.

        Returns ``None`` if reactivation is not warranted (sensors are owned
        by the correction itself, stage keeps them active, or the window was
        not actually empty). Otherwise dispatches the activation batch and
        returns a ``StageOutcome`` that routes the task back to
        ``corr_wait_stable`` with the fresh stabilization delay.
        """
        if corr.activated_here:
            return None
        if self.stage_keeps_active(task=task):
            return None
        if not (
            self.window_empty_for_reactivation(metric=ph)
            or self.window_empty_for_reactivation(metric=ec)
        ):
            return None

        sensor_cmds = self.build_commands(
            plan=plan,
            cmd="activate_sensor_mode",
            params={"stabilization_time_sec": corr.stabilization_sec},
        )
        if not sensor_cmds:
            return None

        current_task = await self._dispatch(
            task=task, commands=sensor_cmds, now=now,
        )
        await self._event_logger.log(
            zone_id=task.zone_id,
            event_type="CORRECTION_SENSOR_MODE_REACTIVATED",
            task=task,
            corr=corr,
            payload={
                "ph_reason": ph.reason,
                "ph_sample_count": ph.sample_count,
                "ec_reason": ec.reason,
                "ec_sample_count": ec.sample_count,
                "stabilization_sec": corr.stabilization_sec,
            },
        )
        _logger.warning(
            "zone %s: decision window is empty, re-activating sensor mode and waiting %ss",
            task.zone_id,
            corr.stabilization_sec,
        )
        next_corr = replace(corr, corr_step="corr_wait_stable")
        return StageOutcome(
            kind="enter_correction",
            correction=next_corr,
            due_delay_sec=corr.stabilization_sec,
            task_override=current_task if current_task is not task else None,
        )

    # ── Pure predicates (static; testable in isolation) ─────────────

    @staticmethod
    def stage_keeps_active(*, task: Any) -> bool:
        """True for stages that leave sensors active outside correction windows."""
        stage = str(getattr(task, "current_stage", "") or "").strip().lower()
        return stage in _STAGES_WITH_PERSISTENT_SENSOR_MODE

    @staticmethod
    def window_empty_for_reactivation(*, metric: DecisionWindowResult) -> bool:
        """True when the window is empty in a way that merits sensor reactivation.

        Empty-window semantics: ``ready=False`` AND ``reason=insufficient_samples``
        AND actual sample_count ≤ 0. Any other ``not-ready`` state means sensors
        are publishing, just not stable enough yet — reactivation would be a
        pointless command round-trip.
        """
        if metric.ready:
            return False
        if (metric.reason or "").strip().lower() != "insufficient_samples":
            return False
        if metric.sample_count is None:
            return True
        try:
            return int(metric.sample_count) <= 0
        except (TypeError, ValueError):
            return False

    # ── Private helpers ─────────────────────────────────────────────

    async def _dispatch(
        self,
        *,
        task: Any,
        commands: tuple[PlannedCommand, ...],
        now: datetime,
    ) -> Any:
        result = await self._command_gateway.run_batch(
            task=task,
            commands=commands,
            now=now,
        )
        if not result["success"]:
            raise TaskExecutionError(
                str(result["error_code"]),
                str(result["error_message"]),
            )
        return result.get("task") or task
