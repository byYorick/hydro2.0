"""Correction apply flow extracted from CorrectionController."""

import asyncio
import logging
import hashlib
from typing import Any, Dict, List, Optional
from uuid import uuid4

from common.db import create_ai_log, create_zone_event
from common.infra_alerts import send_infra_alert
from config.settings import get_settings
from correction_command_retry import (
    publish_controller_command_with_retry,
    trigger_ec_partial_batch_compensation,
    wait_command_done,
)
from correction_cooldown import record_correction
from correction_state_machine import CorrectionStateMachine
from decision_context import DecisionContext
from scheduler_internal_enqueue import enqueue_internal_scheduler_task

logger = logging.getLogger(__name__)


async def apply_correction_with_events(
    controller: Any,
    command: Dict[str, Any],
    command_gateway: Any,
    pid: Optional[Any] = None,
) -> None:
    """
    Применить корректировку: отправить команду, создать события и логи.
    """
    zone_id = command["zone_id"]
    correction_type_str = command["correction_type_str"]
    current_val = command["current_value"]
    target_val = command["target_value"]
    diff = command["event_details"]["diff"]
    correction_type = command["event_details"]["correction_type"]
    reason = command.get("reason", "")
    correlation_id = str(
        command.get("correlation_id")
        or f"corr:correction:{zone_id}:{correction_type_str}:{uuid4().hex[:12]}"
    )
    idempotency_material = "|".join(
        [
            str(zone_id),
            str(correction_type_str),
            str(correction_type),
            f"{float(current_val):.4f}",
            f"{float(target_val):.4f}",
            f"{float(diff):.4f}",
            str(reason or ""),
        ]
    )
    correction_idempotency_key = f"corr-cycle:{zone_id}:{hashlib.sha256(idempotency_material.encode('utf-8')).hexdigest()[:20]}"
    command["correlation_id"] = correlation_id
    command["idempotency_key"] = correction_idempotency_key
    state_machine = CorrectionStateMachine(
        zone_id=zone_id,
        metric=correction_type_str,
        state=str((command.get("state_machine") or {}).get("state") or "plan"),
        correlation_id=correlation_id,
    )
    await state_machine.transition("act", "plan_dispatch_started")
    published_cmd_ids: List[str] = []

    context = DecisionContext(
        current_value=current_val,
        target_value=target_val,
        diff=diff,
        reason=reason,
        telemetry=command.get("telemetry", {}),
        pid_zone=pid.get_zone().value if pid else None,
        pid_output=command["event_details"].get("ml", 0) if pid else None,
        pid_integral=pid.integral if pid else None,
        pid_prev_error=pid.prev_error if pid else None,
    )

    batch_commands = command.get("batch_commands")
    if isinstance(batch_commands, list) and batch_commands:
        dose_delay_sec, ec_stop_tolerance = controller._resolve_batch_dose_control(command)
        batch_aborted = False
        successful_components: List[str] = []
        for idx, batch_cmd in enumerate(batch_commands):
            published = await controller._publish_controller_command_with_retry(
                zone_id=zone_id,
                command_gateway=command_gateway,
                controller_command=batch_cmd,
                context=context,
                correction_type=correction_type_str,
            )
            if not published:
                batch_aborted = True
                failed_component = str(batch_cmd.get("component") or "")
                remaining_components = len(batch_commands) - idx - 1
                compensation_result = await controller._trigger_ec_partial_batch_compensation(
                    zone_id=zone_id,
                    command=command,
                    successful_components=successful_components,
                    failed_component=failed_component,
                )
                await create_zone_event(
                    zone_id,
                    "EC_COMPONENT_BATCH_ABORTED",
                    {
                        "failed_component": failed_component,
                        "failed_channel": batch_cmd.get("channel"),
                        "failed_node_uid": batch_cmd.get("node_uid"),
                        "remaining_components": remaining_components,
                        "reason": "command_unconfirmed",
                    },
                )
                await create_zone_event(
                    zone_id,
                    "EC_BATCH_PARTIAL_FAILURE",
                    {
                        "successful_components": successful_components,
                        "failed_component": failed_component,
                        "failed_channel": batch_cmd.get("channel"),
                        "failed_node_uid": batch_cmd.get("node_uid"),
                        "remaining_components": remaining_components,
                        "status": "degraded",
                        "target_ec": target_val,
                        "current_ec": current_val,
                        "compensation": compensation_result,
                    },
                )
                break

            cmd_id = str(batch_cmd.get("cmd_id") or "").strip()
            if cmd_id:
                published_cmd_ids.append(cmd_id)
            successful_components.append(str(batch_cmd.get("component") or ""))
            is_last = idx >= len(batch_commands) - 1
            if is_last or controller.correction_type.value != "ec":
                continue

            if dose_delay_sec > 0:
                await asyncio.sleep(dose_delay_sec)

            ec_after = await controller._get_latest_ec_value(zone_id)
            if ec_after is None:
                continue

            await create_zone_event(
                zone_id,
                "EC_COMPONENT_RECHECK",
                {
                    "component": batch_cmd.get("component"),
                    "ec_current": ec_after,
                    "ec_target": target_val,
                    "ec_stop_tolerance": ec_stop_tolerance,
                },
            )

            if ec_after >= (target_val - ec_stop_tolerance):
                await create_zone_event(
                    zone_id,
                    "EC_COMPONENT_BATCH_STOPPED",
                    {
                        "stopped_after_component": batch_cmd.get("component"),
                        "ec_current": ec_after,
                        "ec_target": target_val,
                        "ec_stop_tolerance": ec_stop_tolerance,
                        "remaining_components": len(batch_commands) - idx - 1,
                    },
                )
                break

        if batch_aborted:
            await state_machine.transition("verify", "act_batch_partial_failure")
            # Если хотя бы один компонент был успешно дозирован, регистрируем DOSING событие
            # чтобы cooldown сработал в следующем цикле. Без этого automation-engine немедленно
            # повторит полный EC batch, что приведёт к превышению целевого EC.
            if successful_components:
                await create_zone_event(
                    zone_id,
                    "DOSING",
                    {
                        "type": f"{correction_type_str}_correction",
                        "correction_type": correction_type,
                        f"current_{correction_type_str}": current_val,
                        f"target_{correction_type_str}": target_val,
                        "diff": diff,
                        "correlation_id": correlation_id,
                        "partial": True,
                        "successful_components": successful_components,
                    },
                )
            await state_machine.transition("cooldown", "verify_batch_partial_failure_exit")
            return
    else:
        published = await controller._publish_controller_command_with_retry(
            zone_id=zone_id,
            command_gateway=command_gateway,
            controller_command=command,
            context=context,
            correction_type=correction_type_str,
        )
        if not published:
            await state_machine.transition("verify", "act_command_unconfirmed")
            await create_zone_event(
                zone_id,
                "CORRECTION_ABORTED_COMMAND_FAILURE",
                {
                    "correction_type": correction_type_str,
                    "cmd": command.get("cmd"),
                    "node_uid": command.get("node_uid"),
                    "channel": command.get("channel"),
                    "reason": "command_unconfirmed",
                },
            )
            await state_machine.transition("cooldown", "verify_command_failure_exit")
            return
        cmd_id = str(command.get("cmd_id") or "").strip()
        if cmd_id:
            published_cmd_ids.append(cmd_id)

    await record_correction(
        zone_id,
        correction_type_str,
        {
            "correction_type": correction_type,
            f"current_{correction_type_str}": current_val,
            f"target_{correction_type_str}": target_val,
            "diff": diff,
            "reason": reason,
        },
    )
    await state_machine.transition("verify", "act_commands_confirmed")

    correction_event_details = dict(command.get("event_details") or {})
    correction_event_details["correlation_id"] = correlation_id
    correction_event_details["idempotency_key"] = correction_idempotency_key
    correction_event_details["cmd_ids"] = published_cmd_ids
    if published_cmd_ids:
        correction_event_details["cmd_id"] = published_cmd_ids[-1]
    logger.info(
        "Zone %s: correction action event payload enriched with correlation/cmd ids",
        zone_id,
        extra={
            "zone_id": zone_id,
            "correction_type": correction_type_str,
            "correlation_id": correlation_id,
            "idempotency_key": correction_idempotency_key,
            "cmd_ids": published_cmd_ids,
            "event_type": command.get("event_type"),
        },
    )

    await create_zone_event(zone_id, command["event_type"], correction_event_details)
    await create_zone_event(
        zone_id,
        "DOSING",
        {
            "type": f"{correction_type_str}_correction",
            "correction_type": correction_type,
            f"current_{correction_type_str}": current_val,
            f"target_{correction_type_str}": target_val,
            "diff": diff,
            "correlation_id": correlation_id,
            "idempotency_key": correction_idempotency_key,
            "cmd_ids": published_cmd_ids,
            "cmd_id": published_cmd_ids[-1] if published_cmd_ids else None,
        },
    )

    from config.settings import get_settings

    settings = get_settings()
    if controller.correction_type.value == "ph":
        if diff > settings.PH_TOO_HIGH_THRESHOLD:
            await create_zone_event(
                zone_id,
                "PH_TOO_HIGH_DETECTED",
                {
                    "current_ph": current_val,
                    "target_ph": target_val,
                    "diff": diff,
                },
            )
        elif diff < settings.PH_TOO_LOW_THRESHOLD:
            await create_zone_event(
                zone_id,
                "PH_TOO_LOW_DETECTED",
                {
                    "current_ph": current_val,
                    "target_ph": target_val,
                    "diff": diff,
                },
            )

    await create_ai_log(
        zone_id,
        "recommend",
        {
            "action": f"{correction_type_str}_correction",
            "metric": correction_type_str,
            "current": current_val,
            "target": target_val,
            "correction": correction_type,
        },
    )

    if correction_type in {"add_acid", "add_base", "add_nutrients", "dilute"}:
        from config.settings import get_settings as get_controller_settings

        controller._register_pending_effect_window(
            zone_id=zone_id,
            baseline_value=current_val,
            target_value=target_val,
            correction_type=correction_type,
            settings=get_controller_settings(),
            correlation_id=correlation_id,
        )
    await state_machine.transition("cooldown", "verify_completed")


