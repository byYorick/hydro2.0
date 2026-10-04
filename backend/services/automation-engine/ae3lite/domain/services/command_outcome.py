"""Чистая интерпретация command outcome; общий контракт normal/recovery."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from ae3lite.domain.errors import TaskExecutionError

NON_TERMINAL_STATUSES = frozenset({"PENDING", "QUEUED", "SENT", "ACK", "RUNNING"})
TERMINAL_STATUSES = frozenset({"DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"})
PROTOCOL_VIOLATION_STATUSES = frozenset({"ACCEPTED"})


@dataclass(frozen=True)
class CommandOutcome:
    status: str
    terminal_status: str | None
    terminal_at: datetime | None
    last_error: str | None


def decode_command_outcome(row: Mapping[str, Any]) -> CommandOutcome:
    status = str(row.get("status") or "").strip().upper()
    if status in PROTOCOL_VIOLATION_STATUSES:
        raise TaskExecutionError("command_protocol_violation", f"Legacy status {status} не является terminal outcome протокола 2.0")
    if status not in NON_TERMINAL_STATUSES | TERMINAL_STATUSES:
        raise TaskExecutionError("ae3_unsupported_legacy_status", f"Неподдерживаемый legacy status={status or 'empty'}")
    terminal = status if status in TERMINAL_STATUSES else None
    return CommandOutcome(
        status=status,
        terminal_status=terminal,
        terminal_at=(row.get("failed_at") or row.get("ack_at") or row.get("updated_at") or row.get("sent_at") or row.get("created_at")),
        last_error=None if terminal in {None, "DONE"} else str(row.get("error_message") or status),
    )


def response_details_from_legacy_row(legacy_row: Mapping[str, Any]) -> dict[str, Any]:
    """Собрать dose feedback из legacy ``commands`` (duration_ms + params)."""
    details: dict[str, Any] = {}
    raw_duration = legacy_row.get("duration_ms")
    if raw_duration is not None:
        try:
            actual_ms = max(0, int(raw_duration))
        except (TypeError, ValueError):
            actual_ms = 0
        if actual_ms > 0:
            details["duration_ms"] = actual_ms

    params = legacy_row.get("params")
    param_block: Mapping[str, Any] = {}
    if isinstance(params, Mapping):
        param_block = params
        nested = params.get("params")
        if isinstance(nested, Mapping):
            param_block = nested

    if param_block:
        planned_ms = param_block.get("duration_ms")
        if details.get("duration_ms") and planned_ms is not None:
            try:
                if int(planned_ms) > int(details["duration_ms"]):
                    details["duration_limited"] = True
            except (TypeError, ValueError):
                pass
        planned_ml = param_block.get("ml")
        if planned_ml is not None:
            try:
                details["ml"] = float(planned_ml)
            except (TypeError, ValueError):
                pass
        node_mps = param_block.get("ml_per_second")
        if node_mps is None:
            node_mps = param_block.get("ml_per_sec")
        if node_mps is not None:
            try:
                details["ml_per_second"] = float(node_mps)
            except (TypeError, ValueError):
                pass
    return details
