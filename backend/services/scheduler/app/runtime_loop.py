from __future__ import annotations

from typing import Any, Optional


async def run_scheduler_main_loop(m: Any) -> None:
    m.start_http_server(9402)
    m.send_service_log(
        service="scheduler",
        level="info",
        message="Scheduler service started",
        context={"port": 9402, "mode": "planner-only"},
    )
    await m.recover_active_tasks_after_restart()
    last_dispatch_at: Optional[m.datetime] = None

    try:
        while True:
            try:
                is_leader = await m.ensure_scheduler_leader()
                if not is_leader:
                    m.SCHEDULER_DISPATCH_SKIPS.labels(reason="not_leader").inc()
                    last_dispatch_at = None
                else:
                    ready = await m.ensure_scheduler_bootstrap_ready()
                    heartbeat_ok = await m.send_scheduler_bootstrap_heartbeat()
                    if ready and not heartbeat_ok:
                        m.SCHEDULER_DISPATCH_SKIPS.labels(reason="heartbeat_not_ready").inc()
                        await m._emit_scheduler_diagnostic(
                            reason="scheduler_heartbeat_not_ready",
                            message="Scheduler переведен в safe-mode: heartbeat подтвердил not-ready состояние",
                            level="warning",
                            details={"scheduler_id": m.SCHEDULER_ID},
                            alert_code="infra_scheduler_heartbeat_not_ready",
                            error_type="heartbeat_not_ready",
                        )
                        ready = False
                    now = m.utcnow().replace(tzinfo=None)
                    should_dispatch = False
                    if ready:
                        if last_dispatch_at is None:
                            should_dispatch = True
                        else:
                            elapsed = (now - last_dispatch_at).total_seconds()
                            should_dispatch = elapsed >= m.SCHEDULER_DISPATCH_INTERVAL_SEC
                    if should_dispatch:
                        await m.check_and_execute_schedules()
                        last_dispatch_at = now
            except KeyboardInterrupt:
                m.logger.info("Received interrupt signal, shutting down")
                break
            except Exception as e:
                m.logger.exception(f"Error in scheduler main loop: {e}")
                m.send_service_log(
                    service="scheduler",
                    level="error",
                    message="Error in scheduler main loop",
                    context={"error": str(e)},
                )
                await m.asyncio.sleep(max(1.0, m.SCHEDULER_MAIN_TICK_SEC))
                continue

            await m.asyncio.sleep(max(1.0, m.SCHEDULER_MAIN_TICK_SEC))
    finally:
        await m.release_scheduler_leader(reason="shutdown")
