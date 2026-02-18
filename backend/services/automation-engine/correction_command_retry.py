import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


async def wait_command_done(*, tracker, cmd_id: str, timeout_sec: float) -> Optional[bool]:
    try:
        return await tracker.wait_for_command_done(
            cmd_id=cmd_id,
            timeout_sec=timeout_sec,
            poll_interval_sec=min(1.0, max(0.25, timeout_sec / 10.0)),
        )
    except Exception as exc:
        logger.warning(
            "Failed waiting correction command completion for cmd_id=%s: %s",
            cmd_id,
            exc,
            extra={
                "component": "correction_command_retry",
                "decision": "retry_or_fail",
                "reason_code": "wait_command_done_exception",
                "cmd_id": cmd_id,
            },
        )
        return False


async def get_command_outcome(*, tracker, cmd_id: str) -> Dict[str, Optional[str]]:
    empty = {"status": None, "error_code": None, "error_message": None}
    if not tracker or not cmd_id:
        return empty

    try:
        fetch_outcome = getattr(tracker, "get_command_outcome", None)
        if callable(fetch_outcome):
            outcome = await fetch_outcome(cmd_id)
            if isinstance(outcome, dict):
                return {
                    "status": str(outcome.get("status") or "").strip().upper() or None,
                    "error_code": outcome.get("error_code"),
                    "error_message": outcome.get("error_message"),
                }
    except Exception as exc:
        logger.warning(
            "Failed reading detailed command outcome for cmd_id=%s: %s",
            cmd_id,
            exc,
            extra={
                "component": "correction_command_retry",
                "decision": "retry_or_fail",
                "reason_code": "get_command_outcome_exception",
                "cmd_id": cmd_id,
            },
        )

    try:
        status = await tracker._get_command_status_from_db(cmd_id)  # noqa: SLF001
        return {
            "status": str(status or "").strip().upper() or None,
            "error_code": None,
            "error_message": None,
        }
    except Exception as exc:
        logger.warning(
            "Failed reading fallback command status for cmd_id=%s: %s",
            cmd_id,
            exc,
            extra={
                "component": "correction_command_retry",
                "decision": "retry_or_fail",
                "reason_code": "get_command_status_exception",
                "cmd_id": cmd_id,
            },
        )
        return empty


