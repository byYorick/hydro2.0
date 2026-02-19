from __future__ import annotations

from typing import Any


async def check_and_execute_schedules(m: Any, _unused: Any = None) -> None:
    """Check schedules and submit abstract tasks to automation-engine."""
    await m.reconcile_active_tasks()
    now_for_internal = m.utcnow().replace(tzinfo=None)
    await m.process_internal_enqueued_tasks(now_for_internal)
    schedules = await m.get_active_schedules()
    attempted_dispatches = 0
    successful_dispatches = 0
    triggerless_count = 0
    replay_budget = m.SCHEDULER_CATCHUP_RATE_LIMIT_PER_CYCLE
    zone_ids = sorted({schedule["zone_id"] for schedule in schedules})
    simulation_clocks = await m.get_simulation_clocks(zone_ids)

    real_now = m.utcnow().replace(tzinfo=None)
    executed: set = set()
    observed_window_keys: set = set()
    zone_now = {}
    zone_last = {}
    zones_with_pending_time_dispatch: set[int] = set()
    zones_with_successful_time_dispatch: set[int] = set()

    for schedule in schedules:
        zone_id = schedule["zone_id"]
        task_type = schedule["type"]

        key = m._build_schedule_key(zone_id, schedule)
        if key in executed:
            continue

        sim_clock = simulation_clocks.get(zone_id)
        if zone_id not in zone_now:
            now_dt = sim_clock.now() if sim_clock else real_now
            zone_now[zone_id] = now_dt
            zone_last[zone_id] = await m._resolve_zone_last_check(zone_id, now_dt, sim_clock)

        now_dt = zone_now[zone_id]
        last_dt = zone_last[zone_id]

        interval_sec = m._safe_positive_int(schedule.get("interval_sec"))
        task_name = f"{task_type}_zone_{zone_id}"

        if interval_sec > 0:
            should_run = await m._should_run_interval_task(
                task_name=task_name,
                interval_sec=interval_sec,
                sim_clock=sim_clock,
            )
            if should_run:
                attempted_dispatches += 1
                dispatched = await m.execute_scheduled_task(
                    zone_id=zone_id,
                    schedule=schedule,
                    trigger_time=now_dt,
                    schedule_key=key,
                )
                if dispatched:
                    successful_dispatches += 1
                    executed.add(key)
            continue

        schedule_time = schedule.get("time")
        if schedule_time:
            crossings = m._schedule_crossings(last_dt, now_dt, schedule_time)
            planned_triggers = m._apply_catchup_policy(crossings, now_dt)
            had_dispatch_success = False

            if crossings and len(planned_triggers) < len(crossings):
                await m._emit_scheduler_diagnostic(
                    reason="catchup_windows_limited",
                    message=(
                        f"Scheduler ограничил catch-up окна для зоны {zone_id} "
                        f"({len(crossings)} -> {len(planned_triggers)})"
                    ),
                    level="warning",
                    zone_id=zone_id,
                    details={
                        "task_type": task_type,
                        "policy": m.SCHEDULER_CATCHUP_POLICY,
                        "crossings_total": len(crossings),
                        "planned_triggers": len(planned_triggers),
                        "max_windows": m.SCHEDULER_CATCHUP_MAX_WINDOWS,
                    },
                    alert_code="infra_scheduler_catchup_windows_limited",
                    error_type="catchup_limited",
                )

            for trigger_time in planned_triggers:
                is_replay = trigger_time < now_dt
                if is_replay:
                    if replay_budget <= 0:
                        m.SCHEDULER_DISPATCH_SKIPS.labels(reason="catchup_rate_limited").inc()
                        await m._emit_scheduler_diagnostic(
                            reason="catchup_rate_limit_exhausted",
                            message="Scheduler исчерпал лимит replay dispatch в текущем цикле",
                            level="warning",
                            zone_id=zone_id,
                            details={
                                "task_type": task_type,
                                "policy": m.SCHEDULER_CATCHUP_POLICY,
                                "rate_limit": m.SCHEDULER_CATCHUP_RATE_LIMIT_PER_CYCLE,
                            },
                            alert_code="infra_scheduler_catchup_rate_limited",
                            error_type="catchup_rate_limited",
                        )
                        break
                    replay_budget -= 1

                dispatch_trigger = trigger_time
                dispatch_schedule = schedule
                if is_replay:
                    dispatch_payload = dict(schedule.get("payload") or {}) if isinstance(schedule.get("payload"), dict) else {}
                    dispatch_payload["catchup_original_trigger_time"] = trigger_time.isoformat()
                    dispatch_payload["catchup_policy"] = m.SCHEDULER_CATCHUP_POLICY
                    dispatch_schedule = dict(schedule)
                    dispatch_schedule["payload"] = dispatch_payload

                    if (now_dt - trigger_time).total_seconds() > m.SCHEDULER_DUE_GRACE_SEC:
                        dispatch_trigger = now_dt
                    if m.SCHEDULER_CATCHUP_JITTER_SEC > 0:
                        dispatch_trigger = dispatch_trigger + m.timedelta(
                            seconds=m.random.uniform(0, m.SCHEDULER_CATCHUP_JITTER_SEC)
                        )

                attempted_dispatches += 1
                dispatched = await m.execute_scheduled_task(
                    zone_id=zone_id,
                    schedule=dispatch_schedule,
                    trigger_time=dispatch_trigger,
                    schedule_key=key,
                )
                if dispatched:
                    successful_dispatches += 1
                    had_dispatch_success = True
                    zones_with_successful_time_dispatch.add(zone_id)
                    break
            if planned_triggers and not had_dispatch_success:
                zones_with_pending_time_dispatch.add(zone_id)
                await m._emit_scheduler_diagnostic(
                    reason="schedule_time_dispatch_retry_pending",
                    message=(
                        f"Scheduler оставил курсор зоны {zone_id} без продвижения: "
                        f"time-trigger задача {task_type} не была успешно отправлена"
                    ),
                    level="warning",
                    zone_id=zone_id,
                    details={
                        "task_type": task_type,
                        "planned_triggers": len(planned_triggers),
                        "last_check": last_dt.isoformat(),
                        "now": now_dt.isoformat(),
                    },
                    alert_code="infra_scheduler_time_dispatch_retry_pending",
                    error_type="dispatch_retry_pending",
                )
            if planned_triggers:
                executed.add(key)
            continue

        if schedule.get("start_time") and schedule.get("end_time"):
            observed_window_keys.add(key)
            desired_state = m._is_time_in_window(
                now_dt.time(),
                schedule["start_time"],
                schedule["end_time"],
            )
            last_state = m._WINDOW_LAST_STATE.get(key)
            if last_state is None or last_state != desired_state:
                attempted_dispatches += 1
                dispatched = await m.execute_scheduled_task(
                    zone_id=zone_id,
                    schedule=schedule,
                    trigger_time=now_dt,
                    schedule_key=key,
                )
                if dispatched:
                    successful_dispatches += 1
                    m._WINDOW_LAST_STATE[key] = desired_state
            executed.add(key)
            continue

        triggerless_count += 1
        await m._emit_scheduler_diagnostic(
            reason="schedule_without_trigger",
            message=f"Scheduler пропустил задачу {task_type} зоны {zone_id}: отсутствует trigger",
            level="warning",
            zone_id=zone_id,
            details={"schedule": schedule},
            alert_code="infra_scheduler_schedule_without_trigger",
        )

    zones_pending_time_retry = 0
    for zone_id, now_dt in zone_now.items():
        cursor_retry_pending = (
            zone_id in zones_with_pending_time_dispatch and zone_id not in zones_with_successful_time_dispatch
        )
        if cursor_retry_pending:
            zones_pending_time_retry += 1
        cursor_at = zone_last.get(zone_id, now_dt) if cursor_retry_pending else now_dt
        m._LAST_SCHEDULE_CHECKS[zone_id] = cursor_at
        await m._persist_zone_cursor(zone_id, cursor_at)

    for stale_key in list(m._WINDOW_LAST_STATE.keys()):
        if stale_key not in observed_window_keys:
            m._WINDOW_LAST_STATE.pop(stale_key, None)

    m.send_service_log(
        service="scheduler",
        level="info",
        message="Scheduler dispatch cycle completed",
        context={
            "schedules_total": len(schedules),
            "attempted_dispatches": attempted_dispatches,
            "successful_dispatches": successful_dispatches,
            "triggerless_schedules": triggerless_count,
            "active_tasks": len(m._ACTIVE_TASKS),
            "zones_pending_time_retry": zones_pending_time_retry,
        },
    )
    if attempted_dispatches > 0 and successful_dispatches == 0:
        await m._emit_scheduler_diagnostic(
            reason="dispatch_cycle_no_success",
            message="Scheduler не смог успешно dispatch-ить ни одной задачи в текущем цикле",
            level="warning",
            details={
                "schedules_total": len(schedules),
                "attempted_dispatches": attempted_dispatches,
                "active_tasks": len(m._ACTIVE_TASKS),
            },
            alert_code="infra_scheduler_dispatch_cycle_no_success",
            error_type="dispatch_no_success",
        )
