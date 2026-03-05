"""Extracted two-tank workflow coordinator.

This module is imported lazily from SchedulerTaskExecutor to keep startup import-order stable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from domain.workflows.two_tank_irr_state_helpers import (
    request_irr_state_snapshot_best_effort,
    validate_irr_state_expected_vs_actual,
)
from domain.workflows.two_tank_deps import TwoTankDeps
from domain.workflows.two_tank_result import two_tank_error, two_tank_success
from domain.models.decision_models import DecisionOutcome
from executor.executor_constants import (
    ERR_CYCLE_REQUIRED_NODES_UNAVAILABLE,
    ERR_TWO_TANK_COMMAND_FAILED,
    REASON_CYCLE_BLOCKED_NODES_UNAVAILABLE,
)
from executor.workflow_phase_policy import WORKFLOW_STAGE_TO_PHASE


TWO_TANK_STARTUP_WORKFLOWS = {
    "startup",
    "clean_fill_check",
    "solution_fill_check",
    "prepare_recirculation",
    "prepare_recirculation_check",
    "manual_step",
}

TWO_TANK_RECOVERY_WORKFLOWS = {
    "irrigation_recovery",
    "irrigation_recovery_check",
}

TWO_TANK_SUPPORTED_WORKFLOWS = TWO_TANK_STARTUP_WORKFLOWS | TWO_TANK_RECOVERY_WORKFLOWS

_CRITICAL_IRR_STATE_EXPECTATIONS: Dict[str, Dict[str, bool]] = {
    "startup": {
        "pump_main": False,
    },
    "clean_fill_check": {
        "pump_main": False,
    },
    "solution_fill_check": {
        "valve_clean_supply": True,
        "valve_solution_fill": True,
        "pump_main": True,
    },
    "prepare_recirculation_check": {
        "valve_solution_supply": True,
        "valve_solution_fill": True,
        "pump_main": True,
    },
    "irrigation_recovery_check": {
        "valve_solution_supply": True,
        "valve_solution_fill": True,
        "valve_irrigation": False,
        "pump_main": True,
    },
}

_MANUAL_STEP_TO_COMMAND_PLAN: Dict[str, str] = {
    "clean_fill_start": "clean_fill_start",
    "clean_fill_stop": "clean_fill_stop",
    "solution_fill_start": "solution_fill_start",
    "solution_fill_stop": "solution_fill_stop",
    "prepare_recirculation_start": "prepare_recirculation_start",
    "prepare_recirculation_stop": "prepare_recirculation_stop",
    "irrigation_recovery_start": "irrigation_recovery_start",
    "irrigation_recovery_stop": "irrigation_recovery_stop",
}

_logger = logging.getLogger(__name__)

# Транзиентные ошибки irr_state, после которых нужно повторить check через poll_interval
_IRR_STATE_TRANSIENT_REASONS = frozenset({"irr_state_unavailable", "irr_state_stale"})

# Ключи payload с таймингами для check-workflows, которые поддерживают retry
_CHECK_WORKFLOW_TIMING_KEYS: Dict[str, tuple] = {
    "prepare_recirculation_check": (
        "prepare_recirculation_started_at",
        "prepare_recirculation_timeout_at",
    ),
    "irrigation_recovery_check": (
        "irrigation_recovery_started_at",
        "irrigation_recovery_timeout_at",
    ),
}

_CHECK_WORKFLOW_TIMEOUT_CFG_KEY: Dict[str, str] = {
    "prepare_recirculation_check": "prepare_recirculation_timeout_sec",
    "irrigation_recovery_check": "irrigation_recovery_timeout_sec",
}

_WORKFLOW_STATE_ACTIVE_PHASES = frozenset({"tank_filling", "tank_recirc", "irrig_recirc"})
_WORKFLOW_STATE_ALLOWED_BY_PHASE: Dict[str, set[str]] = {
    "tank_filling": {"clean_fill_check", "solution_fill_check"},
    "tank_recirc": {"prepare_recirculation_check"},
    "irrig_recirc": {"irrigation_recovery_check"},
}
_WORKFLOW_STATE_FALLBACK_BY_PHASE: Dict[str, str] = {
    "tank_filling": "solution_fill_check",
    "tank_recirc": "prepare_recirculation_check",
    "irrig_recirc": "irrigation_recovery_check",
}
_WORKFLOW_STATE_CARRY_KEYS = {
    "payload_contract_version",
    "workflow_mode",
    "workflow_reason_code",
    "clean_fill_cycle",
    "clean_fill_started_at",
    "clean_fill_timeout_at",
    "solution_fill_started_at",
    "solution_fill_timeout_at",
    "prepare_recirculation_started_at",
    "prepare_recirculation_timeout_at",
    "irrigation_recovery_attempt",
    "irrigation_recovery_started_at",
    "irrigation_recovery_timeout_at",
}
_WORKFLOW_RESUME_TIMING_KEYS: Dict[str, tuple[str, str, str]] = {
    "clean_fill_check": ("clean_fill_started_at", "clean_fill_timeout_at", "clean_fill_timeout_sec"),
    "solution_fill_check": ("solution_fill_started_at", "solution_fill_timeout_at", "solution_fill_timeout_sec"),
    "prepare_recirculation_check": (
        "prepare_recirculation_started_at",
        "prepare_recirculation_timeout_at",
        "prepare_recirculation_timeout_sec",
    ),
    "irrigation_recovery_check": (
        "irrigation_recovery_started_at",
        "irrigation_recovery_timeout_at",
        "irrigation_recovery_timeout_sec",
    ),
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_target_from_range(section: Dict[str, Any]) -> Optional[float]:
    lower = _as_float(section.get("min"))
    upper = _as_float(section.get("max"))
    if lower is None or upper is None:
        return None
    return (lower + upper) / 2.0


def _payload_has_runtime_targets(payload: Dict[str, Any]) -> bool:
    config = _as_dict(payload.get("config"))
    execution = _as_dict(config.get("execution"))
    ph_payload = _as_dict(payload.get("ph"))
    ec_payload = _as_dict(payload.get("ec"))
    targets_payload = _as_dict(payload.get("targets"))
    candidates = (
        execution.get("target_ph"),
        execution.get("target_ec"),
        ph_payload.get("target"),
        ec_payload.get("target"),
        targets_payload.get("target_ph"),
        targets_payload.get("target_ec"),
        targets_payload.get("ph_target"),
        targets_payload.get("ec_target"),
    )
    return any(candidate is not None for candidate in candidates)


def _payload_missing_profile_runtime_settings(payload: Dict[str, Any]) -> bool:
    execution = _as_dict(_as_dict(payload.get("config")).get("execution"))
    required_keys = (
        "prepare_tolerance",
        "prepare_target_tolerance",
        "target_ec_prepare_npk",
        "nutrient_npk_ratio_pct",
        "npk_ratio_pct",
    )
    return not any(key in execution for key in required_keys)


def _extract_profile_execution_overrides(subsystems: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = _as_dict(subsystems.get("diagnostics"))
    diagnostics_execution = _as_dict(diagnostics.get("execution"))
    return dict(diagnostics_execution) if diagnostics_execution else {}


def _extract_profile_targets(subsystems: Dict[str, Any]) -> Dict[str, float]:
    diagnostics = _as_dict(subsystems.get("diagnostics"))
    diagnostics_execution = _as_dict(diagnostics.get("execution"))
    irrigation = _as_dict(subsystems.get("irrigation"))
    irrigation_execution = _as_dict(irrigation.get("execution"))
    correction_node = _as_dict(irrigation_execution.get("correction_node"))
    ph_targets = _as_dict(_as_dict(subsystems.get("ph")).get("targets"))
    ec_targets = _as_dict(_as_dict(subsystems.get("ec")).get("targets"))

    target_ph = _as_float(diagnostics_execution.get("target_ph"))
    target_ec = _as_float(diagnostics_execution.get("target_ec"))

    if target_ph is None:
        target_ph = _as_float(correction_node.get("target_ph"))
    if target_ec is None:
        target_ec = _as_float(correction_node.get("target_ec"))

    if target_ph is None:
        target_ph = _as_float(ph_targets.get("target"))
    if target_ec is None:
        target_ec = _as_float(ec_targets.get("target"))

    if target_ph is None:
        target_ph = _resolve_target_from_range(ph_targets)
    if target_ec is None:
        target_ec = _resolve_target_from_range(ec_targets)

    resolved: Dict[str, float] = {}
    if target_ph is not None:
        resolved["target_ph"] = target_ph
    if target_ec is not None:
        resolved["target_ec"] = target_ec
    return resolved


def _inject_runtime_targets(payload: Dict[str, Any], targets: Dict[str, float]) -> Dict[str, Any]:
    config = _as_dict(payload.get("config"))
    execution = _as_dict(config.get("execution"))
    if execution.get("target_ph") is None and targets.get("target_ph") is not None:
        execution["target_ph"] = float(targets["target_ph"])
    if execution.get("target_ec") is None and targets.get("target_ec") is not None:
        execution["target_ec"] = float(targets["target_ec"])
    if not execution:
        return payload
    updated_config = dict(config)
    updated_config["execution"] = execution
    return {**payload, "config": updated_config}


def _inject_profile_execution(payload: Dict[str, Any], profile_execution: Dict[str, Any]) -> Dict[str, Any]:
    if not profile_execution:
        return payload

    config = _as_dict(payload.get("config"))
    execution = _as_dict(config.get("execution"))
    merged_execution = dict(execution)
    changed = False

    for key, value in profile_execution.items():
        if merged_execution.get(key) is None:
            merged_execution[key] = value
            changed = True

    if not changed:
        return payload

    updated_config = dict(config)
    updated_config["execution"] = merged_execution
    return {**payload, "config": updated_config}


async def _resolve_runtime_payload_with_profile_targets(
    deps: TwoTankDeps,
    *,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    if _payload_has_runtime_targets(payload) and not _payload_missing_profile_runtime_settings(payload):
        return payload

    try:
        rows = await deps.fetch_fn(
            """
            SELECT subsystems
            FROM zone_automation_logic_profiles
            WHERE zone_id = $1
              AND is_active = TRUE
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            deps.zone_id,
        )
    except Exception:
        _logger.warning(
            "Zone %s: failed to load active automation profile for runtime targets",
            deps.zone_id,
            exc_info=True,
        )
        return payload

    if not rows:
        return payload

    row = rows[0]
    record = row if isinstance(row, dict) else dict(row)
    subsystems = record.get("subsystems")
    if isinstance(subsystems, str):
        try:
            subsystems = json.loads(subsystems)
        except Exception:
            subsystems = None
    if not isinstance(subsystems, dict):
        return payload

    profile_execution = _extract_profile_execution_overrides(subsystems)
    payload_with_overrides = _inject_profile_execution(payload, profile_execution)
    profile_targets = _extract_profile_targets(subsystems)
    if profile_targets:
        payload_with_overrides = _inject_runtime_targets(payload_with_overrides, profile_targets)

    if payload_with_overrides == payload:
        return payload

    _logger.info(
        (
            "Zone %s: runtime profile overrides injected "
            "(target_ph=%s, target_ec=%s, has_prepare_tolerance=%s, has_target_ec_prepare_npk=%s)"
        ),
        deps.zone_id,
        profile_targets.get("target_ph"),
        profile_targets.get("target_ec"),
        bool(profile_execution.get("prepare_tolerance")),
        profile_execution.get("target_ec_prepare_npk") is not None,
    )
    return payload_with_overrides


