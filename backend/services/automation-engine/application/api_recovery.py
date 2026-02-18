"""Recovery helpers for API startup flows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from services.resilience_contract import (
    INFRA_SCHEDULER_TASK_RECOVERY_EVENT_FAILED,
    INFRA_SCHEDULER_TASK_RECOVERY_PERSIST_FAILED,
    INFRA_WORKFLOW_STATE_RECOVERY_ENQUEUE_FAILED,
    INFRA_WORKFLOW_STATE_RECOVERY_ROW_FAILED,
)


RecoverySummary = Dict[str, int]


def _task_id_from_log_name(task_name: Any) -> Optional[str]:
    if not isinstance(task_name, str):
        return None
    prefix = "ae_scheduler_task_"
    if not task_name.startswith(prefix):
        return None
    task_id = task_name[len(prefix):].strip()
    return task_id or None


async def recover_inflight_scheduler_tasks(
    *,
    enabled: bool,
    fetch_fn: Callable[..., Awaitable[Any]],
    scan_limit: int,
    build_execution_terminal_result_fn: Callable[..., Dict[str, Any]],
    scheduler_tasks: Dict[str, Dict[str, Any]],
    scheduler_tasks_lock: Any,
    persist_scheduler_task_snapshot_fn: Callable[[Dict[str, Any]], Awaitable[None]],
    create_zone_event_fn: Callable[[int, str, Dict[str, Any]], Awaitable[Any]],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    task_recovery_success_rate_gauge: Any,
    logger: logging.Logger,
) -> RecoverySummary:
    if not enabled:
        return {"scanned": 0, "inflight": 0, "recovered": 0}

    try:
        rows = await fetch_fn(
            """
            WITH recent_logs AS (
                SELECT id, task_name, status, details, created_at
                FROM scheduler_logs
                WHERE task_name LIKE 'ae_scheduler_task_st-%'
                ORDER BY created_at DESC, id DESC
                LIMIT $1
            )
            SELECT DISTINCT ON (task_name)
                task_name, status, details, created_at
            FROM recent_logs
            ORDER BY task_name, created_at DESC, id DESC
            """,
            scan_limit,
        )
    except Exception:
        logger.warning("Scheduler task recovery scan failed", exc_info=True)
        return {"scanned": 0, "inflight": 0, "recovered": 0}

    scanned = len(rows)
    inflight = 0
    recovered = 0
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    for row in rows:
        details = row.get("details") if isinstance(row.get("details"), dict) else {}
        raw_status = details.get("status") if isinstance(details, dict) else None
        if not raw_status:
            raw_status = row.get("status")
        status = str(raw_status or "").strip().lower()
        if status not in {"accepted", "running"}:
            continue
        inflight += 1

        task_id = details.get("task_id") if isinstance(details, dict) else None
        if not task_id:
            task_id = _task_id_from_log_name(row.get("task_name"))
        zone_id = details.get("zone_id") if isinstance(details, dict) else None
        task_type = details.get("task_type") if isinstance(details, dict) else None
        if not task_id or not zone_id or not task_type:
            continue

        recovery_result = build_execution_terminal_result_fn(
            error_code="task_recovered_after_restart",
            reason="Automation-engine перезапущен: in-flight задача финализирована recovery-политикой",
            mode="startup_recovery_finalize",
            action_required=True,
            decision="fail",
            reason_code="task_recovered_after_restart",
        )

        recovered_task = {
            "task_id": task_id,
            "zone_id": zone_id,
            "task_type": task_type,
            "status": "failed",
            "created_at": details.get("created_at") if isinstance(details, dict) else None,
            "updated_at": now_iso,
            "scheduled_for": details.get("scheduled_for") if isinstance(details, dict) else None,
            "due_at": details.get("due_at") if isinstance(details, dict) else None,
            "expires_at": details.get("expires_at") if isinstance(details, dict) else None,
            "correlation_id": details.get("correlation_id") if isinstance(details, dict) else None,
            "payload_fingerprint": details.get("payload_fingerprint") if isinstance(details, dict) else None,
            "payload": details.get("payload") if isinstance(details.get("payload"), dict) else {},
            "result": recovery_result,
            "error": "task_recovered_after_restart",
            "error_code": "task_recovered_after_restart",
        }

        if not recovered_task["created_at"]:
            created_at = row.get("created_at")
            recovered_task["created_at"] = created_at.isoformat() if hasattr(created_at, "isoformat") else now_iso

        async with scheduler_tasks_lock:
            scheduler_tasks[task_id] = recovered_task

        try:
            await persist_scheduler_task_snapshot_fn(recovered_task)
        except Exception as exc:
            logger.warning(
                "Failed to persist recovered scheduler task snapshot: task_id=%s error=%s",
                task_id,
                exc,
                exc_info=True,
            )
            await send_infra_exception_alert_fn(
                error=exc,
                code=INFRA_SCHEDULER_TASK_RECOVERY_PERSIST_FAILED,
                alert_type="Scheduler Task Recovery Persist Failed",
                severity="error",
                zone_id=int(zone_id),
                service="automation-engine",
                component="scheduler_task_recovery",
                error_type=type(exc).__name__,
                details={"task_id": task_id, "task_type": task_type},
            )

        try:
            await create_zone_event_fn(
                int(zone_id),
                "SCHEDULE_TASK_FAILED",
                {
                    "task_id": task_id,
                    "task_type": task_type,
                    "status": "failed",
                    "error_code": "task_recovered_after_restart",
                    "source": "automation_engine_startup_recovery",
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to publish recovery zone event: task_id=%s zone_id=%s error=%s",
                task_id,
                zone_id,
                exc,
                exc_info=True,
            )
            await send_infra_exception_alert_fn(
                error=exc,
                code=INFRA_SCHEDULER_TASK_RECOVERY_EVENT_FAILED,
                alert_type="Scheduler Task Recovery Event Failed",
                severity="error",
                zone_id=int(zone_id),
                service="automation-engine",
                component="scheduler_task_recovery",
                error_type=type(exc).__name__,
                details={"task_id": task_id, "task_type": task_type},
            )
        recovered += 1

    if inflight <= 0:
        task_recovery_success_rate_gauge.set(1.0)
    else:
        task_recovery_success_rate_gauge.set(recovered / inflight)

    return {"scanned": scanned, "inflight": inflight, "recovered": recovered}


def _normalize_recovery_phase(raw_phase: Any) -> str:
    value = str(raw_phase or "").strip().lower()
    if value in {"idle", "tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"}:
        return value
    return "idle"


def _is_valid_recovery_phase(raw_phase: Any) -> bool:
    value = str(raw_phase or "").strip().lower()
    return value in {"idle", "tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"}


def _extract_recovery_execution_workflow(payload: Dict[str, Any]) -> str:
    targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}
    diagnostics_targets = targets.get("diagnostics") if isinstance(targets.get("diagnostics"), dict) else {}
    execution = diagnostics_targets.get("execution") if isinstance(diagnostics_targets.get("execution"), dict) else {}
    return str(execution.get("workflow") or "").strip().lower()


def _extract_payload_workflow_stage(payload: Dict[str, Any]) -> Tuple[str, str]:
    candidates = [
        ("workflow_stage", payload.get("workflow_stage")),
        ("workflow", payload.get("workflow")),
        ("diagnostics_workflow", payload.get("diagnostics_workflow")),
        ("targets.diagnostics.execution.workflow", _extract_recovery_execution_workflow(payload)),
    ]
    for source, raw_value in candidates:
        value = str(raw_value or "").strip().lower()
        if value:
            return value, f"zone_workflow_state.payload.{source}"
    return "", "zone_workflow_state.payload.workflow_stage"


def _resolve_recovery_phase(
    row: Dict[str, Any],
    payload: Dict[str, Any],
) -> Tuple[str, str, Optional[str]]:
    raw_column_phase = row.get("workflow_phase_raw", row.get("workflow_phase"))
    raw_payload_phase = payload.get("workflow_phase")
    if _is_valid_recovery_phase(raw_column_phase):
        return _normalize_recovery_phase(raw_column_phase), "zone_workflow_state.workflow_phase", None
    if _is_valid_recovery_phase(raw_payload_phase):
        return _normalize_recovery_phase(raw_payload_phase), "zone_workflow_state.payload.workflow_phase", None
    if str(raw_column_phase or "").strip() or str(raw_payload_phase or "").strip():
        return "idle", "zone_workflow_state.workflow_phase", "invalid_phase"
    return "idle", "zone_workflow_state.workflow_phase", None


def _resolve_workflow_for_recovery(
    phase: str,
    payload: Dict[str, Any],
    *,
    zone_id: Optional[int],
    logger: logging.Logger,
) -> Dict[str, Any]:
    payload_workflow, workflow_source = _extract_payload_workflow_stage(payload)
    has_clean_timestamps = bool(
        str(payload.get("clean_fill_started_at") or "").strip()
        or str(payload.get("clean_fill_timeout_at") or "").strip()
    )
    has_solution_timestamps = bool(
        str(payload.get("solution_fill_started_at") or "").strip()
        or str(payload.get("solution_fill_timeout_at") or "").strip()
    )

    tank_filling_fallback = "solution_fill_check"
    if has_clean_timestamps and not has_solution_timestamps:
        tank_filling_fallback = "clean_fill_check"
    elif has_solution_timestamps:
        tank_filling_fallback = "solution_fill_check"

    fallback = {
        "tank_filling": tank_filling_fallback,
        "tank_recirc": "prepare_recirculation_check",
        "irrig_recirc": "irrigation_recovery_check",
    }
    allowed_workflows = {
        "tank_filling": {"clean_fill_check", "solution_fill_check"},
        "tank_recirc": {"prepare_recirculation_check"},
        "irrig_recirc": {"irrigation_recovery_check"},
    }

    mapped = payload_workflow
    if payload_workflow in {"startup", "cycle_start", "refill_check"}:
        mapped = fallback.get(phase, "")
    elif payload_workflow == "prepare_recirculation":
        mapped = "prepare_recirculation_check"
    elif payload_workflow == "irrigation_recovery":
        mapped = "irrigation_recovery_check"

    if mapped:
        allowed = allowed_workflows.get(phase)
        if allowed and mapped in allowed:
            if payload_workflow and payload_workflow != mapped:
                logger.info(
                    "Recovery workflow canonicalized from coarse stage: zone_id=%s phase=%s raw_workflow=%s canonical_workflow=%s",
                    zone_id,
                    phase,
                    payload_workflow,
                    mapped,
                )
                return {
                    "workflow": mapped,
                    "workflow_source": workflow_source,
                    "reason_code": "workflow_stage_canonicalized",
                    "fallback_from": payload_workflow,
                    "fallback_to": mapped,
                }
            return {
                "workflow": mapped,
                "workflow_source": workflow_source,
                "reason_code": "workflow_from_payload",
                "fallback_from": None,
                "fallback_to": None,
            }

        logger.warning(
            "Recovery workflow incompatible with phase, fallback will be used: zone_id=%s phase=%s payload_workflow=%s mapped_workflow=%s",
            zone_id,
            phase,
            payload_workflow or None,
            mapped,
        )

    phase_fallback = fallback.get(phase)
    if phase_fallback:
        if payload_workflow:
            logger.info(
                "Recovery workflow resolved via phase fallback: zone_id=%s phase=%s payload_workflow=%s fallback_workflow=%s",
                zone_id,
                phase,
                payload_workflow,
                phase_fallback,
            )
            return {
                "workflow": phase_fallback,
                "workflow_source": workflow_source,
                "reason_code": "workflow_phase_fallback",
                "fallback_from": mapped or payload_workflow,
                "fallback_to": phase_fallback,
            }
        return {
            "workflow": phase_fallback,
            "workflow_source": workflow_source,
            "reason_code": "workflow_missing_phase_fallback",
            "fallback_from": "missing_workflow",
            "fallback_to": phase_fallback,
        }

    if payload_workflow:
        logger.warning(
            "Recovery workflow unresolved for active phase: zone_id=%s phase=%s payload_workflow=%s",
            zone_id,
            phase,
            payload_workflow,
        )
    return {
        "workflow": None,
        "workflow_source": workflow_source,
        "reason_code": "workflow_unresolved",
        "fallback_from": None,
        "fallback_to": None,
    }


def _extract_recovery_correlation_id(payload: Dict[str, Any]) -> Optional[str]:
    if isinstance(payload.get("recovery"), dict):
        nested = str(payload.get("recovery", {}).get("correlation_id") or "").strip()
        if nested:
            return nested
    correlation_id = str(payload.get("correlation_id") or "").strip()
    return correlation_id or None


def _log_workflow_recovery_action(
    *,
    zone_id: Optional[int],
    workflow_phase_source: str,
    workflow_phase_normalized: str,
    workflow_selected: Optional[str],
    scheduler_task_id_previous: Optional[str],
    recovery_action: str,
    reason_code: str,
    state_age_sec: int,
    correlation_id: Optional[str],
    enqueue_id: Optional[str],
    level: int,
    error_type: Optional[str],
    error_message: Optional[str],
    logger: logging.Logger,
    get_trace_id_fn: Callable[[], Optional[str]],
) -> None:
    details: Dict[str, Any] = {
        "component": "workflow_state_recovery",
        "zone_id": zone_id,
        "workflow_phase_source": workflow_phase_source,
        "workflow_phase_normalized": workflow_phase_normalized,
        "workflow_selected": workflow_selected,
        "scheduler_task_id_previous": scheduler_task_id_previous,
        "recovery_action": recovery_action,
        "reason_code": reason_code,
        "state_age_sec": state_age_sec,
        "correlation_id": correlation_id,
        "enqueue_id": enqueue_id,
    }
    if error_type:
        details["error_type"] = error_type
    if error_message:
        details["error_message"] = error_message
    if level >= logging.ERROR:
        details["trace_id"] = get_trace_id_fn()
    logger.log(level, "Workflow state recovery action", extra=details)


async def _send_workflow_recovery_alert_safe(
    *,
    error: Exception,
    code: str,
    alert_type: str,
    zone_id: Optional[int],
    details: Dict[str, Any],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
) -> None:
    if zone_id is None:
        return
    try:
        await send_infra_exception_alert_fn(
            error=error,
            code=code,
            alert_type=alert_type,
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="workflow_state_recovery",
            error_type=type(error).__name__,
            details=details,
        )
    except Exception as alert_exc:
        logger.warning(
            "Failed to send workflow recovery infra alert: zone_id=%s code=%s error=%s",
            zone_id,
            code,
            alert_exc,
            exc_info=True,
        )


def _coerce_utc_naive(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


async def recover_zone_workflow_states(
    *,
    enabled: bool,
    stale_timeout_sec: int,
    workflow_state_store: Any,
    logger: logging.Logger,
    create_zone_event_fn: Callable[[int, str, Dict[str, Any]], Awaitable[Any]],
    enqueue_internal_scheduler_task_fn: Callable[..., Awaitable[Dict[str, Any]]],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    get_trace_id_fn: Callable[[], Optional[str]],
) -> RecoverySummary:
    if not enabled:
        return {"active": 0, "recovered": 0, "stale_stopped": 0, "skipped": 0, "failed": 0}

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovered = 0
    stale_stopped = 0
    skipped = 0
    failed = 0

    try:
        active_states = await workflow_state_store.list_active()
    except Exception:
        logger.warning("Zone workflow state recovery scan failed", exc_info=True)
        return {"active": 0, "recovered": 0, "stale_stopped": 0, "skipped": 0, "failed": 0}

    for row in active_states:
        zone_id: Optional[int] = None
        phase_source = "zone_workflow_state.workflow_phase"
        phase = "idle"
        workflow: Optional[str] = None
        age_sec = 0
        enqueue_id: Optional[str] = None
        previous_task_id = str(row.get("scheduler_task_id") or "").strip() or None
        correlation_id: Optional[str] = None

        try:
            raw_zone_id = row.get("zone_id")
            try:
                zone_id = int(raw_zone_id)
            except (TypeError, ValueError):
                skipped += 1
                logger.warning(
                    "Workflow recovery skipped invalid row: invalid zone_id raw_zone_id=%r",
                    raw_zone_id,
                )
                _log_workflow_recovery_action(
                    zone_id=None,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=None,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="skip_invalid",
                    reason_code="invalid_zone_id",
                    state_age_sec=age_sec,
                    correlation_id=None,
                    enqueue_id=None,
                    level=logging.WARNING,
                    error_type=None,
                    error_message=None,
                    logger=logger,
                    get_trace_id_fn=get_trace_id_fn,
                )
                continue

            raw_payload = row.get("payload")
            if not isinstance(raw_payload, dict):
                skipped += 1
                logger.warning(
                    "Workflow recovery skipped invalid payload: zone_id=%s payload_type=%s",
                    zone_id,
                    type(raw_payload).__name__,
                )
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=None,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="skip_invalid",
                    reason_code="invalid_payload",
                    state_age_sec=age_sec,
                    correlation_id=None,
                    enqueue_id=None,
                    level=logging.WARNING,
                    error_type=None,
                    error_message=None,
                    logger=logger,
                    get_trace_id_fn=get_trace_id_fn,
                )
                continue

            payload = dict(raw_payload)
            correlation_id = _extract_recovery_correlation_id(payload)
            phase, phase_source, phase_error = _resolve_recovery_phase(row, payload)
            if phase_error is not None:
                skipped += 1
                logger.warning(
                    "Workflow recovery skipped invalid phase: zone_id=%s raw_phase=%r payload_phase=%r",
                    zone_id,
                    row.get("workflow_phase_raw", row.get("workflow_phase")),
                    payload.get("workflow_phase"),
                )
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=None,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="skip_invalid",
                    reason_code=phase_error,
                    state_age_sec=age_sec,
                    correlation_id=correlation_id,
                    enqueue_id=None,
                    level=logging.WARNING,
                    error_type=None,
                    error_message=None,
                    logger=logger,
                    get_trace_id_fn=get_trace_id_fn,
                )
                continue

            updated_at = _coerce_utc_naive(row.get("updated_at")) or now
            age_sec = max(0, int((now - updated_at).total_seconds()))

            if phase in {"idle", "ready"}:
                skipped += 1
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=None,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="skip_idle_ready",
                    reason_code=f"phase_{phase}",
                    state_age_sec=age_sec,
                    correlation_id=correlation_id,
                    enqueue_id=None,
                    level=logging.INFO,
                    error_type=None,
                    error_message=None,
                    logger=logger,
                    get_trace_id_fn=get_trace_id_fn,
                )
                continue

            if age_sec > stale_timeout_sec:
                try:
                    await workflow_state_store.set(
                        zone_id=zone_id,
                        workflow_phase="idle",
                        payload={**payload, "recovery": {"action": "stale_safety_stop", "age_sec": age_sec}},
                        scheduler_task_id=None,
                    )
                    await create_zone_event_fn(
                        zone_id,
                        "WORKFLOW_RECOVERY_STALE_STOPPED",
                        {
                            "previous_workflow_phase": phase,
                            "age_sec": age_sec,
                            "stale_timeout_sec": stale_timeout_sec,
                        },
                    )
                    stale_stopped += 1
                    _log_workflow_recovery_action(
                        zone_id=zone_id,
                        workflow_phase_source=phase_source,
                        workflow_phase_normalized=phase,
                        workflow_selected=None,
                        scheduler_task_id_previous=previous_task_id,
                        recovery_action="stale_stop",
                        reason_code="state_stale_timeout",
                        state_age_sec=age_sec,
                        correlation_id=correlation_id,
                        enqueue_id=None,
                        level=logging.INFO,
                        error_type=None,
                        error_message=None,
                        logger=logger,
                        get_trace_id_fn=get_trace_id_fn,
                    )
                except Exception as exc:
                    failed += 1
                    logger.error(
                        "Failed to stale-stop workflow state during recovery: zone_id=%s phase=%s error=%s",
                        zone_id,
                        phase,
                        exc,
                        exc_info=True,
                    )
                    _log_workflow_recovery_action(
                        zone_id=zone_id,
                        workflow_phase_source=phase_source,
                        workflow_phase_normalized=phase,
                        workflow_selected=None,
                        scheduler_task_id_previous=previous_task_id,
                        recovery_action="failed",
                        reason_code="stale_stop_failed",
                        state_age_sec=age_sec,
                        correlation_id=correlation_id,
                        enqueue_id=None,
                        level=logging.ERROR,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        logger=logger,
                        get_trace_id_fn=get_trace_id_fn,
                    )
                continue

            workflow_resolution = _resolve_workflow_for_recovery(
                phase,
                payload,
                zone_id=zone_id,
                logger=logger,
            )
            workflow = str(workflow_resolution.get("workflow") or "").strip().lower() or None
            reason_code = str(workflow_resolution.get("reason_code") or "").strip().lower() or "workflow_unresolved"
            fallback_from = str(workflow_resolution.get("fallback_from") or "").strip().lower() or None
            fallback_to = str(workflow_resolution.get("fallback_to") or "").strip().lower() or None

            if not workflow:
                skipped += 1
                logger.warning(
                    "Workflow recovery skipped: no continuation workflow resolved: zone_id=%s phase=%s workflow_source=%s",
                    zone_id,
                    phase,
                    workflow_resolution.get("workflow_source"),
                )
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=None,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="skip_invalid",
                    reason_code=reason_code,
                    state_age_sec=age_sec,
                    correlation_id=correlation_id,
                    enqueue_id=None,
                    level=logging.WARNING,
                    error_type=None,
                    error_message=None,
                    logger=logger,
                    get_trace_id_fn=get_trace_id_fn,
                )
                continue

            if fallback_from and fallback_to and fallback_from != fallback_to:
                logger.warning(
                    "Workflow recovery fallback applied: zone_id=%s phase=%s fallback_from=%s fallback_to=%s reason=%s",
                    zone_id,
                    phase,
                    fallback_from,
                    fallback_to,
                    reason_code,
                )
                try:
                    await create_zone_event_fn(
                        zone_id,
                        "WORKFLOW_RECOVERY_WORKFLOW_FALLBACK",
                        {
                            "workflow_phase": phase,
                            "fallback_from": fallback_from,
                            "fallback_to": fallback_to,
                            "reason_code": reason_code,
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to persist workflow fallback event during recovery: zone_id=%s error=%s",
                        zone_id,
                        exc,
                        exc_info=True,
                    )

            continuation_payload = dict(payload)
            continuation_payload["workflow"] = workflow
            continuation_payload["workflow_stage"] = workflow
            continuation_payload["workflow_phase"] = phase
            continuation_payload.setdefault("payload_contract_version", "v2")
            continuation_payload["recovery"] = {
                "source": "automation_engine_startup_recovery",
                "workflow_phase": phase,
                "workflow_phase_source": phase_source,
                "state_age_sec": age_sec,
                "previous_scheduler_task_id": previous_task_id,
                "reason_code": reason_code,
            }

            try:
                enqueue_result = await enqueue_internal_scheduler_task_fn(
                    zone_id=zone_id,
                    task_type="diagnostics",
                    payload=continuation_payload,
                    scheduled_for=now.isoformat(),
                    source="automation-engine:workflow-state-recovery",
                )
                enqueue_id = str(enqueue_result.get("enqueue_id") or "").strip() or None
                correlation_id = correlation_id or (str(enqueue_result.get("correlation_id") or "").strip() or None)
                await workflow_state_store.set(
                    zone_id=zone_id,
                    workflow_phase=phase,
                    payload=continuation_payload,
                    scheduler_task_id=enqueue_id or "",
                )
                await create_zone_event_fn(
                    zone_id,
                    "WORKFLOW_RECOVERY_ENQUEUED",
                    {
                        "workflow_phase": phase,
                        "workflow": workflow,
                        "enqueue_id": enqueue_id,
                        "correlation_id": correlation_id,
                        "state_age_sec": age_sec,
                    },
                )
                recovered += 1
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=workflow,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="enqueue_continuation",
                    reason_code=reason_code,
                    state_age_sec=age_sec,
                    correlation_id=correlation_id,
                    enqueue_id=enqueue_id,
                    level=logging.INFO,
                    error_type=None,
                    error_message=None,
                    logger=logger,
                    get_trace_id_fn=get_trace_id_fn,
                )
            except Exception as exc:
                failed += 1
                logger.error(
                    "Failed to enqueue workflow continuation during startup recovery: zone_id=%s phase=%s error=%s",
                    zone_id,
                    phase,
                    exc,
                    exc_info=True,
                )
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=workflow,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="failed",
                    reason_code="enqueue_failed",
                    state_age_sec=age_sec,
                    correlation_id=correlation_id,
                    enqueue_id=enqueue_id,
                    level=logging.ERROR,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    logger=logger,
                    get_trace_id_fn=get_trace_id_fn,
                )
                await _send_workflow_recovery_alert_safe(
                    error=exc,
                    code=INFRA_WORKFLOW_STATE_RECOVERY_ENQUEUE_FAILED,
                    alert_type="Workflow State Recovery Enqueue Failed",
                    zone_id=zone_id,
                    details={
                        "workflow_phase": phase,
                        "workflow": workflow,
                    },
                    send_infra_exception_alert_fn=send_infra_exception_alert_fn,
                    logger=logger,
                )
        except Exception as exc:
            failed += 1
            logger.error(
                "Unexpected workflow recovery failure for zone row: zone_id=%s error=%s",
                zone_id,
                exc,
                exc_info=True,
            )
            _log_workflow_recovery_action(
                zone_id=zone_id,
                workflow_phase_source=phase_source,
                workflow_phase_normalized=phase,
                workflow_selected=workflow,
                scheduler_task_id_previous=previous_task_id,
                recovery_action="failed",
                reason_code="recovery_exception",
                state_age_sec=age_sec,
                correlation_id=correlation_id,
                enqueue_id=enqueue_id,
                level=logging.ERROR,
                error_type=type(exc).__name__,
                error_message=str(exc),
                logger=logger,
                get_trace_id_fn=get_trace_id_fn,
            )
            await _send_workflow_recovery_alert_safe(
                error=exc,
                code=INFRA_WORKFLOW_STATE_RECOVERY_ROW_FAILED,
                alert_type="Workflow State Recovery Row Failed",
                zone_id=zone_id,
                details={
                    "workflow_phase": phase,
                    "scheduler_task_id_previous": previous_task_id,
                },
                send_infra_exception_alert_fn=send_infra_exception_alert_fn,
                logger=logger,
            )

    return {
        "active": len(active_states),
        "recovered": recovered,
        "stale_stopped": stale_stopped,
        "skipped": skipped,
        "failed": failed,
    }


__all__ = [
    "recover_inflight_scheduler_tasks",
    "recover_zone_workflow_states",
]
