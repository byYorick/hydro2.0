"""Helpers for transition from online correction failure to two-tank recovery."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Sequence

BuildTwoTankRuntimePayloadFn = Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]
ResolveTwoTankRuntimeConfigFn = Callable[[Dict[str, Any]], Dict[str, Any]]
EmitTaskEventFn = Callable[..., Awaitable[None]]
StartTwoTankIrrigationRecoveryFn = Callable[..., Awaitable[Dict[str, Any]]]


async def try_start_two_tank_irrigation_recovery_from_irrigation_failure(
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    result: Dict[str, Any],
    allowed_error_codes: Sequence[str],
    reason_online_correction_failed: str,
    reason_tank_to_tank_correction_started: str,
    build_two_tank_runtime_payload_fn: BuildTwoTankRuntimePayloadFn,
    resolve_two_tank_runtime_config_fn: ResolveTwoTankRuntimeConfigFn,
    emit_task_event_fn: EmitTaskEventFn,
    start_two_tank_irrigation_recovery_fn: StartTwoTankIrrigationRecoveryFn,
) -> Optional[Dict[str, Any]]:
    if bool(result.get("success")):
        return None
    failure_error_code = str(result.get("error_code") or "").strip().lower()
    if failure_error_code not in allowed_error_codes:
        return None

    runtime_payload = build_two_tank_runtime_payload_fn(payload)
    if runtime_payload is None:
        return None
    runtime_cfg = resolve_two_tank_runtime_config_fn(runtime_payload)

    await emit_task_event_fn(
        zone_id=zone_id,
        task_type="irrigation",
        context=context,
        event_type="IRRIGATION_ONLINE_CORRECTION_FAILED",
        payload={
            "reason_code": reason_online_correction_failed,
            "error_code": failure_error_code,
            "workflow": "irrigation_recovery",
            "previous_result": result,
        },
    )

    recovery_result = await start_two_tank_irrigation_recovery_fn(
        zone_id=zone_id,
        payload={**runtime_payload, "workflow": "irrigation_recovery", "irrigation_recovery_attempt": 1},
        context=context,
        runtime_cfg=runtime_cfg,
        attempt=1,
    )
    recovery_result["task_type"] = "irrigation"
    recovery_result["source_reason_code"] = reason_online_correction_failed
    recovery_result["transition_reason_code"] = reason_tank_to_tank_correction_started
    recovery_result["online_correction_error_code"] = failure_error_code
    recovery_result["online_correction_result"] = result
    return recovery_result


__all__ = ["try_start_two_tank_irrigation_recovery_from_irrigation_failure"]
