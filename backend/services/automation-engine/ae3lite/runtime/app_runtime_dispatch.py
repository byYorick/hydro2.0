"""app runtime dispatch: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ae3lite.api.responses import build_start_cycle_response


@dataclass(frozen=True)
class AppRuntimeDispatchPorts:
    spawn_background_task: Callable[..., Any]
    utcnow: Callable[..., Any]
    bind_greenhouse_climate_tick_route: Callable[..., Any]
    bind_internal_task_route: Callable[..., Any]
    bind_start_cycle_route: Callable[..., Any]
    bind_start_irrigation_route: Callable[..., Any]
    bind_start_lighting_tick_route: Callable[..., Any]
    bind_start_solution_change_route: Callable[..., Any]
    bind_start_solution_topup_route: Callable[..., Any]
    logger: Callable[..., Any]


class AppRuntimeDispatch:
    def __init__(self, ports: AppRuntimeDispatchPorts) -> None:
        self._ports = ports

    def bind_dispatch_ingress(
        self,
        *,
        app: Any,
        runtime_config: Any,
        bundle: Any,
        background_tasks: Any,
        start_cycle_rate_limiter: Any,
        start_irrigation_rate_limiter: Any,
        start_lighting_tick_rate_limiter: Any,
        start_solution_topup_rate_limiter: Any,
        start_solution_change_rate_limiter: Any,
        climate_tick_rate_limiter: Any,
        _validate_scheduler_zone: Any,
        _validate_scheduler_security_baseline: Any,
        _load_zone_workflow_phase: Any,
    ) -> Any:
        self._ports.bind_start_cycle_route(
            app,
            validate_scheduler_zone_fn=_validate_scheduler_zone,
            validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
            is_start_cycle_rate_limit_enabled_fn=lambda: runtime_config.start_cycle_rate_limit_enabled,
            start_cycle_rate_limit_check_fn=lambda zone_id: start_cycle_rate_limiter.check(zone_id=zone_id),
            start_cycle_rate_limit_window_sec_fn=lambda: runtime_config.start_cycle_rate_limit_window_sec,
            start_cycle_rate_limit_max_requests_fn=lambda: runtime_config.start_cycle_rate_limit_max_requests,
            claim_start_cycle_intent_fn=lambda *, zone_id, req, now: bundle.zone_intent_repository.claim_start_cycle(
                zone_id=zone_id,
                req=req,
                now=now,
                claimed_stale_after_sec=runtime_config.start_cycle_claim_stale_sec,
                running_stale_after_sec=runtime_config.start_cycle_running_stale_sec,
            ),
            create_task_from_intent_fn=lambda *, zone_id, source, idempotency_key, intent_row, now, allow_create=True: (
                bundle.create_task_from_intent_use_case.run(
                    zone_id=zone_id,
                    source=source,
                    idempotency_key=idempotency_key,
                    intent_row=intent_row,
                    now=now,
                    allow_create=allow_create,
                )
            ),
            ensure_solution_tank_startup_reset_fn=lambda *, zone_id: bundle.solution_tank_startup_guard_use_case.run(
                zone_id=zone_id,
                now=self._ports.utcnow(),
            ),
            kick_worker_fn=bundle.worker.kick,
            build_start_cycle_response_fn=build_start_cycle_response,
            mark_intent_terminal_fn=lambda *, intent_id, now, success, error_code, error_message: (
                bundle.zone_intent_repository.mark_terminal(
                    intent_id=intent_id,
                    now=now,
                    success=success,
                    error_code=error_code,
                    error_message=error_message,
                )
            ),
            logger=self._ports.logger(),
        )
        self._ports.bind_start_irrigation_route(
            app,
            validate_scheduler_zone_fn=_validate_scheduler_zone,
            validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
            is_start_irrigation_rate_limit_enabled_fn=lambda: runtime_config.start_cycle_rate_limit_enabled,
            start_irrigation_rate_limit_check_fn=lambda zone_id: start_irrigation_rate_limiter.check(zone_id=zone_id),
            start_irrigation_rate_limit_window_sec_fn=lambda: runtime_config.start_cycle_rate_limit_window_sec,
            start_irrigation_rate_limit_max_requests_fn=lambda: runtime_config.start_cycle_rate_limit_max_requests,
            claim_start_irrigation_intent_fn=lambda *, zone_id, req, now: (
                bundle.zone_intent_repository.claim_start_irrigation(
                    zone_id=zone_id,
                    req=req,
                    now=now,
                    claimed_stale_after_sec=runtime_config.start_cycle_claim_stale_sec,
                    running_stale_after_sec=runtime_config.start_cycle_running_stale_sec,
                )
            ),
            load_zone_workflow_phase_fn=_load_zone_workflow_phase,
            create_task_from_intent_fn=lambda *, zone_id, source, idempotency_key, intent_row, now, allow_create=True: (
                bundle.create_task_from_intent_use_case.run(
                    zone_id=zone_id,
                    source=source,
                    idempotency_key=idempotency_key,
                    intent_row=intent_row,
                    now=now,
                    allow_create=allow_create,
                )
            ),
            kick_worker_fn=bundle.worker.kick,
            build_start_cycle_response_fn=build_start_cycle_response,
            mark_intent_terminal_fn=lambda *, intent_id, now, success, error_code, error_message: (
                bundle.zone_intent_repository.mark_terminal(
                    intent_id=intent_id,
                    now=now,
                    success=success,
                    error_code=error_code,
                    error_message=error_message,
                )
            ),
            logger=self._ports.logger(),
        )
        self._ports.bind_start_lighting_tick_route(
            app,
            validate_scheduler_zone_fn=_validate_scheduler_zone,
            validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
            is_start_lighting_tick_rate_limit_enabled_fn=lambda: runtime_config.start_cycle_rate_limit_enabled,
            start_lighting_tick_rate_limit_check_fn=lambda zone_id: start_lighting_tick_rate_limiter.check(
                zone_id=zone_id
            ),
            start_lighting_tick_rate_limit_window_sec_fn=lambda: runtime_config.start_cycle_rate_limit_window_sec,
            start_lighting_tick_rate_limit_max_requests_fn=lambda: runtime_config.start_cycle_rate_limit_max_requests,
            claim_start_lighting_tick_intent_fn=lambda *, zone_id, req, now: (
                bundle.zone_intent_repository.claim_start_lighting_tick(
                    zone_id=zone_id,
                    req=req,
                    now=now,
                    claimed_stale_after_sec=runtime_config.start_cycle_claim_stale_sec,
                    running_stale_after_sec=runtime_config.start_cycle_running_stale_sec,
                )
            ),
            create_task_from_intent_fn=lambda *, zone_id, source, idempotency_key, intent_row, now, allow_create=True, lighting_desired_state=None, lighting_brightness_pct=None: (
                bundle.create_task_from_intent_use_case.run(
                    zone_id=zone_id,
                    source=source,
                    idempotency_key=idempotency_key,
                    intent_row=intent_row,
                    now=now,
                    allow_create=allow_create,
                    lighting_desired_state=lighting_desired_state,
                    lighting_brightness_pct=lighting_brightness_pct,
                )
            ),
            kick_worker_fn=bundle.worker.kick,
            build_start_cycle_response_fn=build_start_cycle_response,
            mark_intent_terminal_fn=lambda *, intent_id, now, success, error_code, error_message: (
                bundle.zone_intent_repository.mark_terminal(
                    intent_id=intent_id,
                    now=now,
                    success=success,
                    error_code=error_code,
                    error_message=error_message,
                )
            ),
            logger=self._ports.logger(),
        )
        self._ports.bind_start_solution_topup_route(
            app,
            validate_scheduler_zone_fn=_validate_scheduler_zone,
            validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
            load_zone_workflow_phase_fn=_load_zone_workflow_phase,
            is_start_solution_topup_rate_limit_enabled_fn=lambda: runtime_config.start_cycle_rate_limit_enabled,
            start_solution_topup_rate_limit_check_fn=lambda zone_id: start_solution_topup_rate_limiter.check(
                zone_id=zone_id
            ),
            start_solution_topup_rate_limit_window_sec_fn=lambda: runtime_config.start_cycle_rate_limit_window_sec,
            start_solution_topup_rate_limit_max_requests_fn=lambda: runtime_config.start_cycle_rate_limit_max_requests,
            claim_start_solution_topup_intent_fn=lambda *, zone_id, req, now: (
                bundle.zone_intent_repository.claim_start_solution_topup(
                    zone_id=zone_id,
                    req=req,
                    now=now,
                    claimed_stale_after_sec=runtime_config.start_cycle_claim_stale_sec,
                    running_stale_after_sec=runtime_config.start_cycle_running_stale_sec,
                )
            ),
            create_task_from_intent_fn=lambda *, zone_id, source, idempotency_key, intent_row, now, allow_create=True, solution_topup_mode=None, solution_topup_trigger=None: (
                bundle.create_task_from_intent_use_case.run(
                    zone_id=zone_id,
                    source=source,
                    idempotency_key=idempotency_key,
                    intent_row=intent_row,
                    now=now,
                    allow_create=allow_create,
                    solution_topup_mode=solution_topup_mode,
                    solution_topup_trigger=solution_topup_trigger,
                )
            ),
            kick_worker_fn=bundle.worker.kick,
            build_start_cycle_response_fn=build_start_cycle_response,
            mark_intent_terminal_fn=lambda *, intent_id, now, success, error_code, error_message: (
                bundle.zone_intent_repository.mark_terminal(
                    intent_id=intent_id,
                    now=now,
                    success=success,
                    error_code=error_code,
                    error_message=error_message,
                )
            ),
            logger=self._ports.logger(),
        )
        self._ports.bind_start_solution_change_route(
            app,
            validate_scheduler_zone_fn=_validate_scheduler_zone,
            validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
            load_zone_workflow_phase_fn=_load_zone_workflow_phase,
            is_start_solution_change_rate_limit_enabled_fn=lambda: runtime_config.start_cycle_rate_limit_enabled,
            start_solution_change_rate_limit_check_fn=lambda zone_id: start_solution_change_rate_limiter.check(
                zone_id=zone_id
            ),
            start_solution_change_rate_limit_window_sec_fn=lambda: runtime_config.start_cycle_rate_limit_window_sec,
            start_solution_change_rate_limit_max_requests_fn=lambda: runtime_config.start_cycle_rate_limit_max_requests,
            claim_start_solution_change_intent_fn=lambda *, zone_id, req, now: (
                bundle.zone_intent_repository.claim_start_solution_change(
                    zone_id=zone_id,
                    req=req,
                    now=now,
                    claimed_stale_after_sec=runtime_config.start_cycle_claim_stale_sec,
                    running_stale_after_sec=runtime_config.start_cycle_running_stale_sec,
                )
            ),
            create_task_from_intent_fn=lambda *, zone_id, source, idempotency_key, intent_row, now, allow_create=True: (
                bundle.create_task_from_intent_use_case.run(
                    zone_id=zone_id,
                    source=source,
                    idempotency_key=idempotency_key,
                    intent_row=intent_row,
                    now=now,
                    allow_create=allow_create,
                )
            ),
            kick_worker_fn=bundle.worker.kick,
            build_start_cycle_response_fn=build_start_cycle_response,
            mark_intent_terminal_fn=lambda *, intent_id, now, success, error_code, error_message: (
                bundle.zone_intent_repository.mark_terminal(
                    intent_id=intent_id,
                    now=now,
                    success=success,
                    error_code=error_code,
                    error_message=error_message,
                )
            ),
            logger=self._ports.logger(),
        )
        self._ports.bind_internal_task_route(
            app,
            validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
            load_task_status_fn=lambda task_id: bundle.task_status_read_model.get_by_task_id(task_id=task_id),
        )
        self._ports.bind_greenhouse_climate_tick_route(
            app,
            validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
            is_climate_tick_rate_limit_enabled_fn=lambda: runtime_config.start_cycle_rate_limit_enabled,
            climate_tick_rate_limit_check_fn=lambda greenhouse_id: climate_tick_rate_limiter.check(
                zone_id=greenhouse_id
            ),
            climate_tick_rate_limit_window_sec_fn=lambda: 10,
            climate_tick_rate_limit_max_requests_fn=lambda: 60,
            history_logger_client=bundle.history_logger_client,
            spawn_background_task_fn=lambda coro, **kwargs: self._ports.spawn_background_task(
                coro,
                background_tasks=background_tasks,
                task_name=str(kwargs.get("task_name") or "ae3-background-task"),
                zone_id=kwargs.get("zone_id"),
                task_id=kwargs.get("task_id"),
                task_type=kwargs.get("task_type"),
            ),
            worker_owner=getattr(runtime_config, "worker_owner", None),
            logger=self._ports.logger(),
        )
