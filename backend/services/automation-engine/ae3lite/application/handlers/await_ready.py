"""Стадия await-ready для задач полива."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import (
    IRRIGATION_WAIT_READY_DURATION_SECONDS,
    IRRIGATION_WAIT_READY_POLL,
    IRRIGATION_WAIT_READY_RESOLVED,
    IRRIGATION_WAIT_READY_TIMEOUT,
)
from common.biz_alerts import send_biz_alert
from common.db import create_zone_event


_WAIT_READY_TIMEOUT_SEC = max(30, int(os.getenv("AE_IRRIGATION_WAIT_READY_SEC", "1800")))
_WAIT_READY_POLL_SEC = max(1, int(os.getenv("AE_IRRIGATION_WAIT_READY_POLL_SEC", "10")))

_logger = logging.getLogger(__name__)


def _topology_label(task: Any) -> str:
    raw = str(getattr(task, "topology", "") or "").strip().lower()
    return raw if raw else "unknown"


def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0)


class AwaitReadyHandler(BaseStageHandler):
    def __init__(self, *, runtime_monitor: Any, command_gateway: Any, task_repository: Any) -> None:
        super().__init__(runtime_monitor=runtime_monitor, command_gateway=command_gateway)
        self._task_repository = task_repository

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        runtime = plan.runtime if hasattr(plan, "runtime") else {}
        workflow_phase = str(runtime.get("zone_workflow_phase") or "").strip().lower()
        topo = _topology_label(task)
        grow_cycle_id = runtime.get("grow_cycle_id")
        if grow_cycle_id is not None:
            try:
                grow_cycle_id = int(grow_cycle_id)
            except (TypeError, ValueError):
                grow_cycle_id = None

        if workflow_phase == "ready":
            wf = getattr(task, "workflow", None)
            entered = getattr(wf, "stage_entered_at", None) if wf is not None else None
            if isinstance(entered, datetime):
                dur = (_naive_utc(now) - _naive_utc(entered)).total_seconds()
                IRRIGATION_WAIT_READY_DURATION_SECONDS.labels(topology=topo).observe(max(0.0, float(dur)))
            IRRIGATION_WAIT_READY_RESOLVED.labels(topology=topo).inc()
            return StageOutcome(kind="transition", next_stage="decision_gate")

        deadline = task.irrigation_wait_ready_deadline_at
        if deadline is None:
            owner = str(getattr(task, "claimed_by", "") or "").strip()
            if owner == "":
                raise TaskExecutionError(
                    "irrigation_wait_ready_missing_owner",
                    f"У задачи {getattr(task, 'id', None)} отсутствует owner на этапе await_ready",
                )
            updated = await self._task_repository.update_irrigation_runtime(
                task_id=int(task.id),
                owner=owner,
                now=now,
                irrigation_wait_ready_deadline_at=now.replace(microsecond=0) + timedelta(seconds=_WAIT_READY_TIMEOUT_SEC),
            )
            if updated is None:
                raise TaskExecutionError(
                    "irrigation_wait_ready_deadline_persist_failed",
                    f"Не удалось сохранить deadline wait_ready для задачи {getattr(task, 'id', None)}",
                )
            IRRIGATION_WAIT_READY_POLL.labels(topology=topo).inc()
            return StageOutcome(kind="poll", due_delay_sec=_WAIT_READY_POLL_SEC)

        if self._deadline_reached(now=now, deadline=deadline):
            IRRIGATION_WAIT_READY_TIMEOUT.labels(topology=topo).inc()
            zone_id = int(getattr(task, "zone_id", 0) or 0)
            task_id = int(getattr(task, "id", 0) or 0)
            _logger.warning(
                "irrigation_wait_ready_timeout zone_id=%s task_id=%s snapshot_workflow_phase=%s grow_cycle_id=%s",
                zone_id,
                task_id,
                workflow_phase or "(empty)",
                grow_cycle_id,
            )
            try:
                await create_zone_event(
                    zone_id,
                    "IRRIGATION_WAIT_READY_TIMEOUT",
                    {
                        "task_id": task_id,
                        "workflow_phase": workflow_phase,
                        "grow_cycle_id": grow_cycle_id,
                        "deadline_at": deadline.isoformat() if isinstance(deadline, datetime) else None,
                    },
                )
            except Exception:
                _logger.warning(
                    "AE3 не смог записать IRRIGATION_WAIT_READY_TIMEOUT zone_id=%s task_id=%s",
                    zone_id,
                    task_id,
                    exc_info=True,
                )
            try:
                await send_biz_alert(
                    code="biz_irrigation_wait_ready_timeout",
                    alert_type="AE3 Irrigation Wait Ready Timeout",
                    message="Полив превысил время ожидания на этапе await_ready: зона не перешла в READY.",
                    severity="warning",
                    zone_id=zone_id,
                    dedupe_key=f"ae3_irr_wait_ready_timeout|z{zone_id}|t{task_id}",
                    details={
                        "task_id": task_id,
                        "workflow_phase": workflow_phase,
                        "grow_cycle_id": grow_cycle_id,
                    },
                    scope_parts=("stage:await_ready",),
                )
            except Exception:
                _logger.warning(
                    "AE3 не смог отправить alert biz_irrigation_wait_ready_timeout zone_id=%s task_id=%s",
                    zone_id,
                    task_id,
                    exc_info=True,
                )
            return StageOutcome(
                kind="fail",
                error_code="irrigation_wait_ready_timeout",
                error_message="Истекло время ожидания перехода зоны в состояние READY перед поливом",
            )

        IRRIGATION_WAIT_READY_POLL.labels(topology=topo).inc()
        return StageOutcome(kind="poll", due_delay_sec=_WAIT_READY_POLL_SEC)
