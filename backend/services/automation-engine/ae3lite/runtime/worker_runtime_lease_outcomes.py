"""Ae3RuntimeWorker lease outcomes: explicit collaborators and invocation context."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from ae3lite.runtime.worker_runtime_state import WorkerRuntimeState


@dataclass(frozen=True)
class WorkerRuntimeLeaseOutcomesPorts:
    lease_release_resolve_started_monotonic: Callable[[], Any]
    lease_release_resolve_ttl_sec: Callable[[], Any]
    log_debug: Callable[..., Any]
    logger: Callable[[], Any]
    now_fn: Callable[..., Any]
    owner: Callable[[], Any]
    global_send_infra_resolved_alert: Callable[..., Any]


class WorkerRuntimeLeaseOutcomes:
    def __init__(self, ports: WorkerRuntimeLeaseOutcomesPorts, state: WorkerRuntimeState) -> None:
        self._ports = ports
        self._state = state

    def should_resolve_zone_lease_release_alert(self, *, zone_id: int) -> bool:
        """Resolve только при known-fail или редком TTL opportunistic (stuck после restart)."""
        if zone_id in self._state.lease_release_fail_zones:
            return True
        ttl = self._ports.lease_release_resolve_ttl_sec()
        if ttl <= 0:
            return False
        warm_up = time.monotonic() - self._ports.lease_release_resolve_started_monotonic()
        if warm_up < float(ttl):
            return False
        last = self._state.lease_release_resolve_attempt_at.get(zone_id)
        if last is None:
            return True
        try:
            age_sec = (self._ports.now_fn() - last).total_seconds()
        except Exception:
            return True
        return age_sec >= float(ttl)

    async def maybe_resolve_zone_lease_release_alert(self, *, task: Any, reason: str) -> None:
        zone_id = int(task.zone_id)
        if not self.should_resolve_zone_lease_release_alert(zone_id=zone_id):
            self._ports.log_debug(
                "AE3 skip lease_release resolve: zone_id=%s reason=%s known_fail=%s",
                zone_id,
                reason,
                zone_id in self._state.lease_release_fail_zones,
            )
            return
        await self.resolve_zone_lease_release_alert(task=task, reason=reason)

    async def resolve_zone_lease_release_alert(self, *, task: Any, reason: str = "released") -> None:
        zone_id = int(task.zone_id)
        now = self._ports.now_fn()
        try:
            await self._ports.global_send_infra_resolved_alert(
                code="ae3_zone_lease_release_failed",
                alert_type="AE3 Zone Lease Release Failed",
                message="После завершения задачи lease зоны больше не присутствует.",
                zone_id=zone_id,
                service="automation-engine",
                component="worker:lease",
                details={
                    "task_id": int(task.id),
                    "owner": self._ports.owner(),
                    "topology": str(getattr(task, "topology", "")),
                    "reason": reason,
                    "message": "После завершения задачи lease зоны больше не присутствует.",
                },
            )
            self._state.lease_release_fail_zones.discard(zone_id)
            self._state.lease_release_resolve_attempt_at[zone_id] = now
        except Exception:
            self._ports.logger().warning(
                "AE3 не смог отправить alert lease_release_resolved zone_id=%s",
                task.zone_id,
                exc_info=True,
            )
