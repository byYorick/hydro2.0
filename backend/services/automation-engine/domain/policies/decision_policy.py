"""Decision policy helpers for scheduler task execution."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from domain.models.decision_models import DecisionOutcome


def safe_float(raw: Any) -> Optional[float]:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def safe_int(raw: Any) -> Optional[int]:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value


def safe_bool(raw: Any) -> Optional[bool]:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        if raw == 1:
            return True
        if raw == 0:
            return False
        return None
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def extract_nested_metric(payload: Dict[str, Any], keys: Sequence[str]) -> Optional[float]:
    sources: List[Dict[str, Any]] = []
    for source_key in ("sensor_inputs", "sensors", "telemetry", "metrics"):
        raw = payload.get(source_key)
        if isinstance(raw, dict):
            sources.append(raw)
    sources.append(payload)

    for source in sources:
        for key in keys:
            value = safe_float(source.get(key))
            if value is not None:
                return value
    return None


def extract_nested_bool(payload: Dict[str, Any], keys: Sequence[str]) -> Optional[bool]:
    sources: List[Dict[str, Any]] = []
    for source_key in ("sensor_inputs", "safety", "telemetry", "metrics"):
        raw = payload.get(source_key)
        if isinstance(raw, dict):
            sources.append(raw)
    sources.append(payload)

    for source in sources:
        for key in keys:
            value = safe_bool(source.get(key))
            if isinstance(value, bool):
                return value
    return None


def extract_retry_attempt(payload: Dict[str, Any]) -> int:
    for key in ("decision_retry_attempt", "retry_attempt", "attempt"):
        parsed = safe_int(payload.get(key))
        if parsed is not None:
            return max(0, parsed)
    return 0


def decide_irrigation_action(
    *,
    payload: Dict[str, Any],
    auto_logic_new_sensors_v1: bool,
) -> DecisionOutcome:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    decision_cfg = execution.get("decision") if isinstance(execution.get("decision"), dict) else {}
    safety_cfg = execution.get("safety") if isinstance(execution.get("safety"), dict) else {}

    max_retry = max(
        1,
        safe_int(
            decision_cfg.get("max_retry")
            if decision_cfg.get("max_retry") is not None
            else execution.get("max_retry")
        )
        or 10,
    )
    backoff_sec = max(
        10,
        safe_int(
            decision_cfg.get("backoff_sec")
            if decision_cfg.get("backoff_sec") is not None
            else execution.get("backoff_sec")
        )
        or 60,
    )
    attempt = extract_retry_attempt(payload)
    next_due_at = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=backoff_sec)).isoformat()

    low_water = extract_nested_bool(
        payload,
        ("low_water", "is_low_water", "solution_low_water"),
    )
    if low_water is None:
        low_water = safe_bool(safety_cfg.get("low_water"))

    nodes_unavailable = extract_nested_bool(
        payload,
        ("nodes_unavailable", "required_nodes_unavailable"),
    )
    if nodes_unavailable is None:
        nodes_unavailable = safe_bool(safety_cfg.get("nodes_unavailable"))

    if low_water is True:
        decision = "retry" if attempt < max_retry else "fail"
        return DecisionOutcome(
            action_required=False,
            decision=decision,
            reason_code="low_water",
            reason="Недостаточный уровень воды/раствора, запуск полива отложен",
            details={
                "retry_attempt": attempt + 1,
                "retry_max_attempts": max_retry,
                "retry_backoff_sec": backoff_sec,
                "next_due_at": next_due_at,
                "safety_flags": ["low_water"],
            },
        )

    if nodes_unavailable is True:
        decision = "retry" if attempt < max_retry else "fail"
        return DecisionOutcome(
            action_required=False,
            decision=decision,
            reason_code="nodes_unavailable",
            reason="Недоступны обязательные ноды полива, запуск отложен",
            details={
                "retry_attempt": attempt + 1,
                "retry_max_attempts": max_retry,
                "retry_backoff_sec": backoff_sec,
                "next_due_at": next_due_at,
                "safety_flags": ["nodes_unavailable"],
            },
        )

    if auto_logic_new_sensors_v1:
        soil_moisture_pct = extract_nested_metric(
            payload,
            ("soil_moisture_pct", "soil_moisture", "substrate_moisture"),
        )
        soil_temp_c = extract_nested_metric(
            payload,
            ("soil_temp_c", "soil_temperature", "substrate_temp_c"),
        )
        ambient_temp_c = extract_nested_metric(
            payload,
            ("ambient_temp_c", "ambient_temp", "air_temp_c", "temp_air"),
        )
        moisture_target_pct = safe_float(decision_cfg.get("moisture_target_pct"))
        if moisture_target_pct is None:
            moisture_target_pct = 80.0
        moisture_tolerance_pct = safe_float(decision_cfg.get("moisture_tolerance_pct"))
        if moisture_tolerance_pct is None:
            moisture_tolerance_pct = 10.0
        reduced_ratio = safe_float(decision_cfg.get("reduced_run_ratio"))
        if reduced_ratio is None:
            reduced_ratio = 0.30
        high_temperature_c = safe_float(decision_cfg.get("high_temperature_c"))
        if high_temperature_c is None:
            high_temperature_c = 30.0

        lower_bound = moisture_target_pct - moisture_tolerance_pct
        upper_bound = moisture_target_pct + moisture_tolerance_pct

        if soil_moisture_pct is not None and lower_bound <= soil_moisture_pct <= upper_bound:
            if ambient_temp_c is not None and ambient_temp_c >= high_temperature_c:
                return DecisionOutcome(
                    action_required=True,
                    decision="run",
                    reason_code="irrigation_required",
                    reason="Влажность в норме, но высокая температура требует сниженный полив",
                    details={
                        "run_mode": "run_reduced",
                        "run_ratio": reduced_ratio,
                        "sensor_snapshot": {
                            "soil_moisture_pct": soil_moisture_pct,
                            "soil_temp_c": soil_temp_c,
                            "ambient_temp_c": ambient_temp_c,
                        },
                    },
                )
            return DecisionOutcome(
                action_required=False,
                decision="skip",
                reason_code="target_already_met",
                reason="Влажность субстрата в норме, полив не требуется",
                details={
                    "run_mode": "skip",
                    "sensor_snapshot": {
                        "soil_moisture_pct": soil_moisture_pct,
                        "soil_temp_c": soil_temp_c,
                        "ambient_temp_c": ambient_temp_c,
                    },
                },
            )

        if soil_moisture_pct is not None and soil_moisture_pct < lower_bound:
            return DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code="irrigation_required",
                reason="Влажность ниже нормы, требуется полный цикл полива",
                details={
                    "run_mode": "run_full",
                    "sensor_snapshot": {
                        "soil_moisture_pct": soil_moisture_pct,
                        "soil_temp_c": soil_temp_c,
                        "ambient_temp_c": ambient_temp_c,
                    },
                },
            )

    return DecisionOutcome(
        action_required=True,
        decision="run",
        reason_code="irrigation_required",
        reason="Требуется выполнить задачу по расписанию",
        details={"run_mode": "run_full"},
    )


def decide_action(
    *,
    task_type: str,
    payload: Dict[str, Any],
    auto_logic_decision_v1: bool,
    auto_logic_new_sensors_v1: bool,
) -> DecisionOutcome:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}

    already_running = extract_nested_bool(
        payload,
        ("already_running", "is_running", "operation_in_progress"),
    )
    if already_running is True:
        return DecisionOutcome(
            action_required=False,
            decision="skip",
            reason_code="already_running",
            reason="Операция уже выполняется, повторный запуск не требуется",
        )

    outside_window = extract_nested_bool(
        payload,
        ("outside_window", "is_outside_window"),
    )
    if outside_window is True:
        return DecisionOutcome(
            action_required=False,
            decision="skip",
            reason_code="outside_window",
            reason="Задача вызвана вне допустимого окна выполнения",
        )

    safety_blocked = extract_nested_bool(
        payload,
        ("safety_blocked", "blocked_by_safety"),
    )
    if safety_blocked is None:
        safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
        safety_blocked = safe_bool(safety.get("blocked"))
    if safety_blocked is True:
        return DecisionOutcome(
            action_required=False,
            decision="skip",
            reason_code="safety_blocked",
            reason="Выполнение заблокировано safety-политикой",
        )

    if execution.get("force_skip") is True:
        return DecisionOutcome(
            action_required=False,
            decision="skip",
            reason_code=f"{task_type}_not_required",
            reason="Пропуск задачи по force_skip",
        )

    if execution.get("force_execute") is True:
        return DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=f"{task_type}_required",
            reason="Принудительное выполнение по force_execute",
        )

    explicit_action_required = payload.get("action_required")
    if isinstance(explicit_action_required, bool):
        if explicit_action_required:
            return DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code=f"{task_type}_required",
                reason="Явно запрошено выполнение action_required=true",
            )
        return DecisionOutcome(
            action_required=False,
            decision="skip",
            reason_code=f"{task_type}_not_required",
            reason="Явно запрошен пропуск action_required=false",
        )

    if task_type == "irrigation" and auto_logic_decision_v1:
        return decide_irrigation_action(
            payload=payload,
            auto_logic_new_sensors_v1=auto_logic_new_sensors_v1,
        )

    if task_type == "lighting":
        desired_state = payload.get("desired_state")
        current_state = payload.get("current_state")
        if isinstance(desired_state, bool) and isinstance(current_state, bool) and desired_state == current_state:
            return DecisionOutcome(
                action_required=False,
                decision="skip",
                reason_code="lighting_already_in_target_state",
                reason="Свет уже находится в целевом состоянии",
            )

    return DecisionOutcome(
        action_required=True,
        decision="run",
        reason_code=f"{task_type}_required",
        reason="Требуется выполнить задачу по расписанию",
    )


def extract_next_due_at(*, decision: DecisionOutcome, result: Dict[str, Any]) -> Optional[str]:
    raw = result.get("next_due_at")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(result.get("next_check"), dict):
        scheduled_for = result["next_check"].get("scheduled_for")
        if isinstance(scheduled_for, str) and scheduled_for.strip():
            return scheduled_for.strip()
    if isinstance(decision.details, dict):
        raw = decision.details.get("next_due_at")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None
