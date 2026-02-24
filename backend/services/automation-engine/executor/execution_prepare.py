"""Helpers for execute() input normalization and mapping resolution."""

from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


GetTaskMappingFn = Callable[[str, Dict[str, Any]], Any]


def prepare_execution_inputs(
    *,
    task_type: str,
    payload: Dict[str, Any],
    get_task_mapping_fn: GetTaskMappingFn,
) -> Tuple[str, Dict[str, Any], Any]:
    normalized_task_type = str(task_type or "").strip().lower()
    normalized_payload = payload if isinstance(payload, dict) else {}
    config = normalized_payload.get("config") if isinstance(normalized_payload.get("config"), dict) else {}
    mapping = get_task_mapping_fn(normalized_task_type, config)
    return normalized_task_type, normalized_payload, mapping


__all__ = ["prepare_execution_inputs"]
