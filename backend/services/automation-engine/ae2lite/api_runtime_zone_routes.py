from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Request

from ae2lite.api_automation_state import (
    build_timeline_label as policy_build_timeline_label,
    derive_active_processes as policy_derive_active_processes,
    derive_automation_state as policy_derive_automation_state,
    derive_failed_state as policy_derive_failed_state,
    estimate_completion_seconds as policy_estimate_completion_seconds,
    estimate_progress_percent as policy_estimate_progress_percent,
    extract_timeline_reason as policy_extract_timeline_reason,
    resolve_state_started_at as policy_resolve_state_started_at,
)
from ae2lite.api_automation_state_constants import (
    AUTOMATION_STATE_IDLE,
    AUTOMATION_STATE_IRRIGATING,
    AUTOMATION_STATE_IRRIG_RECIRC,
    AUTOMATION_STATE_LABELS,
    AUTOMATION_STATE_NEXT,
    AUTOMATION_STATE_READY,
    AUTOMATION_STATE_TANK_FILLING,
    AUTOMATION_STATE_TANK_RECIRC,
    AUTOMATION_TIMELINE_EVENT_LABELS,
)
from ae2lite.api_contracts import SchedulerTaskRequest
from ae2lite.api_payload_parsing import (
    coerce_datetime as policy_coerce_datetime,
    extract_workflow as policy_extract_workflow,
    to_optional_int as policy_to_optional_int,
)
from ae2lite.api_zone_state import (
    load_automation_timeline as policy_load_automation_timeline,
    load_latest_irr_node_state as policy_load_latest_irr_node_state,
    load_zone_current_levels as policy_load_zone_current_levels,
    load_zone_system_config as policy_load_zone_system_config,
)
from ae2lite.api_zone_state_payload import build_zone_automation_state_payload as policy_build_zone_automation_state_payload

AUTOMATION_CONTROL_MODE_VALUES = {"auto", "semi", "manual"}
AUTOMATION_MANUAL_STEPS = (
    "clean_fill_start",
    "clean_fill_stop",
    "solution_fill_start",
    "solution_fill_stop",
    "prepare_recirculation_start",
    "prepare_recirculation_stop",
    "irrigation_recovery_start",
    "irrigation_recovery_stop",
)


