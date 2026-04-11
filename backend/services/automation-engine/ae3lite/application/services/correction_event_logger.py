"""CorrectionEventLogger — enrichment and writing of zone_events for correction cycles.

Extracted from ``CorrectionHandler`` as part of the God-Object decomposition
(audit finding B1). Owns the single enrichment pipeline that was previously
scattered across ``_log_correction_event``, ``_event_snapshot_context``,
``_correction_window_id`` and ``_observe_seq``.

The logger accepts two callables via DI:

* ``create_event_fn`` — async writer into ``zone_events`` (typically the
  module-level ``create_zone_event`` from ``common.db``). Injectable so unit
  tests can observe payloads without touching the database.
* ``probe_snapshot_context_fn`` — bound method from ``BaseStageHandler`` that
  reads the probe snapshot context for causal-event linkage. Passed as a
  callable rather than inheriting from the base handler so the logger stays
  independent of handler internals.

All enrichment rules (task_id / stage / topology / correction_window_id /
caused_by_event_id) are preserved one-for-one so existing event-consumers
(frontend Correction Timeline, analytics) see identical payloads.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping, Optional

from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.domain.entities.workflow_state import CorrectionState

_logger = logging.getLogger(__name__)


CreateEventFn = Callable[[int, str, Mapping[str, Any]], Awaitable[None]]
ProbeSnapshotContextFn = Callable[..., Optional[Mapping[str, Any]]]


class CorrectionEventLogger:
    """Enriches and persists ``zone_events`` rows for correction cycle steps."""

    def __init__(
        self,
        *,
        create_event_fn: CreateEventFn,
        probe_snapshot_context_fn: ProbeSnapshotContextFn,
    ) -> None:
        self._create_event = create_event_fn
        self._probe_snapshot_context = probe_snapshot_context_fn

    async def log(
        self,
        *,
        zone_id: int,
        event_type: str,
        task: Any | None = None,
        corr: CorrectionState | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        """Enrich ``payload`` and append a zone event.

        Swallows write errors with a WARNING log — by design, correction cycle
        progress must not be blocked by a transient telemetry-sink failure.
        """
        event_payload: dict[str, Any] = with_runtime_event_contract(payload)
        if task is not None:
            self._enrich_with_task(event_payload=event_payload, task=task, corr=corr)
        if corr is not None:
            self._enrich_with_correction(event_payload=event_payload, corr=corr)
        try:
            await self._create_event(zone_id, event_type, event_payload)
        except Exception:
            _logger.warning("Не удалось записать zone event %s", event_type, exc_info=True)

    # ── Pure static helpers ─────────────────────────────────────────

    @staticmethod
    def correction_window_id(*, task: Any | None) -> str | None:
        """Canonical causal-context id for UI correlation.

        Form: ``task:{task_id}:{workflow_phase}:{stage}``. Returns ``None``
        when any component is missing, so callers can safely ``if cid:``.
        """
        if task is None:
            return None
        task_id = getattr(task, "id", None)
        if task_id is None:
            return None
        stage = str(getattr(task, "current_stage", "") or "").strip()
        workflow = getattr(task, "workflow", None)
        workflow_phase = str(getattr(workflow, "workflow_phase", "") or "").strip()
        if not stage or not workflow_phase:
            return None
        return f"task:{int(task_id)}:{workflow_phase}:{stage}"

    @staticmethod
    def observe_seq(
        *, corr: CorrectionState, pid_type: str, after_dose: bool = False,
    ) -> int | None:
        """Sequence index for observation events, 1-based.

        ``after_dose=True`` adds +1 so the event emitted right after a dose
        gets the index of the observation it triggered.
        """
        current = corr.ec_attempt if pid_type == "ec" else corr.ph_attempt
        observe_seq = int(current) + (1 if after_dose else 0)
        return observe_seq if observe_seq > 0 else None

    @staticmethod
    def serialize_metric_ts(value: Any) -> str | None:
        """Isoformat a timestamp for inclusion in event payloads; tz-aware."""
        if isinstance(value, datetime):
            normalized = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return normalized.isoformat()
        return None

    # ── Enrichment steps ────────────────────────────────────────────

    def _enrich_with_task(
        self,
        *,
        event_payload: dict[str, Any],
        task: Any,
        corr: CorrectionState | None,
    ) -> None:
        task_id = getattr(task, "id", None)
        stage = str(getattr(task, "current_stage", "") or "").strip()
        workflow = getattr(task, "workflow", None)
        workflow_phase = str(getattr(workflow, "workflow_phase", "") or "").strip()
        stage_entered_at = self.serialize_metric_ts(getattr(workflow, "stage_entered_at", None))
        topology = str(getattr(task, "topology", "") or "").strip()

        if task_id is not None:
            event_payload.setdefault("task_id", int(task_id))
        if stage:
            event_payload.setdefault("stage", stage)
            event_payload.setdefault("current_stage", stage)
        if workflow_phase:
            event_payload.setdefault("workflow_phase", workflow_phase)

        window_id = self.correction_window_id(task=task)
        if window_id:
            event_payload.setdefault("correction_window_id", window_id)
        if stage_entered_at:
            event_payload.setdefault("stage_entered_at", stage_entered_at)
        if topology:
            event_payload.setdefault("topology", topology)

        snapshot_ctx = self._build_snapshot_context(task=task, corr=corr)
        if isinstance(snapshot_ctx, Mapping):
            snapshot_event_id = snapshot_ctx.get("snapshot_event_id")
            if snapshot_event_id is not None:
                event_payload.setdefault("caused_by_event_id", snapshot_event_id)
            for key, value in snapshot_ctx.items():
                event_payload.setdefault(key, value)

    @staticmethod
    def _enrich_with_correction(
        *,
        event_payload: dict[str, Any],
        corr: CorrectionState,
    ) -> None:
        if corr.corr_step:
            event_payload.setdefault("corr_step", corr.corr_step)
        event_payload.setdefault("attempt", corr.attempt)
        event_payload.setdefault("ec_attempt", corr.ec_attempt)
        event_payload.setdefault("ph_attempt", corr.ph_attempt)
        event_payload.setdefault("ec_max_attempts", corr.ec_max_attempts)
        event_payload.setdefault("ph_max_attempts", corr.ph_max_attempts)

    def _build_snapshot_context(
        self,
        *,
        task: Any,
        corr: CorrectionState | None,
    ) -> Mapping[str, Any] | None:
        """Resolve the causal-context block used for UI event correlation.

        Priority: explicit probe_snapshot_context (live measurement) over
        the correction-state snapshot (captured at correction window start).
        """
        probe_ctx = self._probe_snapshot_context(task=task)
        if isinstance(probe_ctx, Mapping) and probe_ctx:
            return probe_ctx
        if corr is None:
            return None

        created_at = (
            corr.snapshot_created_at.isoformat()
            if isinstance(corr.snapshot_created_at, datetime)
            else None
        )
        cmd_id = str(corr.snapshot_cmd_id or "").strip() or None
        source_event_type = str(corr.snapshot_source_event_type or "").strip() or None
        event_id = corr.snapshot_event_id if isinstance(corr.snapshot_event_id, int) else None
        context = {
            "snapshot_event_id": event_id if event_id and event_id > 0 else None,
            "snapshot_created_at": created_at,
            "snapshot_cmd_id": cmd_id,
            "snapshot_source_event_type": source_event_type,
        }
        filtered = {key: value for key, value in context.items() if value is not None}
        return filtered or None
