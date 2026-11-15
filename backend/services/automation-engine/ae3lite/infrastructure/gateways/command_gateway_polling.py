"""SequentialCommandGateway polling: explicit collaborators and invocation context."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.domain.claim_fence import same_claim_token
from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.command_outcome import (
    NON_TERMINAL_STATUSES as _NON_TERMINAL_STATUSES,
)
from ae3lite.domain.services.command_outcome import (
    decode_command_outcome,
)
from ae3lite.domain.services.command_outcome import (
    response_details_from_legacy_row as _response_details_from_legacy_row,
)
from ae3lite.infrastructure.gateways.command_publish_pipeline import (
    compute_poll_timeout_sec,
)
from ae3lite.infrastructure.metrics import (
    COMMAND_TERMINAL,
)


@dataclass(frozen=True)
class CommandGatewayPollingPorts:
    command_poll_default_sec: Callable[[], Any]
    command_poll_margin_sec: Callable[[], Any]
    command_repository: Callable[[], Any]
    observe_roundtrip_metrics: Callable[..., Any]
    poll_backoff_factor: Callable[[], Any]
    poll_interval_sec: Callable[[], Any]
    poll_max_interval_sec: Callable[[], Any]
    resolve_legacy_command: Callable[..., Awaitable[Any]]
    task_repository: Callable[[], Any]
    global_utcnow: Callable[..., Any]


class CommandGatewayPolling:
    def __init__(self, ports: CommandGatewayPollingPorts) -> None:
        self._ports = ports

    async def waiting_command_poll_deadline_exceeded(self, *, task: Any, now: datetime) -> bool:
        ae_command = await self._ports.command_repository().get_latest_for_task(task_id=task.id)
        params: Mapping[str, Any] = {}
        if ae_command is not None:
            payload = ae_command.get("payload")
            if isinstance(payload, Mapping):
                raw_params = payload.get("params")
                if isinstance(raw_params, Mapping):
                    params = raw_params
        poll_timeout_sec = compute_poll_timeout_sec(
            params=params,
            default_sec=self._ports.command_poll_default_sec(),
            margin_sec=self._ports.command_poll_margin_sec(),
        )
        waiting_since = getattr(task, "updated_at", None)
        if not isinstance(waiting_since, datetime):
            return False
        poll_deadline = waiting_since + timedelta(seconds=poll_timeout_sec)
        return now > poll_deadline

    async def persist_command_outcome(self, *, ae_command, legacy_row, now):
        outcome = decode_command_outcome(legacy_row)
        await self._ports.command_repository().update_from_legacy(
            ae_command_id=int(ae_command["id"]),
            external_id=str(legacy_row.get("id") or ae_command.get("external_id") or ""),
            ack_received_at=legacy_row.get("ack_at"),
            terminal_status=outcome.terminal_status,
            terminal_at=outcome.terminal_at,
            last_error=outcome.last_error,
            now=now,
        )
        return outcome

    async def apply_legacy_outcome(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        legacy_row: Mapping[str, Any],
        now: datetime,
    ) -> Mapping[str, Any]:
        outcome = await self.persist_command_outcome(ae_command=ae_command, legacy_row=legacy_row, now=now)
        legacy_status = outcome.status
        terminal_status = outcome.terminal_status
        last_error = outcome.last_error
        external_id = str(legacy_row.get("id") or "")
        cmd_id = str(legacy_row.get("cmd_id") or "").strip() or None
        if terminal_status is None:
            return {
                "state": "waiting_command",
                "task": task,
                "legacy_status": legacy_status,
                "external_id": external_id,
                "cmd_id": cmd_id,
                "response_details": {},
            }
        response_details = _response_details_from_legacy_row(legacy_row)
        if terminal_status == "DONE":
            COMMAND_TERMINAL.labels(terminal_status="DONE").inc()
            resumed_task = await self._ports.task_repository().resume_after_waiting_command(
                task_id=task.id,
                owner=str(task.claimed_by or ""),
                now=now,
                claim_generation=int(getattr(task, "claim_generation", 0) or 0),
            )
            if resumed_task is None:
                current_task = await self._ports.task_repository().get_by_id(task_id=task.id)
                current_status = str(getattr(current_task, "status", "") or "").strip().lower()
                if current_task is not None and current_status in {"cancelled", "completed", "failed"}:
                    return {
                        "state": "done",
                        "task": current_task,
                        "legacy_status": terminal_status,
                        "external_id": external_id,
                        "cmd_id": cmd_id,
                        "response_details": response_details,
                    }
                if current_task is not None and current_status == "running" and same_claim_token(task, current_task):
                    return {
                        "state": "done",
                        "task": current_task,
                        "legacy_status": terminal_status,
                        "external_id": external_id,
                        "cmd_id": cmd_id,
                        "response_details": response_details,
                    }
                raise TaskExecutionError(
                    "ae3_waiting_command_transition_failed",
                    f"Не удалось перевести задачу {task.id} из waiting_command в running после DONE",
                )
            return {
                "state": "done",
                "task": resumed_task,
                "legacy_status": terminal_status,
                "external_id": external_id,
                "cmd_id": cmd_id,
                "response_details": response_details,
            }

        COMMAND_TERMINAL.labels(terminal_status=terminal_status).inc()
        failed_task = await self._ports.task_repository().mark_failed(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            error_code=f"command_{terminal_status.strip().lower()}",
            error_message=last_error or f"Команда завершилась с терминальным статусом {terminal_status}",
            now=now,
            claim_generation=int(getattr(task, "claim_generation", 0) or 0),
        )
        if failed_task is None:
            raise TaskExecutionError(
                "ae3_failed_transition_failed",
                f"Не удалось перевести задачу {task.id} в failed после {terminal_status}",
            )
        return {
            "state": "failed",
            "task": failed_task,
            "legacy_status": terminal_status,
            "external_id": external_id,
            "cmd_id": cmd_id,
            "error_code": failed_task.error_code,
            "error_message": failed_task.error_message,
            "response_details": response_details,
        }

    async def await_terminal_without_task_fsm(
        self,
        *,
        task: Any,
        published: Any,
        planned: PlannedCommand,
        status_entry: dict[str, Any],
        now: datetime,
    ) -> Mapping[str, Any]:
        """Ожидает terminal DONE без перехода задачи в waiting_command (fail-safe и publish-only)."""
        ae_command = {
            "id": int(published.ae_command_id),
            "external_id": published.external_id,
            "payload": planned.payload,
        }
        poll_timeout_sec = compute_poll_timeout_sec(
            params=published.params,
            default_sec=self._ports.command_poll_default_sec(),
            margin_sec=self._ports.command_poll_margin_sec(),
        )
        poll_started_at = self._ports.global_utcnow().replace(microsecond=0)
        poll_deadline = poll_started_at + timedelta(seconds=poll_timeout_sec)
        roundtrip_started_at = time.monotonic()
        poll_interval_sec = self._ports.poll_interval_sec()
        poll_iterations = 0

        while True:
            await asyncio.sleep(poll_interval_sec)
            reconcile_now = self._ports.global_utcnow().replace(microsecond=0)
            poll_iterations += 1
            legacy_row, external_id, cmd_id = await self._ports.resolve_legacy_command(task=task, ae_command=ae_command)
            if legacy_row is None:
                if reconcile_now > poll_deadline:
                    return {
                        "success": False,
                        "task": task,
                        "command_statuses": [status_entry],
                        "error_code": "ae3_command_poll_deadline_exceeded",
                        "error_message": (
                            f"Опрос команды превысил дедлайн для задачи {task.id} "
                            f"(publish-only, stage={getattr(task, 'current_stage', None)})"
                        ),
                    }
                poll_interval_sec = min(
                    self._ports.poll_max_interval_sec(), poll_interval_sec * self._ports.poll_backoff_factor()
                )
                continue

            try:
                outcome = await self.persist_command_outcome(
                    ae_command=ae_command,
                    legacy_row=legacy_row,
                    now=reconcile_now,
                )
            except TaskExecutionError as exc:
                return {
                    "success": False,
                    "task": task,
                    "command_statuses": [
                        {**status_entry, "terminal_status": str(legacy_row.get("status") or "").strip().upper()}
                    ],
                    "error_code": exc.code,
                    "error_message": str(exc),
                }
            legacy_status = outcome.status
            ae_command["external_id"] = str(legacy_row.get("id") or external_id or "")

            if legacy_status in _NON_TERMINAL_STATUSES:
                if reconcile_now > poll_deadline:
                    return {
                        "success": False,
                        "task": task,
                        "command_statuses": [{**status_entry, "terminal_status": None}],
                        "error_code": "ae3_command_poll_deadline_exceeded",
                        "error_message": (
                            f"Опрос команды превысил дедлайн для задачи {task.id} "
                            f"(publish-only, stage={getattr(task, 'current_stage', None)})"
                        ),
                    }
                poll_interval_sec = min(
                    self._ports.poll_max_interval_sec(), poll_interval_sec * self._ports.poll_backoff_factor()
                )
                continue

            self._ports.observe_roundtrip_metrics(
                channel=planned.channel,
                terminal_status=legacy_status,
                roundtrip_started_at=roundtrip_started_at,
                poll_iterations=poll_iterations,
            )
            terminal_entry = {
                **status_entry,
                "external_id": str(legacy_row.get("id") or external_id or ""),
                "legacy_cmd_id": cmd_id,
                "terminal_status": legacy_status,
                "response_details": _response_details_from_legacy_row(legacy_row),
            }
            if legacy_status == "DONE":
                COMMAND_TERMINAL.labels(terminal_status="DONE").inc()
                return {
                    "success": True,
                    "task": task,
                    "command_statuses": [terminal_entry],
                }

            COMMAND_TERMINAL.labels(terminal_status=legacy_status).inc()
            return {
                "success": False,
                "task": task,
                "command_statuses": [terminal_entry],
                "error_code": f"command_{legacy_status.strip().lower()}",
                "error_message": str(
                    legacy_row.get("error_message") or f"Команда завершилась с терминальным статусом {legacy_status}"
                ),
            }
