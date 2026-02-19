from __future__ import annotations

from typing import Any, Dict, Optional, Union

import httpx

from infrastructure import ae_client


async def submit_task_to_automation_engine(
    m: Any,
    *,
    zone_id: int,
    task_type: str,
    payload: Optional[Dict[str, Any]] = None,
    scheduled_for: Optional[str] = None,
    correlation_id: Optional[str] = None,
    include_response_meta: bool = False,
) -> Optional[Union[str, Dict[str, Any]]]:
    created_trace = False
    if not m.get_trace_id():
        m.set_trace_id()
        created_trace = True

    effective_correlation_id = correlation_id
    try:
        effective_correlation_id = correlation_id or m._build_scheduler_correlation_id(
            zone_id=zone_id,
            task_type=task_type,
            scheduled_for=scheduled_for,
            schedule_key=(payload or {}).get("schedule_key") if isinstance(payload, dict) else None,
        )
        req_payload: Dict[str, Any] = {
            "zone_id": zone_id,
            "task_type": task_type,
            "payload": payload or {},
            "correlation_id": effective_correlation_id,
        }
        if scheduled_for:
            req_payload["scheduled_for"] = scheduled_for
        due_at, expires_at = m._compute_task_deadlines(scheduled_for)
        if due_at:
            req_payload["due_at"] = due_at
        if expires_at:
            req_payload["expires_at"] = expires_at

        headers = m._scheduler_headers()
        response = await ae_client.post_json(
            url=f"{m.AUTOMATION_ENGINE_URL}/scheduler/task",
            payload=req_payload,
            headers=headers,
            timeout=5.0,
        )

        if response.status_code not in (200, 202):
            m.COMMAND_REST_ERRORS.labels(error_type=f"http_{response.status_code}").inc()
            await m._emit_scheduler_diagnostic(
                reason="task_submit_http_error",
                message=(
                    f"Scheduler получил HTTP {response.status_code} при отправке "
                    f"абстрактной задачи {task_type} для зоны {zone_id}"
                ),
                level="error",
                zone_id=zone_id,
                details={
                    "task_type": task_type,
                    "response": response.text[:300],
                    "correlation_id": effective_correlation_id,
                },
                alert_code="infra_scheduler_task_submit_failed",
                error_type=f"http_{response.status_code}",
            )
            return None

        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        task_id = data.get("task_id") if isinstance(data, dict) else None
        task_status = str(data.get("status") or "accepted").strip().lower() if isinstance(data, dict) else "accepted"
        if not task_id:
            m.COMMAND_REST_ERRORS.labels(error_type="task_id_missing").inc()
            await m._emit_scheduler_diagnostic(
                reason="task_submit_missing_task_id",
                message=f"Scheduler не получил task_id для задачи {task_type} зоны {zone_id}",
                level="error",
                zone_id=zone_id,
                details={"task_type": task_type, "body": body, "correlation_id": effective_correlation_id},
                alert_code="infra_scheduler_task_submit_failed",
                error_type="TaskIdMissing",
            )
            return None

        await m.record_simulation_event(
            zone_id,
            service="scheduler",
            stage="task_submit",
            status=task_status,
            message="Абстрактная задача передана в automation-engine",
            payload={
                "task_id": task_id,
                "task_type": task_type,
                "task_status": task_status,
                "correlation_id": effective_correlation_id,
            },
        )
        if include_response_meta:
            return {
                "task_id": str(task_id),
                "status": task_status,
                "payload": data if isinstance(data, dict) else {},
            }
        return str(task_id)

    except httpx.TimeoutException as e:
        m.COMMAND_REST_ERRORS.labels(error_type="timeout").inc()
        await m._emit_scheduler_diagnostic(
            reason="task_submit_timeout",
            message=f"Scheduler получил таймаут при отправке задачи {task_type} для зоны {zone_id}",
            level="error",
            zone_id=zone_id,
            details={"task_type": task_type, "error": str(e), "correlation_id": effective_correlation_id},
            alert_code="infra_scheduler_task_submit_timeout",
            error_type="timeout",
        )
        return None
    except Exception as e:
        m.COMMAND_REST_ERRORS.labels(error_type=type(e).__name__).inc()
        await m.send_infra_exception_alert(
            error=e,
            code="infra_unknown_error",
            alert_type="Scheduler Task Submit Unexpected Error",
            severity="error",
            zone_id=zone_id,
            service="scheduler",
            component="task_dispatch",
            error_type=type(e).__name__,
            details={"task_type": task_type, "correlation_id": effective_correlation_id},
        )
        return None
    finally:
        if created_trace:
            m.clear_trace_id()


