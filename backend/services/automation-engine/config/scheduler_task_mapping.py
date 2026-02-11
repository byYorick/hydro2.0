"""Конфигурация маппинга абстрактных scheduler-задач в команды automation-engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SchedulerTaskMapping:
    task_type: str
    node_types: Tuple[str, ...] = ()
    cmd: Optional[str] = None
    cmd_true: Optional[str] = None
    cmd_false: Optional[str] = None
    state_key: Optional[str] = None
    default_state: Optional[bool] = None
    default_params: Dict[str, Any] = field(default_factory=dict)
    default_duration_sec: Optional[float] = None
    duration_target_paths: Tuple[Tuple[str, str], ...] = ()


_DEFAULT_MAPPING: Dict[str, SchedulerTaskMapping] = {
    "irrigation": SchedulerTaskMapping(
        task_type="irrigation",
        node_types=("irrig", "irrigation"),
        cmd="run_pump",
        default_duration_sec=60.0,
        duration_target_paths=(("irrigation", "duration_sec"),),
    ),
    "lighting": SchedulerTaskMapping(
        task_type="lighting",
        node_types=("light", "lighting"),
        cmd_true="light_on",
        cmd_false="light_off",
        state_key="desired_state",
        default_state=True,
    ),
    "ventilation": SchedulerTaskMapping(
        task_type="ventilation",
        node_types=("climate", "climate_control", "ventilation"),
        cmd="set_relay",
        state_key="state",
        default_state=True,
        default_params={"state": True},
    ),
    "solution_change": SchedulerTaskMapping(
        task_type="solution_change",
        node_types=("irrig", "irrigation"),
        cmd="run_pump",
        default_duration_sec=180.0,
        duration_target_paths=(("solution_change", "duration_sec"),),
    ),
    "mist": SchedulerTaskMapping(
        task_type="mist",
        node_types=("mist", "fog", "fogger", "climate", "climate_control"),
        cmd="set_relay",
        state_key="state",
        default_state=True,
        default_params={"state": True},
    ),
    "diagnostics": SchedulerTaskMapping(
        task_type="diagnostics",
    ),
}


def _as_tuple(raw: Any, *, default: Tuple[str, ...]) -> Tuple[str, ...]:
    if isinstance(raw, str):
        value = raw.strip()
        return (value,) if value else default

    if isinstance(raw, Sequence):
        normalized = tuple(str(item).strip() for item in raw if str(item).strip())
        return normalized or default

    return default


def _as_optional_bool(raw: Any) -> Optional[bool]:
    if raw is None:
        return None
    return bool(raw)


def get_task_mapping(task_type: str, config_payload: Optional[Dict[str, Any]] = None) -> SchedulerTaskMapping:
    """
    Получить mapping задачи.

    Поддерживает override из `payload.config.execution`:
    - node_types
    - cmd / cmd_true / cmd_false
    - state_key / default_state
    - params (default params)
    - duration_sec
    """
    normalized_type = str(task_type or "").strip().lower()
    base = _DEFAULT_MAPPING.get(normalized_type)
    if not base:
        raise ValueError(f"Unsupported task_type mapping: {task_type}")

    config_payload = config_payload if isinstance(config_payload, dict) else {}
    execution = config_payload.get("execution") if isinstance(config_payload.get("execution"), dict) else {}

    override_params = execution.get("params") if isinstance(execution.get("params"), dict) else {}
    merged_params = dict(base.default_params)
    merged_params.update(override_params)

    duration_sec = execution.get("duration_sec")
    try:
        duration_value = float(duration_sec) if duration_sec is not None else base.default_duration_sec
    except (TypeError, ValueError):
        duration_value = base.default_duration_sec

    return SchedulerTaskMapping(
        task_type=base.task_type,
        node_types=_as_tuple(execution.get("node_types"), default=base.node_types),
        cmd=str(execution.get("cmd")).strip() if execution.get("cmd") else base.cmd,
        cmd_true=str(execution.get("cmd_true")).strip() if execution.get("cmd_true") else base.cmd_true,
        cmd_false=str(execution.get("cmd_false")).strip() if execution.get("cmd_false") else base.cmd_false,
        state_key=str(execution.get("state_key")).strip() if execution.get("state_key") else base.state_key,
        default_state=_as_optional_bool(execution.get("default_state"))
        if "default_state" in execution
        else base.default_state,
        default_params=merged_params,
        default_duration_sec=duration_value,
        duration_target_paths=base.duration_target_paths,
    )
