from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.runtime_state import SchedulerRuntimeState
from infrastructure import ae_client


def _mark_bootstrap_wait(state: SchedulerRuntimeState, *, now: datetime, backoff_steps_sec: tuple[int, ...], retry: bool = True) -> None:
    state.bootstrap_ready = False
    state.bootstrap_lease_id = None
    state.bootstrap_next_heartbeat_at = None
    state.bootstrap_lease_expires_at = None
    if retry:
        backoff = backoff_steps_sec[min(state.bootstrap_retry_idx, len(backoff_steps_sec) - 1)]
        state.bootstrap_next_attempt_at = now + timedelta(seconds=backoff)
        state.bootstrap_retry_idx = min(state.bootstrap_retry_idx + 1, len(backoff_steps_sec) - 1)


async def ensure_scheduler_bootstrap_ready(m: Any) -> bool:
    state = SchedulerRuntimeState.from_module(m)
    now = m.utcnow().replace(tzinfo=None)

    if state.bootstrap_ready and state.bootstrap_lease_expires_at and now < state.bootstrap_lease_expires_at:
        state.apply_to_module(m)
        return True
    if state.bootstrap_next_attempt_at and now < state.bootstrap_next_attempt_at:
        m.SCHEDULER_DISPATCH_SKIPS.labels(reason="bootstrap_retry_backoff").inc()
        await m._emit_scheduler_diagnostic(
            reason="scheduler_bootstrap_retry_backoff",
            message="Scheduler пропускает dispatch: bootstrap в backoff-режиме",
            level="warning",
            details={
                "next_attempt_at": state.bootstrap_next_attempt_at.isoformat(),
                "scheduler_id": m.SCHEDULER_ID,
            },
            alert_code="infra_scheduler_bootstrap_retry_backoff",
            error_type="bootstrap_backoff",
        )
        state.apply_to_module(m)
        return False

    payload = {
        "scheduler_id": m.SCHEDULER_ID,
        "scheduler_version": m.SCHEDULER_VERSION,
        "protocol_version": m.SCHEDULER_PROTOCOL_VERSION,
        "started_at": now.isoformat(),
        "capabilities": {"task_types": sorted(m.SUPPORTED_TASK_TYPES)},
    }

    headers = m.inject_trace_id_header()
    try:
        response = await ae_client.post_json(
            url=f"{m.AUTOMATION_ENGINE_URL}/scheduler/bootstrap",
            payload=payload,
            headers=headers,
            timeout=5.0,
        )
    except Exception as exc:
        m.COMMAND_REST_ERRORS.labels(error_type="bootstrap_request_error").inc()
        await m._emit_scheduler_diagnostic(
            reason="scheduler_bootstrap_request_error",
            message="Scheduler не смог выполнить bootstrap в automation-engine",
            level="error",
            details={"error": str(exc)},
            alert_code="infra_scheduler_bootstrap_failed",
            error_type=type(exc).__name__,
        )
        _mark_bootstrap_wait(state, now=now, backoff_steps_sec=m._BOOTSTRAP_BACKOFF_STEPS_SEC, retry=True)
        state.apply_to_module(m)
        return False

    if response.status_code != 200:
        m.COMMAND_REST_ERRORS.labels(error_type=f"bootstrap_http_{response.status_code}").inc()
        await m._emit_scheduler_diagnostic(
            reason="scheduler_bootstrap_http_error",
            message=f"Scheduler получил HTTP {response.status_code} на bootstrap",
            level="error",
            details={"response": response.text[:300]},
            alert_code="infra_scheduler_bootstrap_failed",
            error_type=f"http_{response.status_code}",
        )
        _mark_bootstrap_wait(state, now=now, backoff_steps_sec=m._BOOTSTRAP_BACKOFF_STEPS_SEC, retry=True)
        state.apply_to_module(m)
        return False

    body = response.json() if response.content else {}
    data = body.get("data") if isinstance(body, dict) else {}
    bootstrap_status = str(data.get("bootstrap_status") or "").lower()

    state.bootstrap_lease_ttl_sec = max(10, int(data.get("lease_ttl_sec") or state.bootstrap_lease_ttl_sec))
    state.bootstrap_poll_interval_sec = max(1, int(data.get("poll_interval_sec") or state.bootstrap_poll_interval_sec))

    if bootstrap_status == "ready":
        lease_id = data.get("lease_id")
        if not isinstance(lease_id, str) or not lease_id.strip():
            await m._emit_scheduler_diagnostic(
                reason="scheduler_bootstrap_missing_lease",
                message="Scheduler получил bootstrap_status=ready без lease_id",
                level="error",
                details={"body": body},
                alert_code="infra_scheduler_bootstrap_failed",
                error_type="missing_lease_id",
            )
            _mark_bootstrap_wait(state, now=now, backoff_steps_sec=m._BOOTSTRAP_BACKOFF_STEPS_SEC, retry=True)
            state.apply_to_module(m)
            return False

        state.bootstrap_ready = True
        state.bootstrap_lease_id = lease_id
        state.bootstrap_lease_expires_at = now + timedelta(seconds=state.bootstrap_lease_ttl_sec)
        state.bootstrap_next_heartbeat_at = now + timedelta(seconds=max(1, state.bootstrap_lease_ttl_sec // 2))
        state.bootstrap_next_attempt_at = None
        state.bootstrap_retry_idx = 0
        m.send_service_log(
            service="scheduler",
            level="info",
            message="Scheduler bootstrap completed",
            context={
                "scheduler_id": m.SCHEDULER_ID,
                "lease_id": lease_id,
                "lease_ttl_sec": state.bootstrap_lease_ttl_sec,
                "poll_interval_sec": state.bootstrap_poll_interval_sec,
            },
        )
        state.apply_to_module(m)
        return True

    level = "critical" if bootstrap_status == "deny" else "warning"
    await m._emit_scheduler_diagnostic(
        reason=f"scheduler_bootstrap_{bootstrap_status or 'unknown'}",
        message=f"Scheduler bootstrap status: {bootstrap_status or 'unknown'}",
        level=level,
        details={"body": body},
        alert_code="infra_scheduler_bootstrap_not_ready",
        error_type=bootstrap_status or "unknown",
    )
    _mark_bootstrap_wait(state, now=now, backoff_steps_sec=m._BOOTSTRAP_BACKOFF_STEPS_SEC, retry=True)
    state.apply_to_module(m)
    return False


async def send_scheduler_bootstrap_heartbeat(m: Any) -> bool:
    state = SchedulerRuntimeState.from_module(m)
    now = m.utcnow().replace(tzinfo=None)

    if not state.bootstrap_ready:
        state.apply_to_module(m)
        return False
    if state.bootstrap_next_heartbeat_at and now < state.bootstrap_next_heartbeat_at:
        state.apply_to_module(m)
        return True
    if not state.bootstrap_lease_id:
        await m._emit_scheduler_diagnostic(
            reason="scheduler_bootstrap_heartbeat_missing_lease",
            message="Scheduler не может отправить heartbeat: отсутствует lease_id",
            level="error",
            details={"scheduler_id": m.SCHEDULER_ID},
            alert_code="infra_scheduler_bootstrap_heartbeat_missing_lease",
            error_type="missing_lease_id",
        )
        _mark_bootstrap_wait(state, now=now, backoff_steps_sec=m._BOOTSTRAP_BACKOFF_STEPS_SEC, retry=True)
        state.apply_to_module(m)
        return False

    headers = m.inject_trace_id_header()
    payload = {"scheduler_id": m.SCHEDULER_ID, "lease_id": state.bootstrap_lease_id}
    try:
        response = await ae_client.post_json(
            url=f"{m.AUTOMATION_ENGINE_URL}/scheduler/bootstrap/heartbeat",
            payload=payload,
            headers=headers,
            timeout=5.0,
        )
    except Exception as exc:
        m.COMMAND_REST_ERRORS.labels(error_type="bootstrap_heartbeat_request_error").inc()
        await m._emit_scheduler_diagnostic(
            reason="scheduler_bootstrap_heartbeat_error",
            message="Scheduler не смог отправить bootstrap heartbeat",
            level="error",
            details={"error": str(exc)},
            alert_code="infra_scheduler_bootstrap_heartbeat_failed",
            error_type=type(exc).__name__,
        )
        _mark_bootstrap_wait(state, now=now, backoff_steps_sec=m._BOOTSTRAP_BACKOFF_STEPS_SEC, retry=True)
        state.apply_to_module(m)
        return False

    if response.status_code != 200:
        m.COMMAND_REST_ERRORS.labels(error_type=f"bootstrap_heartbeat_http_{response.status_code}").inc()
        await m._emit_scheduler_diagnostic(
            reason="scheduler_bootstrap_heartbeat_http_error",
            message=f"Scheduler получил HTTP {response.status_code} на bootstrap heartbeat",
            level="error",
            details={"response": response.text[:300]},
            alert_code="infra_scheduler_bootstrap_heartbeat_failed",
            error_type=f"http_{response.status_code}",
        )
        _mark_bootstrap_wait(state, now=now, backoff_steps_sec=m._BOOTSTRAP_BACKOFF_STEPS_SEC, retry=True)
        state.apply_to_module(m)
        return False

    body = response.json() if response.content else {}
    data = body.get("data") if isinstance(body, dict) else {}
    status = str(data.get("bootstrap_status") or "").lower()
    if status != "ready":
        await m._emit_scheduler_diagnostic(
            reason="scheduler_bootstrap_heartbeat_not_ready",
            message=f"Scheduler heartbeat вернул bootstrap_status={status or 'unknown'}",
            level="warning",
            details={"body": body},
            alert_code="infra_scheduler_bootstrap_heartbeat_not_ready",
            error_type=status or "unknown",
        )
        _mark_bootstrap_wait(state, now=now, backoff_steps_sec=m._BOOTSTRAP_BACKOFF_STEPS_SEC, retry=True)
        state.apply_to_module(m)
        return False

    lease_ttl_sec = max(10, int(data.get("lease_ttl_sec") or state.bootstrap_lease_ttl_sec))
    state.bootstrap_lease_expires_at = now + timedelta(seconds=lease_ttl_sec)
    state.bootstrap_next_heartbeat_at = now + timedelta(seconds=max(1, lease_ttl_sec // 2))
    state.apply_to_module(m)
    return True
