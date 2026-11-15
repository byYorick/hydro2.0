"""ExecuteTaskUseCase failure diagnostics: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from ae3lite.application.services.task_execution_shared import NODE_STALE_ONLINE_THRESHOLD_SEC, logger


@dataclass(frozen=True)
class TaskExecutionFailureDiagnosticsPorts:
    command_repository: Callable[[], Any]
    global_fetch: Callable[..., Any]


class TaskExecutionFailureDiagnostics:
    def __init__(self, ports: TaskExecutionFailureDiagnosticsPorts) -> None:
        self._ports = ports

    async def latest_chemistry_diagnostics(self, *, task: Any) -> Mapping[str, Any] | None:
        """Load the last persisted target outcome for terminal diagnostics."""
        event_types = (
            "CORRECTION_COMPLETE",
            "CORRECTION_TARGETS_NOT_ACHIEVED",
            "CORRECTION_TARGET_OUTCOME_UNKNOWN",
        )
        try:
            rows = await self._ports.global_fetch(
                """
                SELECT type, COALESCE(details, payload_json) AS payload
                FROM zone_events
                WHERE zone_id = $1
                  AND type = ANY($2::text[])
                ORDER BY created_at DESC, id DESC
                LIMIT 64
                """,
                int(task.zone_id),
                list(event_types),
            )
            for row in rows:
                payload = row.get("payload") if isinstance(row, Mapping) else None
                if not isinstance(payload, Mapping):
                    continue
                try:
                    event_task_id = int(payload.get("task_id") or 0)
                except (TypeError, ValueError):
                    continue
                if event_task_id != int(task.id):
                    continue
                event_type = str(row.get("type") or "")
                fallback_outcome = {
                    "CORRECTION_COMPLETE": "targets_achieved",
                    "CORRECTION_TARGETS_NOT_ACHIEVED": "targets_not_achieved",
                    "CORRECTION_TARGET_OUTCOME_UNKNOWN": "unknown",
                }.get(event_type, "unknown")
                return {
                    **dict(payload),
                    "chemistry_outcome": str(payload.get("chemistry_outcome") or fallback_outcome),
                }
        except Exception:
            logger.warning(
                "AE3 could not load terminal chemistry diagnostics zone_id=%s task_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                exc_info=True,
            )
        task_type = str(getattr(task, "task_type", "") or "").strip().lower()
        decision_outcome = str(getattr(task, "irrigation_decision_outcome", "") or "").strip().lower()
        if task_type == "irrigation_start" and decision_outcome != "skip":
            return {
                "chemistry_outcome": "unknown",
                "reason": "terminal_chemistry_diagnostics_missing",
                "task_id": int(getattr(task, "id", 0) or 0),
            }
        return None

    async def build_failure_observability_details(
        self,
        *,
        task: Any,
        error_code: str,
        now: datetime,
    ) -> dict[str, Any]:
        if str(error_code).strip().lower() != "command_timeout":
            return {}

        repository = self._ports.command_repository()
        if repository is None:
            return {}

        try:
            ae_command = await repository.get_latest_for_task(task_id=int(getattr(task, "id", 0) or 0))
            if not isinstance(ae_command, Mapping):
                return {}

            payload = ae_command.get("payload")
            payload = payload if isinstance(payload, Mapping) else {}
            external_id = str(ae_command.get("external_id") or "").strip() or None
            cmd_id = str(payload.get("cmd_id") or "").strip() or None

            legacy_command = None
            if external_id:
                legacy_command = await repository.get_legacy_command_by_id(external_id=external_id)
            elif cmd_id:
                legacy_command = await repository.get_legacy_command_by_cmd_id(
                    zone_id=int(getattr(task, "zone_id", 0) or 0),
                    cmd_id=cmd_id,
                )

            node_uid = str(ae_command.get("node_uid") or "").strip() or None
            if node_uid is None and isinstance(legacy_command, Mapping):
                node_uid = str(legacy_command.get("node_uid") or "").strip() or None

            node_context = None
            if node_uid:
                node_context = await repository.get_node_runtime_context(node_uid=node_uid)

            timeout_details = self.compose_timeout_details(
                task=task,
                ae_command=ae_command,
                payload=payload,
                legacy_command=legacy_command,
                node_context=node_context,
                now=now,
            )
            if timeout_details is None:
                return {}

            result: dict[str, Any] = {"timed_out_command": timeout_details}
            if self.is_startup_probe_timeout(task=task, timeout_details=timeout_details):
                result["startup_probe_timeout"] = {
                    "probe_name": timeout_details.get("probe_name"),
                    "cmd_id": timeout_details.get("cmd_id"),
                    "node_uid": timeout_details.get("node_uid"),
                    "channel": timeout_details.get("channel"),
                    "command": timeout_details.get("command"),
                    "publish_status": timeout_details.get("publish_status"),
                    "legacy_status": timeout_details.get("legacy_status"),
                    "node_status": timeout_details.get("node_status"),
                    "node_last_seen_at": timeout_details.get("node_last_seen_at"),
                    "node_last_seen_age_sec": timeout_details.get("node_last_seen_age_sec"),
                    "node_stale_online_candidate": timeout_details.get("node_stale_online_candidate"),
                    "timeout_at": timeout_details.get("timeout_at"),
                }
            return result
        except Exception:
            logger.warning(
                "AE3 не смог обогатить observability details для command_timeout: zone_id=%s task_id=%s",
                getattr(task, "zone_id", None),
                getattr(task, "id", None),
                exc_info=True,
            )
            return {}

    def compose_timeout_details(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        payload: Mapping[str, Any],
        legacy_command: Mapping[str, Any] | None,
        node_context: Mapping[str, Any] | None,
        now: datetime,
    ) -> dict[str, Any] | None:
        node_uid = str(ae_command.get("node_uid") or "").strip() or None
        channel = str(ae_command.get("channel") or "").strip() or None
        cmd_id = str(payload.get("cmd_id") or "").strip() or None
        command_name = str(payload.get("cmd") or "").strip() or None
        probe_name = str(payload.get("name") or "").strip() or None
        if not any((node_uid, channel, cmd_id, command_name, probe_name, legacy_command, node_context)):
            return None

        sent_at = legacy_command.get("sent_at") if isinstance(legacy_command, Mapping) else None
        ack_at = legacy_command.get("ack_at") if isinstance(legacy_command, Mapping) else None
        failed_at = legacy_command.get("failed_at") if isinstance(legacy_command, Mapping) else None
        node_last_seen_at = node_context.get("last_seen_at") if isinstance(node_context, Mapping) else None

        node_last_seen_age_sec: int | None = None
        if isinstance(node_last_seen_at, datetime):
            normalized_now = (
                now.astimezone(timezone.utc) if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
            )
            normalized_last_seen = (
                node_last_seen_at.astimezone(timezone.utc)
                if node_last_seen_at.tzinfo is not None
                else node_last_seen_at.replace(tzinfo=timezone.utc)
            )
            node_last_seen_age_sec = max(
                0,
                int((normalized_now - normalized_last_seen).total_seconds()),
            )

        node_status = (
            str(node_context.get("node_status") or "").strip().lower() or None
            if isinstance(node_context, Mapping)
            else None
        )
        node_stale_online_candidate = (
            node_status == "online"
            and node_last_seen_age_sec is not None
            and node_last_seen_age_sec >= NODE_STALE_ONLINE_THRESHOLD_SEC
        )

        details: dict[str, Any] = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or ""),
            "cmd_id": cmd_id,
            "command": command_name,
            "probe_name": probe_name,
            "node_uid": node_uid,
            "channel": channel,
            "publish_status": str(ae_command.get("publish_status") or "").strip().lower() or None,
            "terminal_status": str(ae_command.get("terminal_status") or "").strip().upper() or None,
            "legacy_command_id": int(legacy_command["id"])
            if isinstance(legacy_command, Mapping) and legacy_command.get("id") is not None
            else None,
            "legacy_status": str(legacy_command.get("status") or "").strip().upper() or None
            if isinstance(legacy_command, Mapping)
            else None,
            "sent_at": sent_at.isoformat() if isinstance(sent_at, datetime) else None,
            "ack_at": ack_at.isoformat() if isinstance(ack_at, datetime) else None,
            "failed_at": failed_at.isoformat() if isinstance(failed_at, datetime) else None,
            "timeout_at": now.astimezone(timezone.utc).isoformat()
            if now.tzinfo is not None
            else now.replace(tzinfo=timezone.utc).isoformat(),
            "node_status": node_status,
            "node_type": str(node_context.get("node_type") or "").strip().lower() or None
            if isinstance(node_context, Mapping)
            else None,
            "node_last_seen_at": node_last_seen_at.isoformat() if isinstance(node_last_seen_at, datetime) else None,
            "node_last_seen_age_sec": node_last_seen_age_sec,
            "node_stale_online_candidate": node_stale_online_candidate,
        }
        return {key: value for key, value in details.items() if value is not None}

    def is_startup_probe_timeout(self, *, task: Any, timeout_details: Mapping[str, Any]) -> bool:
        return (
            str(getattr(task, "current_stage", "") or "").strip().lower() == "startup"
            and str(timeout_details.get("channel") or "").strip().lower() == "storage_state"
            and str(timeout_details.get("command") or "").strip().lower() == "state"
        )
