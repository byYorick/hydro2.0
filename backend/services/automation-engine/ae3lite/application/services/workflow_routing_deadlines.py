"""WorkflowRouter deadlines: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ae3lite.application.handlers.flow_path_guard import (
    MANUAL_HOLD_STAGE,
)
from ae3lite.application.services.workflow_routing_shared import (
    _DEFAULT_CORRECTION_SLACK_SEC,
    _DEFAULT_MANUAL_HOLD_TIMEOUT_SEC,
    _MAX_CORRECTION_SLACK_SEC,
    _MAX_STAGE_TOTAL_SEC,
    logger,
)
from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.errors import PlannerConfigurationError


@dataclass(frozen=True)
class WorkflowRoutingDeadlinesPorts:
    pass


class WorkflowRoutingDeadlines:
    def __init__(self, ports: WorkflowRoutingDeadlinesPorts) -> None:
        self._ports = ports

    def compute_deadline(
        self,
        *,
        task: Any,
        stage_def: Any,
        runtime: RuntimePlan,
        now: datetime,
        plan: Any = None,
        irrigation_start_entered_at: datetime | None = None,
    ) -> Optional[datetime]:
        """Вычисляет `stage_deadline_at` по timeout-ключам из runtime-конфига."""
        if stage_def.name == "irrigation_check":
            irrigation_runtime = runtime.irrigation_execution
            requested_duration_sec = getattr(task, "irrigation_requested_duration_sec", None)
            if requested_duration_sec is None:
                requested_duration_sec = getattr(runtime, "irrigation_requested_duration_sec", None)
            if requested_duration_sec is None:
                requested_duration_sec = irrigation_runtime.duration_sec
            if requested_duration_sec is not None:
                try:
                    hydraulic_duration_sec = max(1, int(requested_duration_sec))
                    correction_slack_sec = (
                        max(0, int(irrigation_runtime.correction_slack_sec))
                        if bool(irrigation_runtime.correction_during_irrigation)
                        else 0
                    )
                    total_sec = hydraulic_duration_sec + correction_slack_sec
                    if irrigation_runtime.stage_timeout_sec is not None:
                        total_sec = min(total_sec, max(1, int(irrigation_runtime.stage_timeout_sec)))
                    total_sec = min(total_sec, _MAX_STAGE_TOTAL_SEC)
                except (TypeError, ValueError):
                    total_sec = None
                else:
                    if isinstance(irrigation_start_entered_at, datetime):
                        anchor = self.normalize_utc_naive(irrigation_start_entered_at)
                        deadline = anchor + timedelta(seconds=total_sec)
                    else:
                        deadline = now + timedelta(seconds=total_sec)
                    if now.tzinfo is not None:
                        return deadline.replace(tzinfo=timezone.utc)
                    return deadline

            explicit_timeout = irrigation_runtime.stage_timeout_sec
            if explicit_timeout is not None:
                try:
                    return now + timedelta(seconds=max(1, int(explicit_timeout)))
                except (TypeError, ValueError):
                    pass
            raise PlannerConfigurationError(
                "irrigation_check deadline не задан: отсутствуют "
                "irrigation_requested_duration_sec, irrigation_execution.duration_sec "
                "и irrigation_execution.stage_timeout_sec.",
                code="irrigation_check_deadline_unconfigured",
            )
        if stage_def.name == "solution_fill_check":
            base_raw = runtime.solution_fill_timeout_sec
            if base_raw is None:
                return None
            try:
                base_sec = max(1, int(base_raw))
            except (TypeError, ValueError):
                return None
            slack_raw = getattr(runtime, "solution_fill_correction_slack_sec", None)
            if slack_raw is None:
                slack = _DEFAULT_CORRECTION_SLACK_SEC
            else:
                try:
                    slack = max(0, min(_MAX_CORRECTION_SLACK_SEC, int(slack_raw)))
                except (TypeError, ValueError):
                    slack = _DEFAULT_CORRECTION_SLACK_SEC
            total_sec = min(base_sec + slack, _MAX_STAGE_TOTAL_SEC)
            return now + timedelta(seconds=total_sec)
        if stage_def.name in {"solution_topup_check", "solution_topup_start"}:
            base_raw = getattr(runtime, "solution_topup_timeout_sec", None) or runtime.solution_fill_timeout_sec
            if base_raw is None:
                return None
            try:
                base_sec = max(1, int(base_raw))
            except (TypeError, ValueError):
                return None
            return now + timedelta(seconds=min(base_sec, _MAX_STAGE_TOTAL_SEC))
        if stage_def.name in {"solution_drain_check", "solution_drain_start"}:
            base_raw = getattr(runtime, "solution_drain_timeout_sec", None) or runtime.solution_fill_timeout_sec
            if base_raw is None:
                return None
            try:
                base_sec = max(1, int(base_raw))
            except (TypeError, ValueError):
                return None
            return now + timedelta(seconds=min(base_sec, _MAX_STAGE_TOTAL_SEC))
        if stage_def.name in {"await_operator_drain_confirm", "await_operator_refill_confirm"}:
            base_raw = getattr(runtime, "solution_change_operator_confirm_timeout_sec", None)
            if base_raw is None:
                return None
            try:
                base_sec = max(60, int(base_raw))
            except (TypeError, ValueError):
                return None
            return now + timedelta(seconds=min(base_sec, _MAX_STAGE_TOTAL_SEC))
        if stage_def.name == MANUAL_HOLD_STAGE:
            return now + timedelta(seconds=min(_DEFAULT_MANUAL_HOLD_TIMEOUT_SEC, _MAX_STAGE_TOTAL_SEC))
        if stage_def.name == "prepare_recirculation_check":
            # Базовое окно берётся из retry-конфига; inline EC/pH-коррекциям нужно
            # дополнительное wall time на реальном пути HL→MQTT→node.
            base_raw = runtime.prepare_recirculation_timeout_sec
            if base_raw is None:
                return None
            try:
                base_sec = max(1, int(base_raw))
            except (TypeError, ValueError):
                return None
            slack_raw = getattr(runtime, "prepare_recirculation_correction_slack_sec", None)
            if slack_raw is None:
                slack = _DEFAULT_CORRECTION_SLACK_SEC
            else:
                try:
                    slack = max(0, min(_MAX_CORRECTION_SLACK_SEC, int(slack_raw)))
                except (TypeError, ValueError):
                    slack = _DEFAULT_CORRECTION_SLACK_SEC
            total_sec = min(base_sec + slack, _MAX_STAGE_TOTAL_SEC)
            return now + timedelta(seconds=total_sec)
        if stage_def.timeout_key is None:
            return None
        timeout_sec = getattr(runtime, stage_def.timeout_key, None)
        if timeout_sec is None:
            # Audit F13: a missing timeout_key in runtime config is almost
            # always a config error, not a "stage has no deadline" intent.
            # Log it once so ops see the anomaly in the scheduler log rather
            # than silently getting an unbounded stage duration.
            logger.warning(
                "workflow_router: timeout_key=%r для stage=%s отсутствует в runtime; "
                "stage будет без deadline до исправления конфига",
                stage_def.timeout_key,
                stage_def.name,
            )
            return None
        return now + timedelta(seconds=int(timeout_sec))

    def normalize_utc_naive(self, value: datetime) -> datetime:
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value

    def deadline_reached(self, *, now: datetime, deadline: datetime | None) -> bool:
        if deadline is None:
            return False
        return self.normalize_utc_naive(now) >= self.normalize_utc_naive(deadline)