async def publish_controller_command_with_retry(
    *,
    zone_id: int,
    command_bus,
    controller_command: Dict[str, Any],
    context,
    correction_type: str,
    get_settings_fn: Callable[[], Any],
    create_zone_event_fn: Callable[[int, str, Dict[str, Any]], Awaitable[Any]],
    send_infra_alert_fn: Callable[..., Awaitable[Any]],
) -> bool:
    settings = get_settings_fn()
    max_attempts = max(1, int(settings.CORRECTION_COMMAND_MAX_ATTEMPTS))
    timeout_sec = max(0.1, float(settings.CORRECTION_COMMAND_TIMEOUT_SEC))
    retry_delay_sec = max(0.0, float(settings.CORRECTION_COMMAND_RETRY_DELAY_SEC))
    tracker = getattr(command_bus, "tracker", None)

    last_failure_reason = "unknown"
    last_cmd_id: Optional[str] = None
    last_terminal_status: Optional[str] = None
    last_terminal_error_code: Optional[str] = None
    last_terminal_error_message: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        sent = await command_bus.publish_controller_command(zone_id, controller_command, context)
        cmd_id = controller_command.get("cmd_id")
        last_cmd_id = str(cmd_id) if cmd_id else None

        if not sent:
            last_failure_reason = "publish_failed"
        elif tracker and cmd_id:
            wait_result = await wait_command_done(
                tracker=tracker,
                cmd_id=str(cmd_id),
                timeout_sec=timeout_sec,
            )
            if wait_result is True:
                return True

            outcome = await get_command_outcome(tracker=tracker, cmd_id=str(cmd_id))
            last_terminal_status = outcome.get("status")
            last_terminal_error_code = outcome.get("error_code")
            last_terminal_error_message = outcome.get("error_message")

            if wait_result is None:
                last_failure_reason = f"ack_done_timeout_{timeout_sec}s"
                try:
                    await tracker.confirm_command_status(
                        str(cmd_id),
                        "TIMEOUT",
                        error=last_failure_reason,
                    )
                except Exception as confirm_exc:
                    logger.warning(
                        "Zone %s: failed to mark correction timeout cmd_id=%s: %s",
                        zone_id,
                        cmd_id,
                        confirm_exc,
                        extra={
                            "component": "correction_command_retry",
                            "zone_id": zone_id,
                            "decision": "retry_or_fail",
                            "reason_code": "timeout_status_confirm_failed",
                            "cmd_id": cmd_id,
                        },
                    )
            else:
                if last_terminal_status:
                    last_failure_reason = f"terminal_{str(last_terminal_status).lower()}"
                else:
                    last_failure_reason = "command_failed_status"
        elif tracker and not cmd_id:
            last_failure_reason = "cmd_id_missing_after_publish"
            logger.warning(
                "Zone %s: correction command confirmation unavailable: tracker active but cmd_id missing",
                zone_id,
                extra={
                    "component": "correction_command_retry",
                    "zone_id": zone_id,
                    "decision": "fail_closed",
                    "reason_code": "cmd_id_missing_after_publish",
                },
            )
        else:
            last_failure_reason = "command_tracker_unavailable"
            logger.warning(
                "Zone %s: correction command confirmation unavailable: command tracker is missing",
                zone_id,
                extra={
                    "component": "correction_command_retry",
                    "zone_id": zone_id,
                    "decision": "fail_closed",
                    "reason_code": "command_tracker_unavailable",
                },
            )

        await create_zone_event_fn(
            zone_id,
            "CORRECTION_COMMAND_ATTEMPT_FAILED",
            {
                "correction_type": correction_type,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "cmd_id": last_cmd_id,
                "cmd": controller_command.get("cmd"),
                "node_uid": controller_command.get("node_uid"),
                "channel": controller_command.get("channel"),
                "component": controller_command.get("component"),
                "reason": last_failure_reason,
                "terminal_status": last_terminal_status,
                "terminal_error_code": last_terminal_error_code,
                "terminal_error_message": last_terminal_error_message,
            },
        )

        if attempt < max_attempts and retry_delay_sec > 0:
            await asyncio.sleep(retry_delay_sec)

    await send_infra_alert_fn(
        code="infra_correction_command_unconfirmed",
        alert_type="Correction Command Unconfirmed",
        message=f"Команда коррекции не подтверждена после {max_attempts} попыток",
        severity="critical",
        zone_id=zone_id,
        service="automation-engine",
        component="correction_controller",
        node_uid=controller_command.get("node_uid"),
        channel=controller_command.get("channel"),
        cmd=controller_command.get("cmd"),
        error_type="CommandUnconfirmed",
        details={
            "correction_type": correction_type,
            "cmd_id": last_cmd_id,
            "max_attempts": max_attempts,
            "timeout_sec": timeout_sec,
            "reason": last_failure_reason,
            "terminal_status": last_terminal_status,
            "terminal_error_code": last_terminal_error_code,
            "terminal_error_message": last_terminal_error_message,
            "component": controller_command.get("component"),
        },
    )

    return False


async def trigger_ec_partial_batch_compensation(
    *,
    zone_id: int,
    command: Dict[str, Any],
    successful_components: List[str],
    failed_component: str,
    enqueue_internal_scheduler_task_fn: Callable[..., Awaitable[Dict[str, Any]]],
    send_infra_alert_fn: Callable[..., Awaitable[Any]],
) -> Dict[str, Any]:
    payload = {
        "workflow": "irrigation_recovery",
        "payload_contract_version": "v2",
        "source_reason": "ec_batch_partial_failure",
        "ec_batch_partial_failure": {
            "successful_components": successful_components,
            "failed_component": failed_component,
        },
    }

    try:
        enqueue_result = await enqueue_internal_scheduler_task_fn(
            zone_id=zone_id,
            task_type="diagnostics",
            payload=payload,
            scheduled_for=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            source="automation-engine:ec-batch-partial-failure",
        )
        return {
            "status": "degraded_recovery_enqueued",
            "enqueue_id": enqueue_result.get("enqueue_id"),
            "task_type": enqueue_result.get("task_type"),
            "correlation_id": enqueue_result.get("correlation_id"),
        }
    except Exception as exc:
        logger.warning(
            "Zone %s: failed to enqueue EC partial batch compensation task: %s",
            zone_id,
            exc,
            extra={
                "component": "correction_command_retry",
                "zone_id": zone_id,
                "decision": "degraded_recovery_enqueue_failed",
                "reason_code": "ec_partial_batch_compensation_enqueue_failed",
            },
            exc_info=True,
        )
        await send_infra_alert_fn(
            code="infra_ec_batch_partial_failure_compensation_enqueue_failed",
            alert_type="EC Batch Partial Failure Compensation Enqueue Failed",
            message="Не удалось поставить recovery-задачу после partial EC batch failure",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="correction_controller",
            error_type=type(exc).__name__,
            details={
                "failed_component": failed_component,
                "successful_components": successful_components,
                "error": str(exc),
                "command_channel": command.get("channel"),
                "command_node_uid": command.get("node_uid"),
            },
        )
        return {
            "status": "degraded_recovery_enqueue_failed",
            "error": str(exc),
        }
