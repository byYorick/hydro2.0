"""automation diagnostics hints: one cohesive policy."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ae3lite.application.services.automation_diagnostics_values import (
    _HANG_HINT_RECOMMENDATIONS,
    _SENSOR_BLOCK_REASONS,
    _SOLUTION_TEMP_BLOCK_REASONS,
)


def _severity_for_elapsed(elapsed_sec: int, warn_sec: int, critical_sec: int) -> str | None:
    if elapsed_sec >= critical_sec:
        return "critical"
    if elapsed_sec >= warn_sec:
        return "warning"
    return None


def _append_hint(
    hints: list[dict[str, Any]],
    *,
    code: str,
    severity: str,
    message: str,
    recommendation: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    hints.append(
        {
            "code": code,
            "severity": severity,
            "message": message,
            "recommendation": recommendation or _HANG_HINT_RECOMMENDATIONS.get(code),
            "details": dict(details or {}),
        }
    )


def _append_irrigation_block_hint(hints: list[dict[str, Any]], task: Any | None) -> None:
    """Подсказка по колонкам последней задачи полива. Не решает полив заново."""
    if task is None:
        return
    task_type = str(getattr(task, "task_type", "") or "").strip().lower()
    if task_type not in {"", "irrigation_start"}:
        return
    outcome = str(getattr(task, "irrigation_decision_outcome", "") or "").strip().lower()
    if outcome != "skip":
        return
    reason = str(getattr(task, "irrigation_decision_reason_code", "") or "").strip().lower()
    if reason in _SENSOR_BLOCK_REASONS:
        code = "irrigation_sensor_blocked"
        if reason == "smart_soil_target_missing":
            message = "Полив пропущен: не задана цель влажности. Насос не запускался."
        else:
            message = "Полив пропущен: нет свежего измерения влажности. Насос не запускался."
    elif reason in _SOLUTION_TEMP_BLOCK_REASONS:
        code = "solution_temp_blocked"
        if reason == "solution_temp_unavailable":
            message = "Полив пропущен: нет свежей температуры раствора. Насос не запускался."
        else:
            message = "Полив пропущен: температура раствора вне пределов фазы. Насос не запускался."
    else:
        return
    details: dict[str, Any] = {"reason_code": reason}
    task_id = getattr(task, "id", None)
    if task_id is not None:
        details["task_id"] = task_id
    _append_hint(
        hints,
        code=code,
        severity="critical",
        message=message,
        details=details,
    )


def _summarize_required_nodes(rows: Sequence[Mapping[str, Any]], cfg: Mapping[str, int]) -> dict[str, Any]:
    required_types = {"irrig", "ph", "ec"}
    nodes: list[dict[str, Any]] = []
    offline_required: list[str] = []
    persistent_offline = False

    for row in rows:
        node_type = str(row.get("node_type") or row.get("type") or "").strip().lower()
        node_uid = str(row.get("node_uid") or row.get("uid") or "").strip()
        status = str(row.get("status") or "").strip().lower()
        age_raw = row.get("last_seen_age_sec")
        try:
            last_seen_age_sec = int(age_raw) if age_raw is not None else None
        except (TypeError, ValueError):
            last_seen_age_sec = None

        is_online = status == "online"
        is_stale_online = (
            is_online and last_seen_age_sec is not None and last_seen_age_sec >= cfg["nodes_stale_online_sec"]
        )
        entry = {
            "uid": node_uid or None,
            "type": node_type or None,
            "status": status or None,
            "last_seen_age_sec": last_seen_age_sec,
            "required": node_type in required_types,
            "healthy": is_online and not is_stale_online,
        }
        nodes.append(entry)

        if node_type in required_types and (not is_online or is_stale_online):
            offline_required.append(node_uid or node_type)
            if (
                not is_online
                and last_seen_age_sec is not None
                and last_seen_age_sec >= cfg["nodes_persistent_offline_sec"]
            ):
                persistent_offline = True

    return {
        "nodes": nodes,
        "offline_required": offline_required,
        "persistent_offline": persistent_offline,
    }


def _dedupe_hints(hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    severity_rank = {"critical": 2, "warning": 1, "info": 0}
    for hint in sorted(
        hints,
        key=lambda item: severity_rank.get(str(item.get("severity")), 0),
        reverse=True,
    ):
        code = str(hint.get("code") or "")
        dedupe_key = code if code else str(hint.get("message") or "")
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        result.append(hint)
    return result


def _overall_health(hints: list[dict[str, Any]], runtime: Mapping[str, Any]) -> str:
    if any(str(h.get("severity")) == "critical" for h in hints):
        return "critical"
    if any(str(h.get("severity")) == "warning" for h in hints):
        return "warning"
    if runtime.get("task_is_active"):
        return "active"
    return "idle"