async def publish_controller_command_with_retry_method(
    controller: Any,
    *,
    zone_id: int,
    command_gateway: Any,
    controller_command: Dict[str, Any],
    context: DecisionContext,
    correction_type: str,
) -> bool:
    return await publish_controller_command_with_retry(
        zone_id=zone_id,
        command_gateway=command_gateway,
        controller_command=controller_command,
        context=context,
        correction_type=correction_type,
        get_settings_fn=get_settings,
        create_zone_event_fn=create_zone_event,
        send_infra_alert_fn=send_infra_alert,
    )


async def trigger_ec_partial_batch_compensation_method(
    controller: Any,
    *,
    zone_id: int,
    command: Dict[str, Any],
    successful_components: List[str],
    failed_component: str,
) -> Dict[str, Any]:
    _ = controller
    return await trigger_ec_partial_batch_compensation(
        zone_id=zone_id,
        command=command,
        successful_components=successful_components,
        failed_component=failed_component,
        enqueue_internal_scheduler_task_fn=enqueue_internal_scheduler_task,
        send_infra_alert_fn=send_infra_alert,
    )


async def wait_command_done_method(controller: Any, *, tracker: Any, cmd_id: str, timeout_sec: float) -> Optional[bool]:
    _ = controller
    return await wait_command_done(tracker=tracker, cmd_id=cmd_id, timeout_sec=timeout_sec)
