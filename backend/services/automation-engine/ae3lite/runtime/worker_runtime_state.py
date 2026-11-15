"""Per-instance lifecycle state; no repositories or policy methods."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class WorkerRuntimeState:
    active_shutdown_grace_sec: float | None = None
    drain_task: Optional[Any] = None
    inflight_automation_tasks: dict[asyncio.Task, Any] = field(default_factory=dict)
    last_active_task_age_metrics_monotonic: float | None = None
    last_drain_exit_ok: bool = True
    last_drain_exit_reason: str = 'idle'
    last_orphan_intent_reconcile_monotonic: float | None = None
    last_stale_task_reconcile_monotonic: float | None = None
    last_terminal_command_reconcile_monotonic: float | None = None
    lease_release_fail_zones: set[int] = field(default_factory=set)
    lease_release_resolve_attempt_at: dict[int, datetime] = field(default_factory=dict)
    pending_correction_safety_checks: list[Any] = field(default_factory=list)
    pending_health_cache: tuple[float, bool] | None = None
    pending_kicks: int = 0
    reconcile_loop_task: Optional[Any] = None
    respawn_guard_task: Optional[Any] = None
    shutting_down: bool = False
    wake_handle: Optional[asyncio.Handle] = None
    wake_task: Optional[Any] = None
