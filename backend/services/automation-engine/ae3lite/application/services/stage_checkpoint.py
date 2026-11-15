"""Stage component: checkpoint. Explicit ports; no handler dependency."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError

_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageCheckpointPorts:
    live_reload_enabled: Callable[[], Any]
    create_zone_event: Callable[..., Awaitable[Any]]


class StageCheckpoint:
    def __init__(self, ports: StageCheckpointPorts) -> None:
        self._ports = ports

    async def checkpoint(self, *, task: Any, plan: Any, now: datetime) -> Any:
        """Phase 5.5: live-mode config hot-swap.

        Returns either the original ``plan`` unchanged (locked / no advance /
        TTL expired) or a *new* ``CommandPlan`` rebuilt from the current zone
        snapshot. Handlers should assign the result back to their local
        ``plan`` variable:

            plan = await self.checkpoint(task=task, plan=plan, now=now)

        Hot-swap is achieved by:
          1. Comparing `zones.config_revision` (DB) against
             `plan.runtime.config_revision` (in-flight)
          2. On advance + LIVE mode: re-loading the zone snapshot
             (`PgZoneSnapshotReadModel().load`) and rebuilding via
             `CycleStartPlanner.build` — same code path as task claim, so
             both `runtime` and `named_plans` stay aligned with config.
          3. Stamping the new revision onto `runtime.config_revision` so
             subsequent checkpoints in the same `run()` don't re-trigger.

        Emits `CONFIG_HOT_RELOADED` zone_event + `ae3_config_hot_reload_total`
        metric on apply. When revision advanced but rebuild fails, fail-closed
        via ``TaskExecutionError`` — task must not continue on stale RuntimePlan.
        """
        from ae3lite.infrastructure.metrics import (
            CONFIG_HOT_RELOAD,
            ZONE_CONFIG_LIVE_EDITS,
            ZONE_CONFIG_MODE,
        )

        runtime = plan.runtime
        if not self._ports.live_reload_enabled():
            return plan

        # Phase 5: compare integer `zones.config_revision` (DB) vs the
        # monotonic counter snapshot read at plan-build time. Do NOT use
        # `bundle_revision` — that's a content hash, not a counter.
        try:
            current_revision = int(getattr(runtime, "config_revision", None) or 0)
        except (TypeError, ValueError):
            current_revision = 0

        zone_id = int(getattr(task, "zone_id", 0) or 0)
        if zone_id <= 0:
            CONFIG_HOT_RELOAD.labels(result="disabled").inc()
            return plan

        try:
            from common.db import get_pool

            pool = await get_pool()
        except Exception:
            _logger.warning("checkpoint: DB pool unavailable, skipping live-reload", exc_info=True)
            CONFIG_HOT_RELOAD.labels(result="error").inc()
            return plan

        # Cheap pre-check: read zone's mode/revision/TTL only.
        try:
            async with pool.acquire() as conn:
                zone_row = await conn.fetchrow(
                    "SELECT config_mode, config_revision, live_until FROM zones WHERE id = $1",
                    zone_id,
                )
        except Exception:
            _logger.warning("checkpoint: zone read failed zone_id=%s", zone_id, exc_info=True)
            CONFIG_HOT_RELOAD.labels(result="error").inc()
            return plan

        from ae3lite.config.modes import ConfigMode

        if zone_row is None:
            CONFIG_HOT_RELOAD.labels(result="no_change").inc()
            return plan
        observed_mode = ConfigMode.parse(zone_row.get("config_mode"))
        # Phase 7 gauge: observer-style publish на каждом checkpoint. Дёшево
        # потому что уже читаем zone row ради revision сравнения.
        try:
            ZONE_CONFIG_MODE.labels(zone_id=str(zone_id)).set(
                1.0 if observed_mode is ConfigMode.LIVE else 0.0,
            )
        except Exception:  # pragma: no cover — metrics exporter issue
            pass
        if observed_mode is not ConfigMode.LIVE:
            CONFIG_HOT_RELOAD.labels(result="no_change").inc()
            return plan
        live_until = zone_row.get("live_until")
        if isinstance(live_until, datetime):
            now_utc = datetime.now(timezone.utc)
            if live_until.tzinfo is None:
                live_until = live_until.replace(tzinfo=timezone.utc)
            if live_until < now_utc:
                CONFIG_HOT_RELOAD.labels(result="no_change").inc()
                return plan
        new_revision = int(zone_row.get("config_revision") or 0)
        if new_revision <= current_revision:
            CONFIG_HOT_RELOAD.labels(result="no_change").inc()
            return plan

        # Revision advanced — rebuild the full CommandPlan via the canonical
        # planner path so runtime *and* named_plans stay aligned with config.
        try:
            from ae3lite.domain.services.cycle_start_planner import CycleStartPlanner
            from ae3lite.infrastructure.read_models.zone_snapshot_read_model import (
                PgZoneSnapshotReadModel,
            )

            snapshot = await PgZoneSnapshotReadModel().load(zone_id=zone_id)
            new_plan = CycleStartPlanner().build(task=task, snapshot=snapshot)
            new_runtime = getattr(new_plan, "runtime", None)
            if new_runtime is None:
                raise TaskExecutionError(
                    ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED,
                    f"config_revision advanced to {new_revision}, но rebuild не вернул RuntimePlan zone_id={zone_id}",
                )
            new_plan = replace(
                new_plan,
                runtime=new_runtime.model_copy(update={"config_revision": int(new_revision)}),
            )
        except TaskExecutionError:
            CONFIG_HOT_RELOAD.labels(result="error").inc()
            raise
        except Exception:
            _logger.warning(
                "checkpoint: snapshot rebuild failed zone_id=%s rev=%s",
                zone_id,
                new_revision,
                exc_info=True,
            )
            CONFIG_HOT_RELOAD.labels(result="error").inc()
            raise TaskExecutionError(
                ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED,
                f"config_revision advanced to {new_revision}, но snapshot rebuild failed zone_id={zone_id}",
            ) from None

        try:
            await self._ports.create_zone_event(
                zone_id,
                "CONFIG_HOT_RELOADED",
                with_runtime_event_contract(
                    {
                        "revision": new_revision,
                        "previous_revision": current_revision,
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "stage": str(getattr(task, "current_stage", "") or ""),
                    }
                ),
            )
        except Exception:
            _logger.warning(
                "checkpoint: failed to emit CONFIG_HOT_RELOADED event zone_id=%s",
                zone_id,
                exc_info=True,
            )

        CONFIG_HOT_RELOAD.labels(result="applied").inc()
        try:
            ZONE_CONFIG_LIVE_EDITS.labels(
                zone_id=str(zone_id),
                handler=str(getattr(task, "current_stage", "") or "unknown"),
            ).inc()
        except Exception:  # pragma: no cover — metrics exporter issue
            pass
        _logger.info(
            "config_hot_reload: applied zone_id=%s rev=%s→%s",
            zone_id,
            current_revision,
            new_revision,
        )
        return new_plan
