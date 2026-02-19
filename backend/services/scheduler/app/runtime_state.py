from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Set


@dataclass
class SchedulerRuntimeState:
    """Runtime mutable state extracted from scheduler main module."""

    last_schedule_checks: Dict[int, datetime] = field(default_factory=dict)
    loaded_zone_cursors: Set[int] = field(default_factory=set)
    task_terminal_counts: Dict[str, int] = field(default_factory=dict)
    task_deadline_violations: Dict[str, int] = field(default_factory=dict)
    active_tasks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    active_schedule_tasks: Dict[str, str] = field(default_factory=dict)
    window_last_state: Dict[str, bool] = field(default_factory=dict)
    last_diagnostic_at: Dict[str, datetime] = field(default_factory=dict)

    bootstrap_ready: bool = False
    bootstrap_lease_id: Optional[str] = None
    bootstrap_lease_ttl_sec: int = 60
    bootstrap_poll_interval_sec: int = 5
    bootstrap_next_attempt_at: Optional[datetime] = None
    bootstrap_next_heartbeat_at: Optional[datetime] = None
    bootstrap_lease_expires_at: Optional[datetime] = None
    bootstrap_retry_idx: int = 0

    leader_conn: Optional[Any] = None
    leader_active: bool = False
    leader_next_attempt_at: Optional[datetime] = None
    leader_next_healthcheck_at: Optional[datetime] = None

    @classmethod
    def from_module(cls, m: Any) -> "SchedulerRuntimeState":
        return cls(
            last_schedule_checks=m._LAST_SCHEDULE_CHECKS,
            loaded_zone_cursors=m._LOADED_ZONE_CURSORS,
            task_terminal_counts=m._TASK_TERMINAL_COUNTS,
            task_deadline_violations=m._TASK_DEADLINE_VIOLATIONS,
            active_tasks=m._ACTIVE_TASKS,
            active_schedule_tasks=m._ACTIVE_SCHEDULE_TASKS,
            window_last_state=m._WINDOW_LAST_STATE,
            last_diagnostic_at=m._LAST_DIAGNOSTIC_AT,
            bootstrap_ready=bool(m._bootstrap_ready),
            bootstrap_lease_id=m._bootstrap_lease_id,
            bootstrap_lease_ttl_sec=int(m._bootstrap_lease_ttl_sec),
            bootstrap_poll_interval_sec=int(m._bootstrap_poll_interval_sec),
            bootstrap_next_attempt_at=m._bootstrap_next_attempt_at,
            bootstrap_next_heartbeat_at=m._bootstrap_next_heartbeat_at,
            bootstrap_lease_expires_at=m._bootstrap_lease_expires_at,
            bootstrap_retry_idx=int(m._bootstrap_retry_idx),
            leader_conn=m._leader_conn,
            leader_active=bool(m._leader_active),
            leader_next_attempt_at=m._leader_next_attempt_at,
            leader_next_healthcheck_at=m._leader_next_healthcheck_at,
        )

    def apply_to_module(self, m: Any) -> None:
        if m._LAST_SCHEDULE_CHECKS is not self.last_schedule_checks:
            m._LAST_SCHEDULE_CHECKS.clear()
            m._LAST_SCHEDULE_CHECKS.update(self.last_schedule_checks)
        if m._LOADED_ZONE_CURSORS is not self.loaded_zone_cursors:
            m._LOADED_ZONE_CURSORS.clear()
            m._LOADED_ZONE_CURSORS.update(self.loaded_zone_cursors)
        if m._TASK_TERMINAL_COUNTS is not self.task_terminal_counts:
            m._TASK_TERMINAL_COUNTS.clear()
            m._TASK_TERMINAL_COUNTS.update(self.task_terminal_counts)
        if m._TASK_DEADLINE_VIOLATIONS is not self.task_deadline_violations:
            m._TASK_DEADLINE_VIOLATIONS.clear()
            m._TASK_DEADLINE_VIOLATIONS.update(self.task_deadline_violations)
        if m._ACTIVE_TASKS is not self.active_tasks:
            m._ACTIVE_TASKS.clear()
            m._ACTIVE_TASKS.update(self.active_tasks)
        if m._ACTIVE_SCHEDULE_TASKS is not self.active_schedule_tasks:
            m._ACTIVE_SCHEDULE_TASKS.clear()
            m._ACTIVE_SCHEDULE_TASKS.update(self.active_schedule_tasks)
        if m._WINDOW_LAST_STATE is not self.window_last_state:
            m._WINDOW_LAST_STATE.clear()
            m._WINDOW_LAST_STATE.update(self.window_last_state)
        if m._LAST_DIAGNOSTIC_AT is not self.last_diagnostic_at:
            m._LAST_DIAGNOSTIC_AT.clear()
            m._LAST_DIAGNOSTIC_AT.update(self.last_diagnostic_at)

        m._bootstrap_ready = self.bootstrap_ready
        m._bootstrap_lease_id = self.bootstrap_lease_id
        m._bootstrap_lease_ttl_sec = self.bootstrap_lease_ttl_sec
        m._bootstrap_poll_interval_sec = self.bootstrap_poll_interval_sec
        m._bootstrap_next_attempt_at = self.bootstrap_next_attempt_at
        m._bootstrap_next_heartbeat_at = self.bootstrap_next_heartbeat_at
        m._bootstrap_lease_expires_at = self.bootstrap_lease_expires_at
        m._bootstrap_retry_idx = self.bootstrap_retry_idx

        m._leader_conn = self.leader_conn
        m._leader_active = self.leader_active
        m._leader_next_attempt_at = self.leader_next_attempt_at
        m._leader_next_healthcheck_at = self.leader_next_healthcheck_at
