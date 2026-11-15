"""SequentialCommandGateway recovery: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import CommandPublishError, TaskExecutionError
from ae3lite.domain.services.command_outcome import (
    response_details_from_legacy_row as _response_details_from_legacy_row,
)
from ae3lite.infrastructure.gateways.command_gateway_shared import (
    _AE3_FAIL_SAFE_KEY,
    _AE3_STAGE_EXECUTION_TOKEN_KEY,
    logger,
)


@dataclass(frozen=True)
class CommandGatewayRecoveryPorts:
    apply_legacy_outcome: Callable[..., Awaitable[Any]]
    command_repository: Callable[[], Any]
    persist_command_outcome: Callable[..., Awaitable[Any]]
    planned_command_from_ae_command: Callable[..., Any]
    publish_pipeline: Callable[[], Any]
    stage_execution_token: Callable[..., Any]
    task_repository: Callable[[], Any]


class CommandGatewayRecovery:
    def __init__(self, ports: CommandGatewayRecoveryPorts) -> None:
        self._ports = ports

    async def completed_planner_step_status(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        planner_step: str | None,
    ) -> dict[str, Any] | None:
        """Пропускает только точно совпавший step текущего stage execution, уже DONE.

        После startup recovery command-stage запускается повторно. RuntimePlan
        снова задаёт полный ожидаемый batch, а ``planner_step`` связывает каждый
        ожидаемый step с его persisted execution record в ``ae_commands``.
        DONE от прежнего входа в тот же stage name (другой stage_execution_token)
        или fail-safe publish не принимаются.
        """
        if not planner_step:
            return None
        get_latest = getattr(self._ports.command_repository(), "get_latest_by_planner_step", None)
        if not callable(get_latest):
            return None
        existing = await get_latest(task_id=task.id, planner_step=planner_step)
        if existing is None:
            return None
        terminal_status = str(existing.get("terminal_status") or "").strip().upper()
        if terminal_status != "DONE":
            return None

        stored_payload = existing.get("payload")
        planned_payload = command.payload if isinstance(command.payload, Mapping) else {}
        if not isinstance(stored_payload, Mapping):
            return None
        if bool(stored_payload.get(_AE3_FAIL_SAFE_KEY)):
            return None
        current_token = self._ports.stage_execution_token(task=task)
        stored_token = str(stored_payload.get(_AE3_STAGE_EXECUTION_TOKEN_KEY) or "").strip()
        if stored_token != current_token:
            logger.info(
                "AE3 batch resume: DONE planner_step принадлежит другому stage execution "
                "task_id=%s stage=%s planner_step=%s stored_token=%s current_token=%s",
                task.id,
                getattr(task, "current_stage", None),
                planner_step,
                stored_token or None,
                current_token,
            )
            return None
        if (
            str(existing.get("node_uid") or "").strip() != str(command.node_uid or "").strip()
            or str(existing.get("channel") or "").strip() != str(command.channel or "").strip()
            or str(stored_payload.get("cmd") or "").strip() != str(planned_payload.get("cmd") or "").strip()
            or stored_payload.get("params") != planned_payload.get("params")
        ):
            logger.warning(
                "AE3 batch resume: persisted DONE planner_step не совпал с RuntimePlan "
                "task_id=%s stage=%s planner_step=%s",
                task.id,
                getattr(task, "current_stage", None),
                planner_step,
            )
            return None

        logger.info(
            "AE3 batch resume: пропуск подтверждённого DONE step task_id=%s stage=%s planner_step=%s ae_command_id=%s",
            task.id,
            getattr(task, "current_stage", None),
            planner_step,
            existing.get("id"),
        )
        payload_cmd_id = str(stored_payload.get("cmd_id") or "").strip() or None
        return {
            "ae_command_id": existing.get("id"),
            "node_uid": command.node_uid,
            "channel": command.channel,
            "cmd": str(planned_payload.get("cmd") or ""),
            "external_id": existing.get("external_id"),
            "legacy_cmd_id": payload_cmd_id,
            "terminal_status": "DONE",
            "response_details": {},
            "recovered": True,
        }

    async def recover_waiting_command(self, *, task: Any, now: datetime) -> Mapping[str, Any]:
        ae_command = await self._ports.command_repository().get_latest_for_task(task_id=task.id)
        if ae_command is None:
            current_task = await self._ports.task_repository().get_by_id(task_id=task.id)
            current_status = str(getattr(current_task, "status", "") or "").strip().lower()
            if current_task is None or current_status in {"cancelled", "completed"}:
                return {
                    "state": "done",
                    "task": current_task or task,
                    "legacy_status": None,
                    "external_id": None,
                    "cmd_id": None,
                }
            raise TaskExecutionError(
                "ae3_missing_ae_command", f"У задачи {task.id} отсутствует ae_command для recovery"
            )
        legacy_row, external_id, cmd_id = await self.resolve_legacy_command(task=task, ae_command=ae_command)
        if legacy_row is None:
            await self.try_redrive_unpublished_ae_command(task=task, ae_command=ae_command, now=now)
            legacy_row, external_id, cmd_id = await self.resolve_legacy_command(task=task, ae_command=ae_command)
            if legacy_row is None:
                return {
                    "state": "waiting_command",
                    "task": task,
                    "legacy_status": None,
                    "external_id": external_id,
                    "cmd_id": cmd_id,
                }
        return await self._ports.apply_legacy_outcome(task=task, ae_command=ae_command, legacy_row=legacy_row, now=now)

    async def reconcile_terminal_task_command(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        now: datetime,
    ) -> Mapping[str, Any]:
        """Refresh one dangling command without changing an already terminal task."""
        legacy_row, external_id, cmd_id = await self.resolve_legacy_command(
            task=task,
            ae_command=ae_command,
        )
        if legacy_row is None:
            return {
                "state": "waiting_command",
                "task": task,
                "legacy_status": None,
                "external_id": external_id,
                "cmd_id": cmd_id,
                "response_details": {},
                "terminal_at": None,
            }
        outcome = await self._ports.persist_command_outcome(
            ae_command=ae_command,
            legacy_row=legacy_row,
            now=now,
        )
        response_details = _response_details_from_legacy_row(legacy_row) if outcome.terminal_status is not None else {}
        return {
            "state": (
                "waiting_command"
                if outcome.terminal_status is None
                else "done"
                if outcome.terminal_status == "DONE"
                else "failed"
            ),
            "task": task,
            "legacy_status": outcome.status,
            "external_id": str(legacy_row.get("id") or external_id or "") or None,
            "cmd_id": str(legacy_row.get("cmd_id") or cmd_id or "") or None,
            "response_details": response_details,
            "terminal_at": outcome.terminal_at,
            "error_code": (
                None if outcome.terminal_status in {None, "DONE"} else f"command_{outcome.terminal_status.lower()}"
            ),
            "error_message": outcome.last_error,
        }

    async def try_redrive_unpublished_ae_command(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        now: datetime,
    ) -> bool:
        publish_status = str(ae_command.get("publish_status") or "pending").strip().lower()
        external_id = str(ae_command.get("external_id") or "").strip()
        if publish_status not in {"pending", "published_unconfirmed"} or external_id:
            return False
        planned = self._ports.planned_command_from_ae_command(ae_command)
        if planned is None:
            logger.warning(
                "AE3 recover_waiting_command: cannot rebuild PlannedCommand for redrive task_id=%s ae_command_id=%s",
                task.id,
                ae_command.get("id"),
            )
            return False
        try:
            await self._ports.publish_pipeline().redrive_existing(
                task=task,
                ae_command=ae_command,
                command=planned,
                now=now,
            )
            logger.info(
                "AE3 recover_waiting_command: redrove unpublished ae_command task_id=%s ae_command_id=%s",
                task.id,
                ae_command.get("id"),
            )
            return True
        except TaskExecutionError:
            raise
        except CommandPublishError as exc:
            logger.warning(
                "AE3 recover_waiting_command: publish redrive failed task_id=%s ae_command_id=%s error=%s",
                task.id,
                ae_command.get("id"),
                exc,
            )
            return False
        except Exception:
            logger.warning(
                "AE3 recover_waiting_command: unexpected publish redrive failure task_id=%s ae_command_id=%s",
                task.id,
                ae_command.get("id"),
                exc_info=True,
            )
            return False

    async def resolve_legacy_command(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any] | None, str | None, str | None]:
        external_id = str(ae_command.get("external_id") or "").strip() or None
        payload = ae_command.get("payload") if isinstance(ae_command.get("payload"), Mapping) else {}
        cmd_id = str(payload.get("cmd_id") or "").strip() or None
        if external_id:
            row = await self._ports.command_repository().get_legacy_command_by_id(external_id=external_id)
            if row is None:
                raise TaskExecutionError(
                    "ae3_legacy_command_not_found", f"Не найдена legacy command для external_id={external_id}"
                )
            return row, external_id, str(row.get("cmd_id") or "").strip() or cmd_id
        if not cmd_id:
            raise TaskExecutionError(
                "ae3_missing_cmd_id",
                f"У ae_command {ae_command.get('id')} отсутствуют и external_id, и payload.cmd_id",
            )
        row = await self._ports.command_repository().get_legacy_command_by_cmd_id(zone_id=task.zone_id, cmd_id=cmd_id)
        if row is None:
            return None, None, cmd_id
        return row, str(row["id"]), cmd_id
