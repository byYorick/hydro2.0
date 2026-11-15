"""Последовательный pipeline команд к нодам в AE3-Lite."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.claim_fence import same_claim_token
from ae3lite.domain.errors import CommandPublishError, ErrorCodes, TaskExecutionError, TaskTerminalStateReached
from ae3lite.infrastructure.gateways.command_publish_pipeline import (
    CommandPublishPipeline,
    compute_poll_timeout_sec,
    planner_step_for_command,
)
from ae3lite.infrastructure.log_context import log_context_scope
from ae3lite.infrastructure.metrics import (
    COMMAND_DISPATCH_FAILED,
    COMMAND_DISPATCH_DURATION,
    COMMAND_DISPATCHED,
    COMMAND_POLL_ITERATIONS,
    COMMAND_ROUNDTRIP_DURATION,
    COMMAND_TERMINAL,
    inc_observability_write_failed,
)
from common.db import create_zone_event
from common.service_logs import send_service_log
from common.utils.time import utcnow_naive as _utcnow


from ae3lite.domain.services.command_outcome import (
    NON_TERMINAL_STATUSES as _NON_TERMINAL_STATUSES,
    TERMINAL_STATUSES as _TERMINAL_STATUSES,
    PROTOCOL_VIOLATION_STATUSES as _PROTOCOL_VIOLATION_STATUSES,
    decode_command_outcome,
    response_details_from_legacy_row as _response_details_from_legacy_row,
)


from ae3lite.infrastructure.gateways.command_gateway_shared import (
    logger,
    _AE3_FAIL_SAFE_KEY,
    _AE3_STAGE_EXECUTION_TOKEN_KEY,
    _AE3_RECOVERY_RESUME_KEY,
    _PUMP_MAIN_CHANNEL,
)

from ae3lite.infrastructure.gateways.command_gateway_batch_authority import (
    CommandGatewayBatchAuthority,
    CommandGatewayBatchAuthorityPorts,
)
from ae3lite.infrastructure.gateways.command_gateway_batch_execution import (
    CommandGatewayBatchExecution,
    CommandGatewayBatchExecutionPorts,
)
from ae3lite.infrastructure.gateways.command_gateway_safety_publication import (
    CommandGatewaySafetyPublication,
    CommandGatewaySafetyPublicationPorts,
)
from ae3lite.infrastructure.gateways.command_gateway_command_execution import (
    CommandGatewayCommandExecution,
    CommandGatewayCommandExecutionPorts,
)
from ae3lite.infrastructure.gateways.command_gateway_recovery import CommandGatewayRecovery, CommandGatewayRecoveryPorts
from ae3lite.infrastructure.gateways.command_gateway_polling import CommandGatewayPolling, CommandGatewayPollingPorts
from ae3lite.infrastructure.gateways.command_gateway_diagnostics import (
    CommandGatewayDiagnostics,
    CommandGatewayDiagnosticsPorts,
)
from ae3lite.infrastructure.gateways.command_gateway_payload import CommandGatewayPayload, CommandGatewayPayloadPorts


class SequentialCommandGateway:
    """Публикует разрешённые команды по одной и ждёт terminal-статус legacy-команды."""

    def __init__(
        self,
        *,
        task_repository: Any,
        command_repository: Any,
        history_logger_client: Any,
        poll_interval_sec: float,
        poll_backoff_factor: float = 1.5,
        poll_max_interval_sec: float = 5.0,
        command_poll_default_sec: float = 120.0,
        command_poll_margin_sec: float = 30.0,
        command_stage_stop_reserve_sec: float = 5.0,
    ) -> None:
        self._task_repository = task_repository
        self._command_repository = command_repository
        self._history_logger_client = history_logger_client
        self._publish_pipeline = CommandPublishPipeline(
            command_repository=command_repository,
            history_logger_client=history_logger_client,
        )
        self._poll_interval_sec = max(0.05, float(poll_interval_sec))
        self._poll_backoff_factor = max(1.0, float(poll_backoff_factor))
        self._poll_max_interval_sec = max(self._poll_interval_sec, float(poll_max_interval_sec))
        self._command_poll_default_sec = max(1.0, float(command_poll_default_sec))
        self._command_poll_margin_sec = max(0.0, float(command_poll_margin_sec))
        self._command_stage_stop_reserve_sec = max(0.0, float(command_stage_stop_reserve_sec))
        self._command_gateway_batch_authority = CommandGatewayBatchAuthority(
            CommandGatewayBatchAuthorityPorts(
                command_repository=lambda: self._command_repository,
                load_recovery_resume_marker=lambda *args, **kwargs: self._load_recovery_resume_marker(*args, **kwargs),
                task_repository=lambda: self._task_repository,
            )
        )
        self._command_gateway_batch_execution = CommandGatewayBatchExecution(
            CommandGatewayBatchExecutionPorts(
                command_poll_margin_sec=lambda: self._command_poll_margin_sec,
                command_stage_stop_reserve_sec=lambda: self._command_stage_stop_reserve_sec,
                completed_planner_step_status=lambda *args, **kwargs: self._completed_planner_step_status(
                    *args, **kwargs
                ),
                load_recovery_resume_marker=lambda *args, **kwargs: self._load_recovery_resume_marker(*args, **kwargs),
                recovery_batch_resume_active=lambda *args, **kwargs: self._recovery_batch_resume_active(
                    *args, **kwargs
                ),
                run_command=lambda *args, **kwargs: self._run_command(*args, **kwargs),
                stage_execution_token=lambda *args, **kwargs: self._stage_execution_token(*args, **kwargs),
                global_utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            )
        )
        self._command_gateway_safety_publication = CommandGatewaySafetyPublication(
            CommandGatewaySafetyPublicationPorts(
                publish_without_terminal=lambda *args, **kwargs: self._publish_without_terminal(*args, **kwargs),
                run_command=lambda *args, **kwargs: self._run_command(*args, **kwargs),
            )
        )
        self._command_gateway_command_execution = CommandGatewayCommandExecution(
            CommandGatewayCommandExecutionPorts(
                await_terminal_without_task_fsm=lambda *args, **kwargs: self._await_terminal_without_task_fsm(
                    *args, **kwargs
                ),
                cleanup_race_batch_result=lambda *args, **kwargs: self._cleanup_race_batch_result(*args, **kwargs),
                command_poll_default_sec=lambda: self._command_poll_default_sec,
                command_poll_margin_sec=lambda: self._command_poll_margin_sec,
                command_repository=lambda: self._command_repository,
                complete_on_ack=lambda *args, **kwargs: self._complete_on_ack(*args, **kwargs),
                emit_poll_deadline_exceeded_event=lambda *args, **kwargs: self._emit_poll_deadline_exceeded_event(
                    *args, **kwargs
                ),
                enrich_command_payload=lambda *args, **kwargs: self._enrich_command_payload(*args, **kwargs),
                extract_publish_payload=lambda *args, **kwargs: self._extract_publish_payload(*args, **kwargs),
                maybe_raise_offline_instead_of_command_error=lambda *args, **kwargs: (
                    self._maybe_raise_offline_instead_of_command_error(*args, **kwargs)
                ),
                observe_roundtrip_metrics=lambda *args, **kwargs: self._observe_roundtrip_metrics(*args, **kwargs),
                poll_backoff_factor=lambda: self._poll_backoff_factor,
                poll_interval_sec=lambda: self._poll_interval_sec,
                poll_max_interval_sec=lambda: self._poll_max_interval_sec,
                publish_pipeline=lambda: self._publish_pipeline,
                task_repository=lambda: self._task_repository,
                task_row_missing=lambda *args, **kwargs: self._task_row_missing(*args, **kwargs),
                recover_waiting_command=lambda *args, **kwargs: self.recover_waiting_command(*args, **kwargs),
                global_utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
                global_send_service_log=lambda *args, **kwargs: send_service_log(*args, **kwargs),
            )
        )
        self._command_gateway_recovery = CommandGatewayRecovery(
            CommandGatewayRecoveryPorts(
                apply_legacy_outcome=lambda *args, **kwargs: self._apply_legacy_outcome(*args, **kwargs),
                command_repository=lambda: self._command_repository,
                persist_command_outcome=lambda *args, **kwargs: self._persist_command_outcome(*args, **kwargs),
                planned_command_from_ae_command=lambda *args, **kwargs: self._planned_command_from_ae_command(
                    *args, **kwargs
                ),
                publish_pipeline=lambda: self._publish_pipeline,
                stage_execution_token=lambda *args, **kwargs: self._stage_execution_token(*args, **kwargs),
                task_repository=lambda: self._task_repository,
            )
        )
        self._command_gateway_polling = CommandGatewayPolling(
            CommandGatewayPollingPorts(
                command_poll_default_sec=lambda: self._command_poll_default_sec,
                command_poll_margin_sec=lambda: self._command_poll_margin_sec,
                command_repository=lambda: self._command_repository,
                observe_roundtrip_metrics=lambda *args, **kwargs: self._observe_roundtrip_metrics(*args, **kwargs),
                poll_backoff_factor=lambda: self._poll_backoff_factor,
                poll_interval_sec=lambda: self._poll_interval_sec,
                poll_max_interval_sec=lambda: self._poll_max_interval_sec,
                resolve_legacy_command=lambda *args, **kwargs: self._resolve_legacy_command(*args, **kwargs),
                task_repository=lambda: self._task_repository,
                global_utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            )
        )
        self._command_gateway_diagnostics = CommandGatewayDiagnostics(
            CommandGatewayDiagnosticsPorts(
                global_create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            )
        )
        self._command_gateway_payload = CommandGatewayPayload(
            CommandGatewayPayloadPorts(
                stage_execution_token=lambda *args, **kwargs: self._stage_execution_token(*args, **kwargs),
            )
        )

    def _cleanup_race_batch_result(self, *, task: Any, message: str) -> dict[str, Any]:
        return self._command_gateway_batch_authority.cleanup_race_batch_result(task=task, message=message)

    async def _task_row_missing(self, *, task_id: int) -> bool:
        return await self._command_gateway_batch_authority.task_row_missing(task_id=task_id)

    def _stage_execution_token(self, *, task: Any) -> str:
        return self._command_gateway_batch_authority.stage_execution_token(task=task)

    async def mark_recovery_batch_resume(self, *, task: Any, now: datetime) -> bool:
        return await self._command_gateway_batch_authority.mark_recovery_batch_resume(task=task, now=now)

    async def _load_recovery_resume_marker(self, *, task: Any) -> Mapping[str, Any] | None:
        return await self._command_gateway_batch_authority.load_recovery_resume_marker(task=task)

    async def _recovery_batch_resume_active(self, *, task: Any) -> bool:
        return await self._command_gateway_batch_authority.recovery_batch_resume_active(task=task)

    async def run_batch(
        self,
        *,
        task: Any,
        commands: Sequence[PlannedCommand],
        now: datetime,
        track_task_state: bool = True,
    ) -> Mapping[str, Any]:
        return await self._command_gateway_batch_execution.run_batch(
            task=task, commands=commands, now=now, track_task_state=track_task_state
        )

    def _dose_stage_admission_failure(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        now: datetime,
    ) -> dict[str, Any] | None:
        return self._command_gateway_batch_execution.dose_stage_admission_failure(task=task, command=command, now=now)

    async def run_publish_only_batch(
        self,
        *,
        task: Any,
        commands: Sequence[PlannedCommand],
        now: datetime,
    ) -> Mapping[str, Any]:
        return await self._command_gateway_safety_publication.run_publish_only_batch(
            task=task, commands=commands, now=now
        )

    async def _completed_planner_step_status(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        planner_step: str | None,
    ) -> dict[str, Any] | None:
        return await self._command_gateway_recovery.completed_planner_step_status(
            task=task, command=command, planner_step=planner_step
        )

    async def waiting_command_poll_deadline_exceeded(self, *, task: Any, now: datetime) -> bool:
        return await self._command_gateway_polling.waiting_command_poll_deadline_exceeded(task=task, now=now)

    async def recover_waiting_command(self, *, task: Any, now: datetime) -> Mapping[str, Any]:
        return await self._command_gateway_recovery.recover_waiting_command(task=task, now=now)

    async def reconcile_terminal_task_command(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        now: datetime,
    ) -> Mapping[str, Any]:
        return await self._command_gateway_recovery.reconcile_terminal_task_command(
            task=task, ae_command=ae_command, now=now
        )

    async def _run_command(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        now: datetime,
        track_task_state: bool,
        seq_index: int = 0,
        planner_step: str | None = None,
        recovery_resume_marker: Mapping[str, Any] | None = None,
        await_terminal: bool = True,
    ) -> Mapping[str, Any]:
        # complete_on_ack устарел для mutating-команд: terminal success только по DONE (протокол 2.0).
        return await self._command_gateway_command_execution.run_command(
            task=task,
            command=command,
            now=now,
            track_task_state=track_task_state,
            seq_index=seq_index,
            planner_step=planner_step,
            recovery_resume_marker=recovery_resume_marker,
            await_terminal=await_terminal,
        )

    async def _handle_publish_failure(
        self,
        *,
        task: Any,
        planned: PlannedCommand,
        ae_command_id: int | None,
        cmd_id: str,
        cmd_name: str,
        exc: Exception,
        now: datetime,
    ) -> Mapping[str, Any]:
        return await self._command_gateway_command_execution.handle_publish_failure(
            task=task, planned=planned, ae_command_id=ae_command_id, cmd_id=cmd_id, cmd_name=cmd_name, exc=exc, now=now
        )

    async def _emit_poll_deadline_exceeded_event(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        cmd_id: str,
        external_id: str,
        checked_at: datetime,
        deadline: datetime,
        poll_iterations: int,
        deadline_kind: str = "poll",
    ) -> None:
        return await self._command_gateway_diagnostics.emit_poll_deadline_exceeded_event(
            task=task,
            command=command,
            cmd_id=cmd_id,
            external_id=external_id,
            checked_at=checked_at,
            deadline=deadline,
            poll_iterations=poll_iterations,
            deadline_kind=deadline_kind,
        )

    def _observe_roundtrip_metrics(
        self,
        *,
        channel: str | None,
        terminal_status: Any,
        roundtrip_started_at: float,
        poll_iterations: int,
    ) -> None:
        return self._command_gateway_diagnostics.observe_roundtrip_metrics(
            channel=channel,
            terminal_status=terminal_status,
            roundtrip_started_at=roundtrip_started_at,
            poll_iterations=poll_iterations,
        )

    def _planned_command_from_ae_command(self, ae_command: Mapping[str, Any]) -> PlannedCommand | None:
        return self._command_gateway_payload.planned_command_from_ae_command(ae_command=ae_command)

    async def _try_redrive_unpublished_ae_command(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        now: datetime,
    ) -> bool:
        return await self._command_gateway_recovery.try_redrive_unpublished_ae_command(
            task=task, ae_command=ae_command, now=now
        )

    async def _resolve_legacy_command(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any] | None, str | None, str | None]:
        return await self._command_gateway_recovery.resolve_legacy_command(task=task, ae_command=ae_command)

    async def _persist_command_outcome(self, *, ae_command, legacy_row, now):
        return await self._command_gateway_polling.persist_command_outcome(
            ae_command=ae_command, legacy_row=legacy_row, now=now
        )

    async def _apply_legacy_outcome(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        legacy_row: Mapping[str, Any],
        now: datetime,
    ) -> Mapping[str, Any]:
        return await self._command_gateway_polling.apply_legacy_outcome(
            task=task, ae_command=ae_command, legacy_row=legacy_row, now=now
        )

    async def _await_terminal_without_task_fsm(
        self,
        *,
        task: Any,
        published: Any,
        planned: PlannedCommand,
        status_entry: dict[str, Any],
        now: datetime,
    ) -> Mapping[str, Any]:
        return await self._command_gateway_polling.await_terminal_without_task_fsm(
            task=task, published=published, planned=planned, status_entry=status_entry, now=now
        )

    async def _publish_without_terminal(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        now: datetime,
        seq_index: int = 0,
    ) -> Mapping[str, Any]:
        return await self._command_gateway_safety_publication.publish_without_terminal(
            task=task, command=command, now=now, seq_index=seq_index
        )

    def _enrich_command_payload(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        recovery_resume_marker: Mapping[str, Any] | None = None,
    ) -> PlannedCommand:
        return self._command_gateway_payload.enrich_command_payload(
            task=task, command=command, recovery_resume_marker=recovery_resume_marker
        )

    async def _maybe_raise_offline_instead_of_command_error(
        self,
        *,
        task: Any,
        planned: PlannedCommand,
        error_code: str,
        error_message: str,
    ) -> None:
        return await self._command_gateway_diagnostics.maybe_raise_offline_instead_of_command_error(
            task=task, planned=planned, error_code=error_code, error_message=error_message
        )

    def _extract_publish_payload(self, command: PlannedCommand) -> tuple[str, Mapping[str, Any]]:
        return self._command_gateway_payload.extract_publish_payload(command=command)

    def _complete_on_ack(self, command: PlannedCommand) -> bool:
        return self._command_gateway_payload.complete_on_ack(command=command)
