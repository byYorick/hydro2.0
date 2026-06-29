"""Диагностика зависаний two-tank workflow и runtime AE3 для UI observability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from ae3lite.domain.services.workflow_failure_rollback import resolve_diagnostic_stage_after_rollback
from common.observability_thresholds import (
    resolved_thresholds,
    should_skip_correction_substep_stalled_hint,
    should_skip_stage_elapsed_long_hint,
    stage_threshold_pair,
)

_ACTIVE_TASK_STATUSES = frozenset({"pending", "claimed", "running", "waiting_command"})
_DISPATCH_STUCK_STATUSES = frozenset({"pending", "claimed"})

_HANG_HINT_LABELS: dict[str, str] = {
    "stage_deadline_exceeded": "Превышен дедлайн текущего этапа",
    "waiting_command_stuck": "Задача ждёт ответа по команде дольше ожидаемого",
    "stage_elapsed_long": "Этап выполняется дольше типового времени",
    "workflow_snapshot_stale": "Снимок workflow в БД не обновлялся при активной фазе",
    "no_active_task_during_workflow": "Активная фаза workflow без running-задачи AE3",
    "level_sensors_unlatched": "Датчики уровня не подтверждают заполнение баков",
    "telemetry_unavailable": "Телеметрия зоны недоступна для диагностики",
    "correction_substep_stalled": "Подшаг коррекции pH/EC выполняется слишком долго",
    "nodes_offline": "Обязательные узлы зоны offline или stale",
    "task_dispatch_stuck": "Задача AE3 не переходит в running дольше ожидаемого",
    "level_clean_max_unlatched": "Верхний уровень чистой воды не подтверждён",
    "level_solution_max_unlatched": "Верхний уровень раствора не подтверждён",
    "level_solution_min_unlatched": "Нижний уровень раствора не подтверждён",
}

_HANG_HINT_RECOMMENDATIONS: dict[str, str] = {
    "stage_deadline_exceeded": "Проверьте датчики уровня, узел irrig и последние команды fill/stop.",
    "waiting_command_stuck": "Проверьте MQTT, history-logger и command_response для последней команды.",
    "stage_elapsed_long": "Сверьте уровни баков, online-статус irrig-ноды и журнал zone_events.",
    "workflow_snapshot_stale": "Возможен рестарт AE или зависшая задача — проверьте ae_tasks и логи AE3.",
    "no_active_task_during_workflow": "Запустите start-cycle или проверьте pending intent планировщика.",
    "level_sensors_unlatched": "Перезапустите fill workflow или проверьте физику/симулятор level_switch.",
    "telemetry_unavailable": "Проверьте history-logger и sensors/telemetry_last для зоны.",
    "correction_substep_stalled": "Проверьте pH/EC сенсоры, насосы дозирования и corr_step в ae_tasks.",
    "nodes_offline": "Проверьте питание, Wi‑Fi/MQTT и last_seen_at узлов irrig/ph/ec.",
    "task_dispatch_stuck": "Проверьте lease AE3, очередь claim и логи automation-engine.",
    "level_clean_max_unlatched": "Перезапустите clean fill или проверьте level_clean_max / симулятор.",
    "level_solution_max_unlatched": "Перезапустите solution fill или проверьте level_solution_max.",
    "level_solution_min_unlatched": "Проверьте уровень раствора и гидравлику бака.",
}


def _normalize_utc_naive(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _iso_or_none(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


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
    hints.append({
        "code": code,
        "severity": severity,
        "message": message,
        "recommendation": recommendation or _HANG_HINT_RECOMMENDATIONS.get(code),
        "details": dict(details or {}),
    })


def build_automation_observability(
    *,
    zone_id: int,
    task: Any | None,
    workflow_state: Any | None,
    telemetry: Mapping[str, Any],
    telemetry_fetch_ok: bool,
    now: datetime,
    node_rows: Sequence[Mapping[str, Any]] | None = None,
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Собирает runtime-диагностику для `/zones/{id}/state`."""
    cfg = resolved_thresholds(thresholds)
    hints: list[dict[str, Any]] = []
    runtime: dict[str, Any] = {
        "zone_id": zone_id,
        "task_id": None,
        "task_status": None,
        "task_is_active": False,
        "current_stage": None,
        "workflow_phase": None,
        "stage_entered_at": None,
        "stage_elapsed_sec": 0,
        "stage_deadline_at": None,
        "stage_deadline_remaining_sec": None,
        "waiting_command": False,
        "correction_step": None,
        "pending_manual_step": None,
        "topology": None,
        "workflow_snapshot_updated_at": None,
        "workflow_snapshot_age_sec": None,
        "waiting_elapsed_sec": 0,
        "task_updated_age_sec": None,
    }

    status = ""
    wf = None
    task_updated_at: datetime | None = None
    if task is not None:
        status = str(getattr(task, "status", "") or "").strip().lower()
        wf = getattr(task, "workflow", None)
        runtime["task_id"] = getattr(task, "id", None)
        runtime["task_status"] = status or None
        runtime["task_is_active"] = status in _ACTIVE_TASK_STATUSES
        runtime["topology"] = getattr(task, "topology", None)
        runtime["current_stage"] = getattr(wf, "current_stage", None) if wf is not None else None
        runtime["workflow_phase"] = getattr(wf, "workflow_phase", None) if wf is not None else None
        runtime["pending_manual_step"] = getattr(wf, "pending_manual_step", None) if wf is not None else None

        stage_entered_at = _normalize_utc_naive(getattr(wf, "stage_entered_at", None) if wf is not None else None)
        runtime["stage_entered_at"] = _iso_or_none(stage_entered_at)
        if stage_entered_at is not None:
            if status == "failed":
                completed_at = _normalize_utc_naive(getattr(task, "completed_at", None))
                end_at = completed_at if completed_at is not None else now
                runtime["stage_elapsed_sec"] = max(0, int((end_at - stage_entered_at).total_seconds()))
            else:
                runtime["stage_elapsed_sec"] = max(0, int((now - stage_entered_at).total_seconds()))

        stage_deadline_at = _normalize_utc_naive(getattr(wf, "stage_deadline_at", None) if wf is not None else None)
        runtime["stage_deadline_at"] = _iso_or_none(stage_deadline_at)
        if stage_deadline_at is not None and status != "failed":
            runtime["stage_deadline_remaining_sec"] = int((stage_deadline_at - now).total_seconds())

        runtime["waiting_command"] = status == "waiting_command"

        task_updated_at = _normalize_utc_naive(getattr(task, "updated_at", None))
        if task_updated_at is not None:
            runtime["task_updated_age_sec"] = max(0, int((now - task_updated_at).total_seconds()))

        correction = getattr(task, "correction", None)
        if correction is not None and status in _ACTIVE_TASK_STATUSES:
            runtime["correction_step"] = str(getattr(correction, "corr_step", "") or "").strip() or None
            wait_until = _normalize_utc_naive(getattr(correction, "wait_until", None))
            runtime["correction_wait_until"] = _iso_or_none(wait_until)
            if wait_until is not None:
                runtime["correction_wait_remaining_sec"] = int((wait_until - now).total_seconds())
            stabilization_sec = getattr(correction, "stabilization_sec", None)
            if stabilization_sec is not None:
                try:
                    runtime["correction_stabilization_sec"] = int(stabilization_sec)
                except (TypeError, ValueError):
                    pass

    if workflow_state is not None:
        wf_updated = _normalize_utc_naive(getattr(workflow_state, "updated_at", None))
        runtime["workflow_snapshot_updated_at"] = _iso_or_none(wf_updated)
        if wf_updated is not None:
            runtime["workflow_snapshot_age_sec"] = max(0, int((now - wf_updated).total_seconds()))
        if runtime.get("workflow_phase") in (None, "", "idle"):
            wf_phase = str(getattr(workflow_state, "workflow_phase", "") or "").strip().lower()
            if wf_phase:
                runtime["workflow_phase"] = wf_phase
        if not runtime.get("current_stage"):
            payload = getattr(workflow_state, "payload", None)
            if isinstance(payload, Mapping):
                stage_from_payload = str(payload.get("ae3_cycle_start_stage") or "").strip()
                wf_phase = str(getattr(workflow_state, "workflow_phase", "") or "").strip().lower()
                display_stage = resolve_diagnostic_stage_after_rollback(
                    workflow_phase=wf_phase,
                    payload=payload,
                    raw_stage=stage_from_payload or None,
                )
                if display_stage:
                    runtime["current_stage"] = display_stage

    if not telemetry_fetch_ok:
        _append_hint(
            hints,
            code="telemetry_unavailable",
            severity="warning",
            message=_HANG_HINT_LABELS["telemetry_unavailable"],
        )

    current_stage = str(runtime.get("current_stage") or "").strip().lower()
    stage_elapsed = int(runtime.get("stage_elapsed_sec") or 0)
    workflow_phase = str(runtime.get("workflow_phase") or "").strip().lower()
    task_updated_age = runtime.get("task_updated_age_sec")
    waiting_elapsed = stage_elapsed
    if runtime["waiting_command"] and isinstance(task_updated_age, int):
        waiting_elapsed = task_updated_age
    runtime["waiting_elapsed_sec"] = waiting_elapsed

    if runtime["waiting_command"]:
        severity = _severity_for_elapsed(
            waiting_elapsed,
            cfg["waiting_command_warn_sec"],
            cfg["waiting_command_critical_sec"],
        )
        if severity is not None:
            _append_hint(
                hints,
                code="waiting_command_stuck",
                severity=severity,
                message=_HANG_HINT_LABELS["waiting_command_stuck"],
                details={
                    "waiting_elapsed_sec": waiting_elapsed,
                    "stage_elapsed_sec": stage_elapsed,
                    "task_status": status,
                },
            )

    if status in _DISPATCH_STUCK_STATUSES and isinstance(task_updated_age, int):
        severity = _severity_for_elapsed(
            task_updated_age,
            cfg["task_dispatch_warn_sec"],
            cfg["task_dispatch_critical_sec"],
        )
        if severity is not None:
            _append_hint(
                hints,
                code="task_dispatch_stuck",
                severity=severity,
                message=_HANG_HINT_LABELS["task_dispatch_stuck"],
                details={"task_status": status, "task_updated_age_sec": task_updated_age},
            )

    stage_deadline_remaining = runtime.get("stage_deadline_remaining_sec")
    if isinstance(stage_deadline_remaining, int) and stage_deadline_remaining < 0 and runtime["task_is_active"]:
        _append_hint(
            hints,
            code="stage_deadline_exceeded",
            severity="critical",
            message=_HANG_HINT_LABELS["stage_deadline_exceeded"],
            details={
                "overdue_sec": abs(stage_deadline_remaining),
                "current_stage": current_stage or None,
            },
        )

    stage_pair = stage_threshold_pair(cfg, current_stage)
    deadline_remaining = runtime.get("stage_deadline_remaining_sec")
    skip_elapsed_long = should_skip_stage_elapsed_long_hint(
        stage=current_stage,
        stage_deadline_remaining_sec=deadline_remaining if isinstance(deadline_remaining, int) else None,
    )
    if stage_pair is not None and runtime["task_is_active"] and not skip_elapsed_long:
        severity = _severity_for_elapsed(stage_elapsed, stage_pair[0], stage_pair[1])
        if severity is not None:
            _append_hint(
                hints,
                code="stage_elapsed_long",
                severity=severity,
                message=f"{_HANG_HINT_LABELS['stage_elapsed_long']}: {current_stage}",
                details={"stage_elapsed_sec": stage_elapsed, "current_stage": current_stage},
            )

    corr_step = str(runtime.get("correction_step") or "").strip().lower()
    if corr_step.startswith("corr_wait") and runtime["task_is_active"]:
        wait_remaining = runtime.get("correction_wait_remaining_sec")
        wait_remaining_int = wait_remaining if isinstance(wait_remaining, int) else None
        substep_elapsed = task_updated_age if isinstance(task_updated_age, int) else stage_elapsed
        skip_correction_stall = should_skip_correction_substep_stalled_hint(
            correction_step=corr_step,
            correction_wait_remaining_sec=wait_remaining_int,
            substep_elapsed_sec=substep_elapsed,
            stabilization_sec=runtime.get("correction_stabilization_sec")
            if isinstance(runtime.get("correction_stabilization_sec"), int)
            else None,
        )
        if not skip_correction_stall and substep_elapsed >= cfg["correction_substep_warn_sec"]:
            _append_hint(
                hints,
                code="correction_substep_stalled",
                severity="warning" if substep_elapsed < cfg["correction_substep_critical_sec"] else "critical",
                message=f"{_HANG_HINT_LABELS['correction_substep_stalled']} ({corr_step})",
                details={
                    "correction_step": corr_step,
                    "substep_elapsed_sec": substep_elapsed,
                    "stage_elapsed_sec": stage_elapsed,
                    "correction_wait_remaining_sec": wait_remaining_int,
                },
            )

    wf_age = runtime.get("workflow_snapshot_age_sec")
    active_phases = {"tank_filling", "tank_recirc", "irrigating", "irrig_recirc"}
    db_workflow_phase = ""
    if workflow_state is not None:
        db_workflow_phase = str(getattr(workflow_state, "workflow_phase", "") or "").strip().lower()
    stale_phase = db_workflow_phase if db_workflow_phase else workflow_phase
    if (
        isinstance(wf_age, int)
        and wf_age >= cfg["workflow_snapshot_stale_warn_sec"]
        and stale_phase in active_phases
        and runtime.get("task_is_active")
    ):
        _append_hint(
            hints,
            code="workflow_snapshot_stale",
            severity="warning" if wf_age < cfg["workflow_snapshot_stale_critical_sec"] else "critical",
            message=_HANG_HINT_LABELS["workflow_snapshot_stale"],
            details={"workflow_snapshot_age_sec": wf_age, "workflow_phase": workflow_phase},
        )

    if (
        task is None
        and workflow_state is not None
        and stale_phase in active_phases
        and runtime.get("task_status") != "failed"
    ):
        _append_hint(
            hints,
            code="no_active_task_during_workflow",
            severity="warning",
            message=_HANG_HINT_LABELS["no_active_task_during_workflow"],
            details={"workflow_phase": workflow_phase},
        )

    # Level sensors: only for active tasks on relevant check-stages.
    if runtime["task_is_active"] and telemetry_fetch_ok:
        clean_max = bool(telemetry.get("clean_max_triggered"))
        solution_max = bool(telemetry.get("solution_max_triggered"))
        solution_min = bool(telemetry.get("solution_min_triggered"))
        if current_stage in {"clean_fill_check", "clean_fill_start"} and not clean_max and stage_elapsed >= cfg["level_clean_max_unlatched_sec"]:
            _append_hint(
                hints,
                code="level_clean_max_unlatched",
                severity="warning",
                message=_HANG_HINT_LABELS["level_clean_max_unlatched"],
                details={"clean_max_triggered": clean_max, "current_stage": current_stage},
            )
        if current_stage in {"solution_fill_check"} and not solution_max and stage_elapsed >= cfg["level_solution_max_unlatched_sec"]:
            _append_hint(
                hints,
                code="level_solution_max_unlatched",
                severity="warning",
                message=_HANG_HINT_LABELS["level_solution_max_unlatched"],
                details={"solution_max_triggered": solution_max, "current_stage": current_stage},
            )
        if current_stage in {"irrigation_recovery_check"} and not solution_min and stage_elapsed >= cfg["level_solution_min_unlatched_sec"]:
            _append_hint(
                hints,
                code="level_solution_min_unlatched",
                severity="warning",
                message=_HANG_HINT_LABELS["level_solution_min_unlatched"],
                details={"solution_min_triggered": solution_min, "current_stage": current_stage},
            )

    nodes_summary = _summarize_required_nodes(node_rows or (), cfg)
    if nodes_summary.get("offline_required"):
        _append_hint(
            hints,
            code="nodes_offline",
            severity="critical" if nodes_summary.get("persistent_offline") else "warning",
            message=_HANG_HINT_LABELS["nodes_offline"],
            details={"nodes": nodes_summary.get("nodes", [])},
        )

    overall = _overall_health(hints, runtime)
    return {
        "runtime": runtime,
        "nodes": nodes_summary,
        "hang_hints": _dedupe_hints(hints),
        "overall_health": overall,
    }


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
        is_stale_online = is_online and last_seen_age_sec is not None and last_seen_age_sec >= cfg["nodes_stale_online_sec"]
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
            if not is_online and last_seen_age_sec is not None and last_seen_age_sec >= cfg["nodes_persistent_offline_sec"]:
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


__all__ = ["build_automation_observability"]
