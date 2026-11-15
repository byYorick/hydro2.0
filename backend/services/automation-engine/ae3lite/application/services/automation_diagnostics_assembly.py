"""automation diagnostics assembly: one cohesive policy."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from ae3lite.application.services.automation_diagnostics_hints import (
    _append_hint,
    _append_irrigation_block_hint,
    _dedupe_hints,
    _overall_health,
    _summarize_required_nodes,
)
from ae3lite.application.services.automation_diagnostics_projection import _build_runtime_view
from ae3lite.application.services.automation_diagnostics_timing import _append_task_timing_hints
from ae3lite.application.services.automation_diagnostics_values import _HANG_HINT_LABELS
from ae3lite.application.services.automation_diagnostics_workflow_sensors import _append_workflow_sensor_hints
from common.observability_thresholds import (
    resolved_thresholds,
)


def build_automation_observability(
    *,
    zone_id: int,
    task: Any | None,
    workflow_state: Any | None,
    telemetry: Mapping[str, Any],
    telemetry_fetch_ok: bool,
    now: datetime,
    node_rows: Sequence[Mapping[str, Any]] | None = None,
    thresholds: Mapping[str, Any] | None = None,
    irrigation_task: Any | None = None,
) -> dict[str, Any]:
    """Собирает runtime-диагностику для `/zones/{id}/state`."""
    cfg = resolved_thresholds(thresholds)
    hints: list[dict[str, Any]] = []
    runtime, status = _build_runtime_view(zone_id=zone_id, task=task, workflow_state=workflow_state, now=now)

    if not telemetry_fetch_ok:
        _append_hint(
            hints,
            code="telemetry_unavailable",
            severity="warning",
            message=_HANG_HINT_LABELS["telemetry_unavailable"],
        )

    current_stage, stage_elapsed, workflow_phase = _append_task_timing_hints(
        runtime=runtime, cfg=cfg, hints=hints, status=status
    )

    _append_workflow_sensor_hints(
        runtime=runtime,
        workflow_state=workflow_state,
        workflow_phase=workflow_phase,
        task=task,
        hints=hints,
        cfg=cfg,
        telemetry_fetch_ok=telemetry_fetch_ok,
        telemetry=telemetry,
        current_stage=current_stage,
        stage_elapsed=stage_elapsed,
    )
    _append_irrigation_block_hint(
        hints,
        irrigation_task if irrigation_task is not None else task,
    )
    nodes_summary = _summarize_required_nodes(node_rows or (), cfg)
    if nodes_summary.get("offline_required"):
        _append_hint(
            hints,
            code="nodes_offline",
            severity="critical" if nodes_summary.get("persistent_offline") else "warning",
            message=_HANG_HINT_LABELS["nodes_offline"],
            details={"nodes": nodes_summary.get("nodes", [])},
        )

    overall = _overall_health(hints, runtime)
    return {
        "runtime": runtime,
        "nodes": nodes_summary,
        "hang_hints": _dedupe_hints(hints),
        "overall_health": overall,
    }