def bind_zone_routes(
    app: FastAPI,
    *,
    validate_scheduler_zone_fn: Callable[[int], Awaitable[None]],
    validate_scheduler_security_baseline_fn: Callable[[Request], Awaitable[None]],
    load_latest_zone_task_fn: Callable[[int], Awaitable[Optional[Dict[str, Any]]]],
    create_scheduler_task_fn: Callable[..., Awaitable[Any]],
    execute_scheduler_task_fn: Callable[[str, SchedulerTaskRequest, Optional[str]], Awaitable[None]],
    spawn_background_task_fn: Callable[..., Any],
    workflow_state_store: Any,
    default_topology: str,
    fetch_fn: Callable[..., Awaitable[Any]],
    create_zone_event_fn: Callable[[int, str, Dict[str, Any]], Awaitable[Any]],
    get_trace_id_fn: Callable[[], Optional[str]],
    logger: Any,
):
    async def _load_zone_control_mode(zone_id: int) -> str:
        row = await workflow_state_store.get(zone_id)
        payload = row.get("payload_normalized") if isinstance(row, dict) and isinstance(row.get("payload_normalized"), dict) else {}
        mode = str(payload.get("control_mode") or "").strip().lower()
        return mode if mode in AUTOMATION_CONTROL_MODE_VALUES else "auto"

    async def _persist_zone_control_mode(zone_id: int, control_mode: str) -> Dict[str, Any]:
        existing = await workflow_state_store.get(zone_id)
        workflow_phase = str(existing.get("workflow_phase") or "idle").strip().lower() if isinstance(existing, dict) else "idle"
        payload = dict(existing.get("payload_normalized")) if isinstance(existing, dict) and isinstance(existing.get("payload_normalized"), dict) else {}
        scheduler_task_id = str(existing.get("scheduler_task_id") or "").strip() or None if isinstance(existing, dict) else None
        payload["control_mode"] = control_mode
        await workflow_state_store.set(zone_id=zone_id, workflow_phase=workflow_phase or "idle", payload=payload, scheduler_task_id=scheduler_task_id)
        return await workflow_state_store.get(zone_id) or {"zone_id": zone_id, "workflow_phase": workflow_phase, "payload_normalized": payload}

    @app.get("/zones/{zone_id}/state")
    async def zone_automation_state(zone_id: int):
        await validate_scheduler_zone_fn(zone_id)
        payload = await policy_build_zone_automation_state_payload(
            zone_id,
            load_latest_zone_task_fn=load_latest_zone_task_fn,
            derive_automation_state_fn=lambda task: policy_derive_automation_state(task, extract_workflow=policy_extract_workflow, state_idle=AUTOMATION_STATE_IDLE, state_tank_filling=AUTOMATION_STATE_TANK_FILLING, state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC, state_ready=AUTOMATION_STATE_READY, state_irrigating=AUTOMATION_STATE_IRRIGATING, state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC),
            resolve_state_started_at_fn=lambda task, state: policy_resolve_state_started_at(task, state, coerce_datetime=policy_coerce_datetime, state_tank_filling=AUTOMATION_STATE_TANK_FILLING, state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC, state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC, state_irrigating=AUTOMATION_STATE_IRRIGATING),
            estimate_progress_percent_fn=lambda task, state: policy_estimate_progress_percent(task, state, extract_workflow=policy_extract_workflow, to_optional_int=policy_to_optional_int, state_idle=AUTOMATION_STATE_IDLE, state_ready=AUTOMATION_STATE_READY, state_tank_filling=AUTOMATION_STATE_TANK_FILLING, state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC, state_irrigating=AUTOMATION_STATE_IRRIGATING, state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC),
            load_zone_system_config_fn=lambda zone_id_value, task_payload: policy_load_zone_system_config(zone_id_value, task_payload, fetch_fn=fetch_fn),
            load_zone_current_levels_fn=lambda zone_id_value: policy_load_zone_current_levels(zone_id_value, fetch_fn=fetch_fn),
            load_latest_irr_node_state_fn=lambda zone_id_value: policy_load_latest_irr_node_state(zone_id_value, fetch_fn=fetch_fn, logger=logger),
            derive_active_processes_fn=lambda task, state: policy_derive_active_processes(task, state, extract_workflow=policy_extract_workflow, state_tank_filling=AUTOMATION_STATE_TANK_FILLING, state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC, state_irrigating=AUTOMATION_STATE_IRRIGATING, state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC),
            load_automation_timeline_fn=lambda zone_id_value: policy_load_automation_timeline(zone_id_value, fetch_fn=fetch_fn, extract_timeline_reason_fn=policy_extract_timeline_reason, build_timeline_label_fn=lambda event_type, reason_code: policy_build_timeline_label(event_type, reason_code, event_labels=AUTOMATION_TIMELINE_EVENT_LABELS), logger=logger),
            estimate_completion_seconds_fn=lambda task: policy_estimate_completion_seconds(task, now=datetime.now(timezone.utc).replace(tzinfo=None), coerce_datetime=policy_coerce_datetime),
            derive_failed_state_fn=policy_derive_failed_state,
            automation_state_labels=AUTOMATION_STATE_LABELS,
            automation_state_idle=AUTOMATION_STATE_IDLE,
            automation_state_next=AUTOMATION_STATE_NEXT,
        )
        control_mode = await _load_zone_control_mode(zone_id)
        payload["control_mode"] = control_mode
        payload["control_mode_available"] = sorted(AUTOMATION_CONTROL_MODE_VALUES)
        payload["allowed_manual_steps"] = list(AUTOMATION_MANUAL_STEPS) if control_mode in {"manual", "semi"} else []
        return payload

    @app.get("/zones/{zone_id}/control-mode")
    async def zone_automation_control_mode(zone_id: int):
        await validate_scheduler_zone_fn(zone_id)
        row = await workflow_state_store.get(zone_id)
        control_mode = await _load_zone_control_mode(zone_id)
        updated_at = row.get("updated_at") if isinstance(row, dict) else None
        return {
            "status": "ok",
            "data": {
                "zone_id": zone_id,
                "control_mode": control_mode,
                "available_modes": sorted(AUTOMATION_CONTROL_MODE_VALUES),
                "allowed_manual_steps": list(AUTOMATION_MANUAL_STEPS) if control_mode in {"manual", "semi"} else [],
                "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else None,
            },
        }

    @app.post("/zones/{zone_id}/control-mode")
    async def zone_automation_set_control_mode(
        zone_id: int,
        request: Request,
        payload: Optional[Dict[str, Any]] = Body(default=None),
    ):
        await validate_scheduler_zone_fn(zone_id)
        await validate_scheduler_security_baseline_fn(request)
        payload = payload if isinstance(payload, dict) else {}
        requested_mode = str(payload.get("control_mode") or "").strip().lower()
        if requested_mode not in AUTOMATION_CONTROL_MODE_VALUES:
            raise HTTPException(status_code=422, detail={"code": "invalid_control_mode", "available_modes": sorted(AUTOMATION_CONTROL_MODE_VALUES)})
        source = str(payload.get("source") or "frontend").strip() or "frontend"
        previous_mode = await _load_zone_control_mode(zone_id)
        persisted = await _persist_zone_control_mode(zone_id, requested_mode)
        updated_at = persisted.get("updated_at") if isinstance(persisted, dict) else None
        await create_zone_event_fn(zone_id, "AUTOMATION_CONTROL_MODE_UPDATED", {"zone_id": zone_id, "control_mode": requested_mode, "previous_control_mode": previous_mode, "source": source, "reason_code": "automation_control_mode_updated"})
        return {
            "status": "ok",
            "data": {
                "zone_id": zone_id,
                "control_mode": requested_mode,
                "previous_control_mode": previous_mode,
                "available_modes": sorted(AUTOMATION_CONTROL_MODE_VALUES),
                "allowed_manual_steps": list(AUTOMATION_MANUAL_STEPS) if requested_mode in {"manual", "semi"} else [],
                "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else None,
            },
        }

    @app.post("/zones/{zone_id}/manual-step")
    async def zone_automation_manual_step(
        zone_id: int,
        request: Request,
        payload: Optional[Dict[str, Any]] = Body(default=None),
    ):
        await validate_scheduler_zone_fn(zone_id)
        await validate_scheduler_security_baseline_fn(request)
        payload = payload if isinstance(payload, dict) else {}
        manual_step = str(payload.get("manual_step") or "").strip().lower()
        if manual_step not in AUTOMATION_MANUAL_STEPS:
            raise HTTPException(status_code=422, detail={"code": "manual_step_unsupported", "available_steps": list(AUTOMATION_MANUAL_STEPS)})
        control_mode = await _load_zone_control_mode(zone_id)
        if control_mode == "auto":
            raise HTTPException(status_code=409, detail={"code": "manual_step_forbidden_in_auto_mode", "control_mode": control_mode})

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        latest_task = await load_latest_zone_task_fn(zone_id)
        latest_payload = latest_task.get("payload") if isinstance(latest_task, dict) and isinstance(latest_task.get("payload"), dict) else {}
        latest_config = latest_payload.get("config") if isinstance(latest_payload.get("config"), dict) else {}
        latest_execution = latest_config.get("execution") if isinstance(latest_config.get("execution"), dict) else {}
        execution = dict(latest_execution)
        requested_topology = str(execution.get("topology") or "").strip().lower()
        if requested_topology and requested_topology != default_topology:
            raise HTTPException(status_code=409, detail={"code": "manual_step_topology_not_supported", "topology": requested_topology, "supported_topology": default_topology})
        execution["topology"] = default_topology

        req = SchedulerTaskRequest(
            zone_id=zone_id,
            task_type="diagnostics",
            payload={"workflow": "manual_step", "manual_step": manual_step, "config": {"execution": execution}, "control_mode": control_mode},
            scheduled_for=now.isoformat(),
            due_at=(now + timedelta(seconds=45)).isoformat(),
            expires_at=(now + timedelta(minutes=10)).isoformat(),
            correlation_id=f"ae:manual_step:{zone_id}:{manual_step}:{uuid4().hex[:12]}",
        )
        task, is_duplicate = await create_scheduler_task_fn(req)
        if not is_duplicate:
            await create_zone_event_fn(zone_id, "MANUAL_STEP_ACCEPTED", {"zone_id": zone_id, "task_id": task.get("task_id"), "manual_step": manual_step, "control_mode": control_mode, "source": str(payload.get("source") or "frontend_manual_step").strip() or "frontend_manual_step", "reason_code": "manual_step_requested"})
            spawn_background_task_fn(
                execute_scheduler_task_fn(task["task_id"], req, get_trace_id_fn()),
                task_name=f"scheduler_task_{task['task_id']}",
                zone_id=zone_id,
                task_id=task["task_id"],
                task_type="diagnostics",
            )
        return {"status": "ok", "data": {"zone_id": zone_id, "task_id": task.get("task_id"), "manual_step": manual_step, "control_mode": control_mode, "is_duplicate": is_duplicate}}

    return (
        zone_automation_state,
        zone_automation_control_mode,
        zone_automation_set_control_mode,
        zone_automation_manual_step,
    )


__all__ = ["bind_zone_routes"]
