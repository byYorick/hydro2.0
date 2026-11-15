"""StartupRecoveryUseCase terminal repair: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from ae3lite.application.services.startup_recovery_shared import logger
from ae3lite.application.services.startup_recovery_state import StartupRecoveryState
from ae3lite.infrastructure.advisory_locks import (
    AE3_STARTUP_RECOVERY_ADVISORY_LOCK_KEY,
)


@dataclass(frozen=True)
class StartupRecoveryTerminalRepairPorts:
    alert_repository: Callable[[], Any]
    command_gateway: Callable[[], Any]
    command_repository: Callable[[], Any]
    pid_state_repository: Callable[[], Any]
    task_repository: Callable[[], Any]
    terminal_command_reconcile_limit: Callable[[], Any]
    use_startup_recovery_lock: Callable[[], Any]
    global_create_zone_event: Callable[..., Any]
    global_try_session_advisory_lock: Callable[..., Any]


class StartupRecoveryTerminalRepair:
    def __init__(self, ports: StartupRecoveryTerminalRepairPorts, state: StartupRecoveryState) -> None:
        self._ports = ports
        self._state = state

    async def reconcile_terminal_commands(self, *, now: datetime) -> tuple[int, int]:
        """Periodic repair only; never repeat active-task startup recovery."""
        if not self._ports.use_startup_recovery_lock():
            return await self.reconcile_terminal_task_commands(now=now)
        async with self._ports.global_try_session_advisory_lock(AE3_STARTUP_RECOVERY_ADVISORY_LOCK_KEY) as acquired:
            if acquired:
                return await self.reconcile_terminal_task_commands(now=now)
        return 0, 0

    async def reconcile_terminal_task_commands(self, *, now: datetime) -> tuple[int, int]:
        """Сверить хвост команд terminal-задач и учесть DONE dose в PID.

        Выборка шире accepted/NULL: туда же входят published_unconfirmed и
        DONE dose без маркера учёта. Terminal status здесь не синтезируется.
        Падение записи PID не ставит маркер, строка остаётся в следующей выборке.
        """
        list_rows = getattr(
            self._ports.command_repository(),
            "list_unreconciled_for_terminal_tasks",
            None,
        )
        reconcile = getattr(self._ports.command_gateway(), "reconcile_terminal_task_command", None)
        if not callable(list_rows) or not callable(reconcile):
            return 0, 0

        try:
            rows = await list_rows(limit=self._ports.terminal_command_reconcile_limit())
        except Exception:
            logger.warning("Startup recovery: terminal-command scan failed", exc_info=True)
            return 0, 0

        reconciled = 0
        unresolved = 0
        for ae_command in rows:
            task_id = int(ae_command.get("task_id") or 0)
            task = await self._ports.task_repository().get_by_id(task_id=task_id)
            if task is None:
                unresolved += 1
                continue
            try:
                result = await reconcile(task=task, ae_command=ae_command, now=now)
            except Exception:
                unresolved += 1
                logger.warning(
                    "Startup recovery: terminal-command reconcile failed task_id=%s ae_command_id=%s",
                    task_id,
                    ae_command.get("id"),
                    exc_info=True,
                )
                await self.emit_terminal_command_alert(
                    task=task,
                    ae_command=ae_command,
                    state="unknown",
                    result=None,
                    now=now,
                )
                continue

            state = str(result.get("state") or "waiting_command").strip().lower()
            if state == "waiting_command":
                unresolved += 1
                await self.emit_terminal_command_alert(
                    task=task,
                    ae_command=ae_command,
                    state="unknown",
                    result=result,
                    now=now,
                )
                continue

            reconciled += 1
            if state == "done":
                try:
                    await self.reconcile_terminal_dose_pid_state(
                        task=task,
                        ae_command=ae_command,
                        result=result,
                        now=now,
                    )
                except Exception:
                    reconciled -= 1
                    unresolved += 1
                    logger.warning(
                        "Startup recovery: terminal dose PID accounting failed task_id=%s ae_command_id=%s",
                        task_id,
                        ae_command.get("id"),
                        exc_info=True,
                    )
                    continue
            await self.record_terminal_command_reconciled_event(
                task=task,
                ae_command=ae_command,
                result=result,
            )
            await self.emit_terminal_command_alert(
                task=task,
                ae_command=ae_command,
                state=state,
                result=result,
                now=now,
            )
        return reconciled, unresolved

    @staticmethod
    def terminal_dose_pid_type(ae_command: Mapping[str, Any]) -> tuple[str, str] | None:
        payload = ae_command.get("payload")
        if not isinstance(payload, Mapping):
            return None
        if str(payload.get("cmd") or "").strip().lower() != "dose":
            return None
        context = payload.get("_ae3_dose_context")
        if isinstance(context, Mapping):
            pid_type = context.get("pid_type")
            kind = context.get("last_correction_kind")
            if (pid_type, kind) in {("ec", "ec"), ("ph", "ph_up"), ("ph", "ph_down")}:
                return str(pid_type), str(kind)
        planner_step = str(ae_command.get("planner_step") or "").strip().lower()
        channel = str(ae_command.get("channel") or "").strip().lower()
        if "corr_dose_ec" in planner_step or any(token in channel for token in ("ec", "npk", "calcium")):
            return "ec", "ec"
        if "corr_dose_ph_up" in planner_step or "ph_up" in channel or "alkali" in channel:
            return "ph", "ph_up"
        if "corr_dose_ph" in planner_step or "ph_down" in channel or "acid" in channel:
            return "ph", "ph_down"
        return None

    async def reconcile_terminal_dose_pid_state(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        result: Mapping[str, Any],
        now: datetime,
    ) -> None:
        reconcile_pid = getattr(self._ports.pid_state_repository(), "reconcile_completed_dose", None)
        dose_kind = self.terminal_dose_pid_type(ae_command)
        terminal_at = result.get("terminal_at")
        if not callable(reconcile_pid) or dose_kind is None or not isinstance(terminal_at, datetime):
            return
        payload = ae_command.get("payload") if isinstance(ae_command.get("payload"), Mapping) else {}
        params = payload.get("params") if isinstance(payload.get("params"), Mapping) else {}
        details = result.get("response_details") if isinstance(result.get("response_details"), Mapping) else {}
        raw_duration = details.get("duration_ms", params.get("duration_ms", 0))
        try:
            duration_ms = max(0, int(raw_duration or 0))
        except (TypeError, ValueError):
            duration_ms = 0
        pid_type, correction_kind = dose_kind
        context = payload.get("_ae3_dose_context")
        if isinstance(context, Mapping):
            hold_sec = max(0, int(context["hold_sec"]))
        else:
            # Legacy commands did not persist their process timing. Preserve
            # the task's available stabilization policy, without inventing it.
            hold_sec = max(0, int(getattr(getattr(task, "correction", None), "stabilization_sec", 0) or 0))
        await reconcile_pid(
            zone_id=int(task.zone_id),
            pid_type=pid_type,
            last_output_ms=duration_ms,
            last_dose_at=terminal_at,
            hold_until=terminal_at + timedelta(seconds=hold_sec),
            last_correction_kind=correction_kind,
            ae_command_id=int(ae_command["id"]),
            now=now,
        )
        await self.mark_terminal_dose_accounted(ae_command=ae_command, now=now)

    async def mark_terminal_dose_accounted(
        self,
        *,
        ae_command: Mapping[str, Any],
        now: datetime,
    ) -> None:
        """Закрыть учёт дозы только после успешного reconcile_completed_dose."""
        mark = getattr(self._ports.command_repository(), "mark_dose_accounted", None)
        command_id = ae_command.get("id")
        if not callable(mark) or command_id is None:
            return
        await mark(ae_command_id=int(command_id), now=now)

    async def record_terminal_command_reconciled_event(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> None:
        try:
            await self._ports.global_create_zone_event(
                int(task.zone_id),
                "AE_TERMINAL_TASK_COMMAND_RECONCILED",
                {
                    "task_id": int(task.id),
                    "ae_command_id": int(ae_command["id"]),
                    "cmd_id": result.get("cmd_id"),
                    "terminal_status": result.get("legacy_status"),
                    "stage": str(ae_command.get("stage_name") or ""),
                },
            )
        except Exception:
            logger.warning(
                "Startup recovery: failed to emit terminal-command event task_id=%s ae_command_id=%s",
                task.id,
                ae_command.get("id"),
                exc_info=True,
            )

    async def emit_terminal_command_alert(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        state: str,
        result: Mapping[str, Any] | None,
        now: datetime,
    ) -> None:
        raise_active = getattr(self._ports.alert_repository(), "raise_active", None)
        if not callable(raise_active):
            return
        normalized_state = str(state or "unknown").strip().lower()
        if normalized_state == "done":
            code = "biz_ae3_terminal_task_command_reconciled"
            severity = "warning"
        elif normalized_state == "failed":
            code = "biz_ae3_terminal_task_command_failed"
            severity = "error"
        else:
            code = "biz_ae3_terminal_task_command_unknown"
            severity = "error"
        try:
            await raise_active(
                zone_id=int(task.zone_id),
                code=code,
                details={
                    "task_id": int(task.id),
                    "task_status": str(getattr(task, "status", "") or ""),
                    "ae_command_id": int(ae_command["id"]),
                    "cmd_id": (result or {}).get("cmd_id"),
                    "terminal_status": (result or {}).get("legacy_status"),
                    "reconciliation_state": normalized_state,
                    "dedupe_key": f"{code}:{int(task.zone_id)}:{int(ae_command['id'])}",
                },
                now=now,
                category="operations",
                severity=severity,
            )
        except Exception:
            logger.warning(
                "Startup recovery: failed to emit terminal-command alert task_id=%s ae_command_id=%s",
                task.id,
                ae_command.get("id"),
                exc_info=True,
            )