async def _maybe_reenqueue_on_irr_state_transient(
    deps: TwoTankDeps,
    *,
    workflow: str,
    payload: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    irr_state_guard_result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Если irr_state транзиентно недоступен/устарел — повторно ставим в очередь check-задачу.

    Возвращает dict с результатом retry или None (не нужно повторять).
    """
    zone_id = deps.zone_id
    reason_code = irr_state_guard_result.get("reason_code", "")
    if reason_code not in _IRR_STATE_TRANSIENT_REASONS:
        return None

    timing_keys = _CHECK_WORKFLOW_TIMING_KEYS.get(workflow)
    if not timing_keys:
        return None

    from scheduler_internal_enqueue import parse_iso_datetime

    started_key, timeout_key = timing_keys
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    phase_started_at = parse_iso_datetime(str(payload.get(started_key) or "")) or now
    phase_timeout_at = parse_iso_datetime(str(payload.get(timeout_key) or ""))
    if phase_timeout_at is None:
        timeout_cfg_key = _CHECK_WORKFLOW_TIMEOUT_CFG_KEY.get(workflow, "prepare_recirculation_timeout_sec")
        timeout_sec = int(runtime_cfg.get(timeout_cfg_key) or 1800)
        phase_timeout_at = phase_started_at + timedelta(seconds=timeout_sec)

    if now >= phase_timeout_at:
        # Таймаут вышел — не ре-энкью, отдаём ошибку вызывающей стороне
        return None

    try:
        enqueue_result = await deps._enqueue_two_tank_check(
            zone_id=zone_id,
            payload=payload,
            workflow=workflow,
            phase_started_at=phase_started_at,
            phase_timeout_at=phase_timeout_at,
            poll_interval_sec=int(runtime_cfg.get("poll_interval_sec") or 60),
        )
    except Exception:
        _logger.warning(
            "Zone %s: failed to re-enqueue %s after irr_state transient error (%s)",
            zone_id,
            workflow,
            reason_code,
            exc_info=True,
        )
        return None

    _logger.info(
        "Zone %s: irr_state transient error (%s) — re-enqueued %s check",
        zone_id,
        reason_code,
        workflow,
    )
    return {
        **irr_state_guard_result,
        "mode": f"two_tank_{workflow.replace('_check', '')}_irr_state_retry",
        "irr_state_retry": True,
        "next_check": enqueue_result,
    }


def _normalize_workflow_state_payload(raw_payload: Any) -> Dict[str, Any]:
    if isinstance(raw_payload, dict):
        return dict(raw_payload)
    if isinstance(raw_payload, (bytes, bytearray)):
        try:
            raw_payload = raw_payload.decode("utf-8")
        except Exception:
            return {}
    if isinstance(raw_payload, str):
        source = raw_payload.strip()
        if not source:
            return {}
        try:
            decoded = json.loads(source)
        except Exception:
            return {}
        if isinstance(decoded, dict):
            return decoded
    return {}


def _coerce_utc_naive_datetime(raw_value: Any) -> Optional[datetime]:
    if not isinstance(raw_value, datetime):
        return None
    if raw_value.tzinfo is None:
        return raw_value
    return raw_value.astimezone(timezone.utc).replace(tzinfo=None)


def _resolve_startup_workflow_from_state_payload(*, phase: str, state_payload: Dict[str, Any]) -> str:
    raw_workflow = (
        state_payload.get("workflow_stage")
        or state_payload.get("workflow")
        or state_payload.get("diagnostics_workflow")
        or ""
    )
    payload_workflow = str(raw_workflow or "").strip().lower()
    has_clean_timestamps = bool(
        str(state_payload.get("clean_fill_started_at") or "").strip()
        or str(state_payload.get("clean_fill_timeout_at") or "").strip()
    )
    has_solution_timestamps = bool(
        str(state_payload.get("solution_fill_started_at") or "").strip()
        or str(state_payload.get("solution_fill_timeout_at") or "").strip()
    )
    fallback_workflow = _WORKFLOW_STATE_FALLBACK_BY_PHASE.get(phase, "")
    if phase == "tank_filling":
        if has_clean_timestamps and not has_solution_timestamps:
            fallback_workflow = "clean_fill_check"
        elif has_solution_timestamps:
            fallback_workflow = "solution_fill_check"

    mapped_workflow = payload_workflow
    if payload_workflow in {"startup", "cycle_start", "refill_check"}:
        mapped_workflow = fallback_workflow
    elif payload_workflow == "prepare_recirculation":
        mapped_workflow = "prepare_recirculation_check"
    elif payload_workflow == "irrigation_recovery":
        mapped_workflow = "irrigation_recovery_check"

    allowed = _WORKFLOW_STATE_ALLOWED_BY_PHASE.get(phase, set())
    if mapped_workflow in allowed:
        return mapped_workflow
    return fallback_workflow if fallback_workflow in allowed else ""


def _merge_resume_payload(
    *,
    payload: Dict[str, Any],
    state_payload: Dict[str, Any],
    workflow: str,
    phase: str,
) -> Dict[str, Any]:
    merged_payload = dict(payload)
    for key in _WORKFLOW_STATE_CARRY_KEYS:
        if key in state_payload:
            merged_payload[key] = state_payload[key]
    merged_payload["workflow"] = workflow
    merged_payload["workflow_stage"] = workflow
    merged_payload["workflow_phase"] = phase
    if "payload_contract_version" not in merged_payload:
        merged_payload["payload_contract_version"] = state_payload.get("payload_contract_version") or "v2"
    return merged_payload


def _ensure_resume_timing_fields(
    *,
    payload: Dict[str, Any],
    workflow: str,
    runtime_cfg: Dict[str, Any],
    now: datetime,
) -> Optional[Dict[str, Any]]:
    timing_keys = _WORKFLOW_RESUME_TIMING_KEYS.get(workflow)
    if timing_keys is None:
        return payload

    from scheduler_internal_enqueue import parse_iso_datetime

    started_key, timeout_key, timeout_cfg_key = timing_keys
    updated_payload = dict(payload)
    phase_started_at = parse_iso_datetime(str(updated_payload.get(started_key) or "")) or now
    phase_timeout_at = parse_iso_datetime(str(updated_payload.get(timeout_key) or ""))
    if phase_timeout_at is None:
        timeout_sec = int(runtime_cfg.get(timeout_cfg_key) or 0)
        if timeout_sec <= 0:
            return None
        phase_timeout_at = phase_started_at + timedelta(seconds=timeout_sec)
    if now >= phase_timeout_at:
        return None

    updated_payload[started_key] = phase_started_at.isoformat()
    updated_payload[timeout_key] = phase_timeout_at.isoformat()
    if workflow == "clean_fill_check":
        updated_payload["clean_fill_cycle"] = max(1, int(updated_payload.get("clean_fill_cycle") or 1))
    if workflow == "irrigation_recovery_check":
        updated_payload["irrigation_recovery_attempt"] = max(
            1,
            int(updated_payload.get("irrigation_recovery_attempt") or 1),
        )
    return updated_payload


async def _maybe_resume_two_tank_startup_workflow(
    deps: TwoTankDeps,
    *,
    payload: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
) -> tuple[Dict[str, Any], Optional[str]]:
    zone_id = deps.zone_id
    try:
        rows = await deps.fetch_fn(
            """
            SELECT workflow_phase, updated_at, payload
            FROM zone_workflow_state
            WHERE zone_id = $1
            LIMIT 1
            """,
            zone_id,
        )
    except Exception:
        _logger.warning(
            "Zone %s: failed to load zone_workflow_state for startup resume",
            zone_id,
            exc_info=True,
        )
        return payload, None

    if not rows:
        return payload, None

    row = rows[0]
    record = row if isinstance(row, dict) else dict(row)
    phase = str(record.get("workflow_phase") or "").strip().lower()
    if phase not in _WORKFLOW_STATE_ACTIVE_PHASES:
        return payload, None

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    updated_at = _coerce_utc_naive_datetime(record.get("updated_at"))
    if updated_at is not None:
        active_timeout_candidates = [
            int(runtime_cfg.get("clean_fill_timeout_sec") or 0),
            int(runtime_cfg.get("solution_fill_timeout_sec") or 0),
            int(runtime_cfg.get("prepare_recirculation_timeout_sec") or 0),
            int(runtime_cfg.get("irrigation_recovery_timeout_sec") or 0),
            int(runtime_cfg.get("poll_interval_sec") or 0) * 3,
            300,
        ]
        max_resume_age_sec = max(active_timeout_candidates)
        age_sec = max(0.0, (now - updated_at).total_seconds())
        if age_sec > float(max_resume_age_sec):
            return payload, None

    state_payload = _normalize_workflow_state_payload(record.get("payload"))
    if not state_payload:
        return payload, None

    resume_workflow = _resolve_startup_workflow_from_state_payload(phase=phase, state_payload=state_payload)
    if not resume_workflow:
        return payload, None

    resume_payload = _merge_resume_payload(
        payload=payload,
        state_payload=state_payload,
        workflow=resume_workflow,
        phase=phase,
    )
    resume_payload = _ensure_resume_timing_fields(
        payload=resume_payload,
        workflow=resume_workflow,
        runtime_cfg=runtime_cfg,
        now=now,
    )
    if resume_payload is None:
        return payload, None

    _logger.info(
        "Zone %s: startup workflow resumed from workflow_state (phase=%s, workflow=%s)",
        zone_id,
        phase,
        resume_workflow,
    )
    return resume_payload, resume_workflow


_MANUAL_STEP_TO_PHASE: Dict[str, str] = {
    "clean_fill_start": "tank_filling",
    "clean_fill_stop": "idle",
    "solution_fill_start": "tank_filling",
    "solution_fill_stop": "idle",
    "prepare_recirculation_start": "tank_recirc",
    "prepare_recirculation_stop": "idle",
    "irrigation_recovery_start": "irrig_recirc",
    "irrigation_recovery_stop": "idle",
}


async def execute_two_tank_startup_workflow_core(
    deps: TwoTankDeps,
    *,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
) -> Dict[str, Any]:
    zone_id = deps.zone_id
    payload = await _resolve_runtime_payload_with_profile_targets(deps, payload=payload)
    runtime_cfg = deps._resolve_two_tank_runtime_config(payload)
    workflow = deps._normalize_two_tank_workflow(payload)
    if workflow == "startup":
        payload, resumed_workflow = await _maybe_resume_two_tank_startup_workflow(
            deps,
            payload=payload,
            runtime_cfg=runtime_cfg,
        )
        if resumed_workflow:
            workflow = resumed_workflow

    if workflow not in TWO_TANK_SUPPORTED_WORKFLOWS:
        return two_tank_error(
            mode="two_tank_unknown_workflow",
            workflow=workflow,
            reason_code="unsupported_workflow",
            reason=f"Неподдерживаемый workflow для топологии two_tank: {workflow or '<missing>'}",
            error_code="unsupported_workflow",
            error="unsupported_workflow",
        )

    await deps._emit_task_event(
        zone_id=zone_id,
        task_type="diagnostics",
        context=context,
        event_type="TWO_TANK_STARTUP_INITIATED",
        payload={
            "workflow": workflow,
            "topology": deps._extract_topology(payload),
            "action_required": decision.action_required,
            "decision": decision.decision,
            "reason_code": decision.reason_code,
        },
    )

    stage_phase = WORKFLOW_STAGE_TO_PHASE.get(workflow)
    if stage_phase:
        await deps._update_zone_workflow_phase(
            zone_id=zone_id,
            workflow_phase=stage_phase,
            workflow_stage=workflow,
            reason_code=decision.reason_code,
            context=context,
        )

    nodes_state = await deps._check_required_nodes_online(zone_id, runtime_cfg["required_node_types"])
    if nodes_state["missing_types"]:
        return two_tank_error(
            mode="two_tank_required_nodes_missing",
            workflow=workflow,
            reason_code=REASON_CYCLE_BLOCKED_NODES_UNAVAILABLE,
            reason="Нет online-нод, необходимых для startup 2-бакового контура",
            error_code=ERR_CYCLE_REQUIRED_NODES_UNAVAILABLE,
            missing_node_types=nodes_state["missing_types"],
        )

    if workflow == "manual_step":
        manual_step = str(payload.get("manual_step") or "").strip().lower()
        command_plan_name = _MANUAL_STEP_TO_COMMAND_PLAN.get(manual_step)
        if not command_plan_name:
            return two_tank_error(
                mode="two_tank_manual_step_unsupported",
                workflow=workflow,
                reason_code="manual_step_unsupported",
                reason=f"Неподдерживаемый manual_step: {manual_step or '<missing>'}",
                error_code="manual_step_unsupported",
                error="manual_step_unsupported",
                manual_step=manual_step or None,
            )

        phase = _MANUAL_STEP_TO_PHASE.get(manual_step)
        if phase:
            await deps._update_zone_workflow_phase(
                zone_id=zone_id,
                workflow_phase=phase,
                workflow_stage="manual_step",
                reason_code="manual_step_requested",
                context=context,
            )

        await deps._emit_task_event(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="MANUAL_STEP_REQUESTED",
            payload={
                "workflow": workflow,
                "manual_step": manual_step,
                "command_plan": command_plan_name,
                "reason_code": "manual_step_requested",
            },
        )

        command_plan = runtime_cfg["commands"].get(command_plan_name)
        if not isinstance(command_plan, list) or not command_plan:
            return two_tank_error(
                mode="two_tank_manual_step_failed",
                workflow=workflow,
                reason_code="manual_step_command_plan_missing",
                reason=f"Не найден command plan для manual step: {manual_step}",
                error_code="manual_step_command_plan_missing",
                error="manual_step_command_plan_missing",
                manual_step=manual_step,
                workflow_phase=phase,
            )

        plan_result = await deps._dispatch_two_tank_command_plan(
            zone_id=zone_id,
            command_plan=command_plan,
            context=context,
            decision=DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code="manual_step_requested",
                reason=f"Выполнение manual step: {manual_step}",
            ),
        )
        if not plan_result.get("success"):
            return two_tank_error(
                mode="two_tank_manual_step_failed",
                workflow=workflow,
                reason_code="manual_step_failed",
                reason=f"Не удалось выполнить manual step: {manual_step}",
                error_code=str(plan_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
                error=str(plan_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                commands_total=plan_result.get("commands_total", 0),
                commands_failed=plan_result.get("commands_failed", 1),
                command_statuses=plan_result.get("command_statuses", []),
                manual_step=manual_step,
                workflow_phase=phase,
            )

        await deps._emit_task_event(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="MANUAL_STEP_EXECUTED",
            payload={
                "workflow": workflow,
                "manual_step": manual_step,
                "command_plan": command_plan_name,
                "commands_total": plan_result.get("commands_total", 0),
                "commands_effect_confirmed": plan_result.get("commands_effect_confirmed", 0),
                "commands_failed": plan_result.get("commands_failed", 0),
                "reason_code": "manual_step_executed",
            },
        )

        return two_tank_success(
            mode="two_tank_manual_step_executed",
            workflow=workflow,
            reason_code="manual_step_executed",
            reason=f"Manual step выполнен: {manual_step}",
            action_required=True,
            decision="run",
            commands_total=plan_result.get("commands_total", 0),
            commands_failed=plan_result.get("commands_failed", 0),
            command_statuses=plan_result.get("command_statuses", []),
            manual_step=manual_step,
            workflow_phase=phase,
            commands_effect_confirmed=plan_result.get("commands_effect_confirmed", 0),
        )

    if deps.safety_config.irr_state_validation:
        state_cmd_id = await request_irr_state_snapshot_best_effort(
            deps,
            zone_id=zone_id,
            workflow=workflow,
        )
        irr_state_guard_result = await validate_irr_state_expected_vs_actual(
            deps,
            zone_id=zone_id,
            workflow=workflow,
            runtime_cfg=runtime_cfg,
            critical_expectations=_CRITICAL_IRR_STATE_EXPECTATIONS,
            requested_state_cmd_id=state_cmd_id,
        )
        if irr_state_guard_result is not None:
            retry_result = await _maybe_reenqueue_on_irr_state_transient(
                deps,
                workflow=workflow,
                payload=payload,
                runtime_cfg=runtime_cfg,
                irr_state_guard_result=irr_state_guard_result,
            )
            if retry_result is not None:
                return retry_result
            return irr_state_guard_result

    if workflow in TWO_TANK_STARTUP_WORKFLOWS:
        from domain.workflows.two_tank_startup_core import execute_two_tank_startup_branch

        return await execute_two_tank_startup_branch(
            deps,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
            workflow=workflow,
        )

    if workflow in TWO_TANK_RECOVERY_WORKFLOWS:
        from domain.workflows.two_tank_recovery_core import execute_two_tank_recovery_branch

        return await execute_two_tank_recovery_branch(
            deps,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
            workflow=workflow,
        )

    return two_tank_error(
        mode="two_tank_unknown_workflow",
        workflow=workflow,
        reason_code="unsupported_workflow",
        reason=f"Неподдерживаемый workflow для топологии two_tank: {workflow}",
        error_code="unsupported_workflow",
        error="unsupported_workflow",
    )