async def execute_scheduled_task(
    m: Any,
    *,
    zone_id: int,
    schedule: Dict[str, Any],
    trigger_time,
    schedule_key: Optional[str] = None,
) -> bool:
    task_type = str(schedule.get("type") or "").strip().lower()
    if task_type not in m.SUPPORTED_TASK_TYPES:
        await m._emit_scheduler_diagnostic(
            reason="unsupported_task_type",
            message=f"Scheduler получил неподдерживаемый task_type={task_type} для зоны {zone_id}",
            level="warning",
            zone_id=zone_id,
            details={"schedule": schedule},
            alert_code="infra_scheduler_unsupported_task_type",
        )
        return False

    task_name = f"{task_type}_zone_{zone_id}"
    if m.SCHEDULER_ZONE_PREFLIGHT_ENFORCE:
        zone_exists = await m._zone_exists_preflight(zone_id)
        if zone_exists is False:
            m.SCHEDULER_DISPATCH_SKIPS.labels(reason="zone_not_found").inc()
            await m.create_scheduler_log(
                task_name,
                "failed",
                {
                    "zone_id": zone_id,
                    "task_type": task_type,
                    "error": "zone_not_found",
                    "error_code": "zone_not_found",
                },
            )
            await m._create_zone_event_safe(
                zone_id,
                "SCHEDULE_TASK_FAILED",
                {
                    "task_type": task_type,
                    "reason": "zone_not_found",
                    "error_code": "zone_not_found",
                },
                task_type=task_type,
            )
            await m._emit_scheduler_diagnostic(
                reason="dispatch_zone_not_found",
                message=f"Scheduler пропустил dispatch: зона {zone_id} не найдена",
                level="error",
                zone_id=zone_id,
                details={"task_type": task_type, "schedule_key": schedule_key},
                alert_code="infra_scheduler_dispatch_zone_not_found",
                error_type="zone_not_found",
            )
            return False

    normalized_key = schedule_key or m._build_schedule_key(zone_id, schedule)
    if m._is_schedule_busy(normalized_key):
        m.SCHEDULER_DISPATCH_SKIPS.labels(reason="schedule_busy").inc()
        await m._emit_scheduler_diagnostic(
            reason="schedule_busy_skip",
            message=f"Scheduler пропустил dispatch: активная задача уже выполняется (zone={zone_id}, task={task_type})",
            level="warning",
            zone_id=zone_id,
            details={
                "task_type": task_type,
                "schedule_key": normalized_key,
                "active_task_id": m._ACTIVE_SCHEDULE_TASKS.get(normalized_key),
            },
            alert_code="infra_scheduler_schedule_busy_skip",
            error_type="schedule_busy",
        )
        return False

    await m.create_scheduler_log(
        task_name,
        "running",
        {
            "zone_id": zone_id,
            "task_type": task_type,
            "trigger_time": trigger_time.isoformat(),
            "schedule_key": normalized_key,
        },
    )

    schedule_payload = schedule.get("payload") if isinstance(schedule.get("payload"), dict) else {}
    payload: Dict[str, Any] = dict(schedule_payload)
    payload.setdefault("targets", schedule.get("targets") or {})
    payload.setdefault("config", schedule.get("config") or {})
    payload["trigger_time"] = trigger_time.isoformat()
    payload["schedule_key"] = normalized_key

    if task_type == "lighting" and schedule.get("start_time") and schedule.get("end_time"):
        now_t = trigger_time.time()
        start_t = schedule.get("start_time")
        end_t = schedule.get("end_time")
        desired_state = m._is_time_in_window(now_t, start_t, end_t)
        payload.update(
            {
                "desired_state": desired_state,
                "start_time": start_t.isoformat(),
                "end_time": end_t.isoformat(),
            }
        )

    submitted_at = m.utcnow().replace(tzinfo=None)
    preset_correlation_id = str(schedule.get("correlation_id") or "").strip()
    correlation_anchor = trigger_time.isoformat()
    raw_catchup_trigger = payload.get("catchup_original_trigger_time")
    if isinstance(raw_catchup_trigger, str):
        parsed_catchup_trigger = m._parse_iso_datetime_utc(raw_catchup_trigger)
        if parsed_catchup_trigger is not None:
            correlation_anchor = parsed_catchup_trigger.isoformat()
    correlation_id = preset_correlation_id or m._build_scheduler_correlation_id(
        zone_id=zone_id,
        task_type=task_type,
        scheduled_for=correlation_anchor,
        schedule_key=normalized_key,
    )
    submit_result = await m.submit_task_to_automation_engine(
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        scheduled_for=trigger_time.isoformat(),
        correlation_id=correlation_id,
        include_response_meta=True,
    )
    accepted_at = m.utcnow().replace(tzinfo=None)

    task_id: Optional[str]
    submit_status = "accepted"
    submit_payload: Dict[str, Any] = {}
    if isinstance(submit_result, dict):
        raw_task_id = submit_result.get("task_id")
        task_id = str(raw_task_id).strip() if raw_task_id else None
        submit_status = str(submit_result.get("status") or "accepted").strip().lower()
        submit_payload = submit_result.get("payload") if isinstance(submit_result.get("payload"), dict) else {}
    else:
        task_id = str(submit_result).strip() if submit_result else None

    if not task_id:
        m.SCHEDULER_TASK_STATUS.labels(task_type=task_type, status="submit_failed").inc()
        await m.create_scheduler_log(
            task_name,
            "failed",
            {
                "zone_id": zone_id,
                "task_type": task_type,
                "error": "submit_failed",
                "schedule_key": normalized_key,
            },
        )
        await m._create_zone_event_safe(
            zone_id,
            "SCHEDULE_TASK_FAILED",
            {
                "task_type": task_type,
                "reason": "submit_failed",
                "correlation_id": correlation_id,
            },
            task_type=task_type,
        )
        return False

    accept_latency_sec = max(0.0, (accepted_at - submitted_at).total_seconds())
    m.SCHEDULER_TASK_ACCEPT_LATENCY_SEC.labels(task_type=task_type).observe(accept_latency_sec)

    if m._is_terminal_status(submit_status):
        terminal_status = m._normalize_terminal_status(submit_status)
        terminal_payload = submit_payload

        fetched_status, fetched_payload = await m._fetch_task_status_once(
            task_id,
            zone_id=zone_id,
            task_type=task_type,
        )
        if fetched_status and m._is_terminal_status(fetched_status):
            terminal_status = m._normalize_terminal_status(fetched_status)
            if isinstance(fetched_payload, dict) and fetched_payload:
                terminal_payload = fetched_payload

        outcome = m._extract_task_outcome_fields(terminal_payload)
        m.SCHEDULER_TASK_COMPLETION_LATENCY_SEC.labels(task_type=task_type, status=terminal_status).observe(accept_latency_sec)
        m.TASK_ACCEPT_TO_TERMINAL_LATENCY.labels(task_type=task_type, status=terminal_status).observe(accept_latency_sec)
        m._update_deadline_violation_rate(task_type, terminal_status)
        if terminal_status == "completed":
            m.SCHEDULE_EXECUTIONS.labels(zone_id=zone_id, task_type=task_type).inc()
            m.SCHEDULER_TASK_STATUS.labels(task_type=task_type, status="completed").inc()
            await m.create_scheduler_log(
                task_name,
                "completed",
                {
                    "zone_id": zone_id,
                    "task_type": task_type,
                    "task_id": task_id,
                    "status": terminal_status,
                    "status_payload": terminal_payload,
                    "action_required": outcome["action_required"],
                    "decision": outcome["decision"],
                    "reason_code": outcome["reason_code"],
                    **m._outcome_extended_fields(outcome),
                    "result": outcome["result"],
                    "terminal_on_submit": True,
                },
            )
            await m._create_zone_event_safe(
                zone_id,
                "SCHEDULE_TASK_COMPLETED",
                {
                    "task_type": task_type,
                    "task_id": task_id,
                    "status": terminal_status,
                    "action_required": outcome["action_required"],
                    "decision": outcome["decision"],
                    "reason_code": outcome["reason_code"],
                    **m._outcome_extended_fields(outcome),
                    "terminal_on_submit": True,
                },
                task_id=task_id,
                task_type=task_type,
            )
            return True

        m.SCHEDULER_TASK_STATUS.labels(task_type=task_type, status=terminal_status).inc()
        await m.create_scheduler_log(
            task_name,
            "failed",
            {
                "zone_id": zone_id,
                "task_type": task_type,
                "task_id": task_id,
                "status": terminal_status,
                "status_payload": terminal_payload,
                "error": outcome["error"],
                "error_code": outcome["error_code"],
                "action_required": outcome["action_required"],
                "decision": outcome["decision"],
                "reason_code": outcome["reason_code"],
                **m._outcome_extended_fields(outcome),
                "terminal_on_submit": True,
            },
        )
        await m._create_zone_event_safe(
            zone_id,
            "SCHEDULE_TASK_FAILED",
            {
                "task_type": task_type,
                "task_id": task_id,
                "status": terminal_status,
                "error": outcome["error"],
                "error_code": outcome["error_code"],
                "action_required": outcome["action_required"],
                "decision": outcome["decision"],
                "reason_code": outcome["reason_code"],
                **m._outcome_extended_fields(outcome),
                "terminal_on_submit": True,
            },
            task_id=task_id,
            task_type=task_type,
        )
        return False

    await m._create_zone_event_safe(
        zone_id,
        "SCHEDULE_TASK_ACCEPTED",
        {
            "task_type": task_type,
            "task_id": task_id,
            "trigger_time": trigger_time.isoformat(),
            "schedule_key": normalized_key,
            "correlation_id": correlation_id,
        },
        task_id=task_id,
        task_type=task_type,
    )
    await m.create_scheduler_log(
        task_name,
        "accepted",
        {
            "zone_id": zone_id,
            "task_type": task_type,
            "task_id": task_id,
            "trigger_time": trigger_time.isoformat(),
            "schedule_key": normalized_key,
            "correlation_id": correlation_id,
            "accepted_at": accepted_at.isoformat(),
        },
    )
    m._register_active_task(
        task_id,
        {
            "zone_id": zone_id,
            "task_type": task_type,
            "task_name": task_name,
            "accepted_at": accepted_at,
            "schedule_key": normalized_key,
            "correlation_id": correlation_id,
        },
    )
    return True
