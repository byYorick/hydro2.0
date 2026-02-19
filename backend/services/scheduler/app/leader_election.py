from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from app.runtime_state import SchedulerRuntimeState


async def transition_to_follower(*, m: Any, now, reason: str, retry: bool) -> None:
    state = SchedulerRuntimeState.from_module(m)

    conn = state.leader_conn
    was_leader = state.leader_active
    state.leader_conn = None
    state.leader_active = False
    state.leader_next_healthcheck_at = None
    state.leader_next_attempt_at = now + timedelta(seconds=m.SCHEDULER_LEADER_RETRY_BACKOFF_SEC) if retry else None
    m.SCHEDULER_LEADER_ROLE.set(0)

    if conn is not None:
        try:
            if was_leader and not conn.is_closed():
                await conn.execute("SELECT pg_advisory_unlock($1::bigint)", m._LEADER_LOCK_KEY)
        except Exception:
            pass
        try:
            if not conn.is_closed():
                await conn.close()
        except Exception:
            pass

    if was_leader:
        m.SCHEDULER_LEADER_TRANSITIONS.labels(transition="leader_to_follower").inc()
        m.send_service_log(
            service="scheduler",
            level="warning",
            message="Scheduler switched to follower mode",
            context={"reason": reason, "scope": m.SCHEDULER_LEADER_LOCK_SCOPE, "scheduler_id": m.SCHEDULER_ID},
        )

    state.apply_to_module(m)


async def release_scheduler_leader(m: Any, reason: str = "shutdown") -> None:
    if not m.SCHEDULER_LEADER_ELECTION_ENABLED:
        return
    now = m.utcnow().replace(tzinfo=None)
    await transition_to_follower(m=m, now=now, reason=reason, retry=False)


async def ensure_scheduler_leader(m: Any) -> bool:
    state = SchedulerRuntimeState.from_module(m)

    if not m.SCHEDULER_LEADER_ELECTION_ENABLED:
        state.leader_active = True
        m.SCHEDULER_LEADER_ROLE.set(1)
        state.apply_to_module(m)
        return True

    now = m.utcnow().replace(tzinfo=None)

    if state.leader_active and state.leader_conn is not None and not state.leader_conn.is_closed():
        if state.leader_next_healthcheck_at is None or now >= state.leader_next_healthcheck_at:
            try:
                await state.leader_conn.fetchval("SELECT 1")
            except Exception as exc:
                await m._emit_scheduler_diagnostic(
                    reason="scheduler_leader_connection_lost",
                    message="Scheduler потерял лидерское соединение с БД",
                    level="error",
                    details={"error": str(exc)},
                    alert_code="infra_scheduler_leader_connection_lost",
                    error_type=type(exc).__name__,
                )
                await transition_to_follower(m=m, now=now, reason="connection_lost", retry=True)
                return False
            state.leader_next_healthcheck_at = now + timedelta(seconds=m.SCHEDULER_LEADER_HEALTHCHECK_SEC)
            state.apply_to_module(m)
        return True

    if state.leader_next_attempt_at and now < state.leader_next_attempt_at:
        m.SCHEDULER_DISPATCH_SKIPS.labels(reason="leader_retry_backoff").inc()
        await m._emit_scheduler_diagnostic(
            reason="scheduler_leader_retry_backoff",
            message="Scheduler пропускает dispatch: активен backoff повторного захвата лидерского lock",
            level="warning",
            details={
                "next_attempt_at": state.leader_next_attempt_at.isoformat(),
                "scope": m.SCHEDULER_LEADER_LOCK_SCOPE,
                "scheduler_id": m.SCHEDULER_ID,
            },
            alert_code="infra_scheduler_leader_retry_backoff",
            error_type="leader_backoff",
        )
        state.apply_to_module(m)
        return False

    settings = m.get_settings()
    conn: Optional[Any] = None
    try:
        conn = await m.asyncpg.connect(
            host=settings.pg_host,
            port=settings.pg_port,
            database=settings.pg_db,
            user=settings.pg_user,
            password=settings.pg_pass,
            timeout=m.SCHEDULER_LEADER_DB_TIMEOUT_SEC,
            command_timeout=m.SCHEDULER_LEADER_DB_TIMEOUT_SEC,
        )
        acquired = bool(await conn.fetchval("SELECT pg_try_advisory_lock($1::bigint)", m._LEADER_LOCK_KEY))
    except Exception as exc:
        if conn is not None:
            try:
                if not conn.is_closed():
                    await conn.close()
            except Exception:
                pass
        state.leader_next_attempt_at = now + timedelta(seconds=m.SCHEDULER_LEADER_RETRY_BACKOFF_SEC)
        await m._emit_scheduler_diagnostic(
            reason="scheduler_leader_acquire_error",
            message="Scheduler не смог попытаться захватить лидерский lock",
            level="error",
            details={"error": str(exc)},
            alert_code="infra_scheduler_leader_acquire_failed",
            error_type=type(exc).__name__,
        )
        state.apply_to_module(m)
        return False

    if not acquired:
        try:
            if not conn.is_closed():
                await conn.close()
        except Exception:
            pass
        state.leader_active = False
        state.leader_next_attempt_at = now + timedelta(seconds=m.SCHEDULER_LEADER_RETRY_BACKOFF_SEC)
        state.leader_next_healthcheck_at = None
        m.SCHEDULER_LEADER_ROLE.set(0)
        await m._emit_scheduler_diagnostic(
            reason="scheduler_leader_lock_busy",
            message="Scheduler работает в follower mode: лидерский lock удерживается другим инстансом",
            level="warning",
            details={"scope": m.SCHEDULER_LEADER_LOCK_SCOPE, "scheduler_id": m.SCHEDULER_ID},
            error_type="lock_busy",
        )
        state.apply_to_module(m)
        return False

    state.leader_conn = conn
    state.leader_active = True
    state.leader_next_attempt_at = None
    state.leader_next_healthcheck_at = now + timedelta(seconds=m.SCHEDULER_LEADER_HEALTHCHECK_SEC)
    m.SCHEDULER_LEADER_ROLE.set(1)
    m.SCHEDULER_LEADER_TRANSITIONS.labels(transition="follower_to_leader").inc()
    m.send_service_log(
        service="scheduler",
        level="info",
        message="Scheduler acquired leader lock",
        context={"scope": m.SCHEDULER_LEADER_LOCK_SCOPE, "scheduler_id": m.SCHEDULER_ID},
    )
    state.apply_to_module(m)
    return True
