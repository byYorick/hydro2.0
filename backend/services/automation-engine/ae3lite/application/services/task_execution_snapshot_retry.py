"""ExecuteTaskUseCase snapshot retry: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.application.services.task_execution_shared import (
    COMMAND_SEND_MAX_STAGE_AGE_SEC,
    COMMAND_SEND_RETRY_EXHAUSTED_CODE,
    COMMAND_SEND_RETRY_SCHEDULED_CODE,
    COMMAND_SEND_RETRY_SEC,
    SNAPSHOT_RETRY_EXHAUSTED_CODE,
    SNAPSHOT_RETRY_SCHEDULED_CODE,
    SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC,
    SNAPSHOT_TRANSIENT_RETRY_SEC,
    logger,
)
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.domain.claim_fence import claim_generation
from ae3lite.domain.errors import (
    ErrorCodes,
    SnapshotBuildError,
    TaskExecutionError,
)


@dataclass(frozen=True)
class TaskExecutionSnapshotRetryPorts:
    task_repository: Callable[[], Any]
    complete_execution_failure: Callable[..., Awaitable[Any]]
    global_create_zone_event: Callable[..., Any]
    global_send_infra_alert: Callable[..., Any]


class TaskExecutionSnapshotRetry:
    def __init__(self, ports: TaskExecutionSnapshotRetryPorts) -> None:
        self._ports = ports

    async def retry_transient_command_send_failure(
        self,
        *,
        task: Any,
        owner: str,
        error: TaskExecutionError,
        now: datetime,
        snapshot: Any = None,
        plan: Any = None,
    ) -> Any | None:
        stage_entered_at = getattr(getattr(task, "workflow", None), "stage_entered_at", None)
        stage_age_sec = self.stage_age_sec(stage_entered_at=stage_entered_at, now=now)
        error_message = str(error).strip() or type(error).__name__
        details = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or ""),
            "topology": str(getattr(task, "topology", "") or ""),
            "error_code": COMMAND_SEND_RETRY_EXHAUSTED_CODE,
            "source_error_code": "command_send_failed",
            "source_error": error_message,
            "retry_reason": "history_logger_transport_transient",
            "stage_age_sec": stage_age_sec,
            "max_stage_age_sec": COMMAND_SEND_MAX_STAGE_AGE_SEC,
        }
        if stage_age_sec >= COMMAND_SEND_MAX_STAGE_AGE_SEC:
            final_message = (
                f"{error_message} (command-send retry budget exhausted after {stage_age_sec}s "
                f"in stage {getattr(task, 'current_stage', '')})"
            )
            logger.error(
                "AE3 transient command_send_failed исчерпал бюджет повторов: zone_id=%s task_id=%s stage=%s stage_age_sec=%s error=%s",
                getattr(task, "zone_id", None),
                getattr(task, "id", None),
                getattr(task, "current_stage", None),
                stage_age_sec,
                error_message,
            )
            await self.emit_snapshot_retry_observability(
                task=task,
                now=now,
                event_type="AE_COMMAND_SEND_RETRY_EXHAUSTED",
                alert_code="infra_ae3_command_send_retry_exhausted",
                alert_message=final_message,
                severity="error",
                details=details,
            )
            return await self._ports.complete_execution_failure(
                task=task,
                snapshot=snapshot,
                plan=plan,
                now=now,
                owner=owner,
                error_code=COMMAND_SEND_RETRY_EXHAUSTED_CODE,
                error_message=final_message,
            )

        update_stage = getattr(self._ports.task_repository(), "update_stage", None)
        if not callable(update_stage):
            raise TaskExecutionError(
                "ae3_command_send_retry_persist_failed",
                f"Task repository не поддерживает update_stage для command_send retry task_id={task.id}",
            )

        due_at = now + timedelta(seconds=COMMAND_SEND_RETRY_SEC)
        updated_task = await update_stage(
            task_id=int(getattr(task, "id", 0) or 0),
            owner=owner,
            workflow=getattr(task, "workflow"),
            correction=getattr(task, "correction", None),
            due_at=due_at,
            now=now,
            claim_generation=claim_generation(task),
        )
        if updated_task is None:
            raise TaskExecutionError(
                "ae3_command_send_retry_persist_failed",
                f"Не удалось сохранить command_send retry для задачи {task.id}",
            )
        logger.warning(
            "AE3 transient command_send_failed: zone_id=%s task_id=%s stage=%s retry_in=%ss stage_age_sec=%s error=%s",
            getattr(task, "zone_id", None),
            getattr(task, "id", None),
            getattr(task, "current_stage", None),
            COMMAND_SEND_RETRY_SEC,
            stage_age_sec,
            error_message,
        )
        await self.emit_snapshot_retry_observability(
            task=task,
            now=now,
            event_type="AE_COMMAND_SEND_RETRY_SCHEDULED",
            alert_code=COMMAND_SEND_RETRY_SCHEDULED_CODE,
            alert_message=error_message,
            severity="warning",
            details={
                **details,
                "retry_after_sec": COMMAND_SEND_RETRY_SEC,
                "next_due_at": due_at.astimezone(timezone.utc).isoformat()
                if due_at.tzinfo is not None
                else due_at.replace(tzinfo=timezone.utc).isoformat(),
            },
        )
        return updated_task

    async def retry_transient_snapshot_gap(
        self,
        *,
        task: Any,
        owner: str,
        error: SnapshotBuildError,
        now: datetime,
    ) -> Any | None:
        snapshot_error_code = getattr(error, "code", ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED)
        error_message = str(error).strip()
        if not self.is_transient_snapshot_gap(task=task, error_code=snapshot_error_code):
            return None

        snapshot_details = error.details if isinstance(getattr(error, "details", None), Mapping) else {}
        stage_entered_at = getattr(getattr(task, "workflow", None), "stage_entered_at", None)
        stage_age_sec = self.stage_age_sec(stage_entered_at=stage_entered_at, now=now)
        details = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or ""),
            "topology": str(getattr(task, "topology", "") or ""),
            "error_code": SNAPSHOT_RETRY_EXHAUSTED_CODE,
            "snapshot_error_code": snapshot_error_code,
            "snapshot_error": error_message,
            "snapshot_reason": "no_online_actuator_channels",
            "stage_age_sec": stage_age_sec,
            "max_stage_age_sec": SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC,
        }
        for key in (
            "zone_nodes",
            "persistently_offline_uids",
            "transiently_offline_uids",
            "persistent_dead_threshold_sec",
        ):
            if key in snapshot_details:
                details[key] = snapshot_details[key]

        if stage_age_sec >= SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC:
            final_message = (
                f"{error_message} (transient snapshot retry budget exhausted after {stage_age_sec}s "
                f"in stage {getattr(task, 'current_stage', '')})"
            )
            logger.error(
                "AE3 transient snapshot gap исчерпал бюджет повторов: zone_id=%s task_id=%s stage=%s stage_age_sec=%s error=%s",
                getattr(task, "zone_id", None),
                getattr(task, "id", None),
                getattr(task, "current_stage", None),
                stage_age_sec,
                error_message,
            )
            await self.emit_snapshot_retry_observability(
                task=task,
                now=now,
                event_type="AE_SNAPSHOT_RETRY_EXHAUSTED",
                alert_code="infra_ae3_snapshot_retry_exhausted",
                alert_message=final_message,
                severity="error",
                details=details,
            )
            return await self._ports.complete_execution_failure(
                task=task,
                snapshot=None,
                plan=None,
                now=now,
                owner=owner,
                error_code=SNAPSHOT_RETRY_EXHAUSTED_CODE,
                error_message=final_message,
            )

        update_stage = getattr(self._ports.task_repository(), "update_stage", None)
        if not callable(update_stage):
            raise TaskExecutionError(
                "ae3_snapshot_retry_persist_failed",
                f"Task repository не поддерживает update_stage для transient snapshot retry task_id={task.id}",
            )

        due_at = now + timedelta(seconds=SNAPSHOT_TRANSIENT_RETRY_SEC)
        updated_task = await update_stage(
            task_id=int(getattr(task, "id", 0) or 0),
            owner=owner,
            workflow=getattr(task, "workflow"),
            correction=getattr(task, "correction", None),
            due_at=due_at,
            now=now,
            claim_generation=claim_generation(task),
        )
        if updated_task is None:
            raise TaskExecutionError(
                "ae3_snapshot_retry_persist_failed",
                f"Не удалось сохранить transient snapshot retry для задачи {task.id}",
            )

        logger.warning(
            "Обнаружен AE3 transient snapshot gap: zone_id=%s task_id=%s stage=%s retry_in=%ss stage_age_sec=%s error=%s",
            getattr(task, "zone_id", None),
            getattr(task, "id", None),
            getattr(task, "current_stage", None),
            SNAPSHOT_TRANSIENT_RETRY_SEC,
            stage_age_sec,
            error_message,
        )
        await self.emit_snapshot_retry_observability(
            task=task,
            now=now,
            event_type="AE_SNAPSHOT_RETRY_SCHEDULED",
            alert_code=SNAPSHOT_RETRY_SCHEDULED_CODE,
            alert_message=error_message,
            severity="warning",
            details={
                **details,
                "retry_after_sec": SNAPSHOT_TRANSIENT_RETRY_SEC,
                "next_due_at": due_at.astimezone(timezone.utc).isoformat()
                if due_at.tzinfo is not None
                else due_at.replace(tzinfo=timezone.utc).isoformat(),
            },
        )
        return updated_task

    def is_transient_snapshot_gap(self, *, task: Any, error_code: str) -> bool:
        topology = str(getattr(task, "topology", "") or "").strip().lower()
        pack = TopologyRegistry().try_pack(topology)
        return (
            pack is not None
            and pack.retries_missing_actuators
            and str(error_code or "").strip() == ErrorCodes.AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS
        )

    def stage_age_sec(self, *, stage_entered_at: datetime | None, now: datetime) -> int:
        if not isinstance(stage_entered_at, datetime):
            return 0
        normalized_now = now.astimezone(timezone.utc) if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        normalized_stage_entered_at = (
            stage_entered_at.astimezone(timezone.utc)
            if stage_entered_at.tzinfo is not None
            else stage_entered_at.replace(tzinfo=timezone.utc)
        )
        return max(0, int((normalized_now - normalized_stage_entered_at).total_seconds()))

    async def emit_snapshot_retry_observability(
        self,
        *,
        task: Any,
        now: datetime,
        event_type: str,
        alert_code: str,
        alert_message: str,
        severity: str,
        details: Mapping[str, Any],
    ) -> None:
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        try:
            await self._ports.global_create_zone_event(zone_id, event_type, with_runtime_event_contract(details))
        except Exception:
            logger.warning(
                "AE3 не смог записать observability event retry snapshot zone_id=%s task_id=%s event_type=%s",
                zone_id,
                int(getattr(task, "id", 0) or 0),
                event_type,
                exc_info=True,
            )

        try:
            await self._ports.global_send_infra_alert(
                code=alert_code,
                message=alert_message,
                zone_id=zone_id,
                severity=severity,
                service="automation-engine",
                component="execute_task",
                error_type="SnapshotBuildError",
                details=dict(details),
            )
        except Exception:
            logger.warning(
                "AE3 не смог отправить infra alert retry snapshot zone_id=%s task_id=%s code=%s",
                zone_id,
                int(getattr(task, "id", 0) or 0),
                alert_code,
                exc_info=True,
            )
