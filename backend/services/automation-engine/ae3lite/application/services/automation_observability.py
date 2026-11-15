"""Compatibility entry points for application/services/automation_observability.py; implementations have explicit policy owners."""

from __future__ import annotations
from ae3lite.application.services.automation_diagnostics_assembly import build_automation_observability
from ae3lite.application.services.automation_diagnostics_projection import (
    _build_runtime_view,
    _normalize_utc_naive,
    _iso_or_none,
)
from ae3lite.application.services.automation_diagnostics_timing import _append_task_timing_hints
from ae3lite.application.services.automation_diagnostics_workflow_sensors import _append_workflow_sensor_hints
from ae3lite.application.services.automation_diagnostics_hints import (
    _severity_for_elapsed,
    _append_hint,
    _append_irrigation_block_hint,
    _summarize_required_nodes,
    _dedupe_hints,
    _overall_health,
)
from ae3lite.application.services.automation_diagnostics_values import (
    _ACTIVE_TASK_STATUSES,
    _DISPATCH_STUCK_STATUSES,
    _SENSOR_BLOCK_REASONS,
    _SOLUTION_TEMP_BLOCK_REASONS,
    _HANG_HINT_LABELS,
    _HANG_HINT_RECOMMENDATIONS,
)

__all__ = ["build_automation_observability"]
