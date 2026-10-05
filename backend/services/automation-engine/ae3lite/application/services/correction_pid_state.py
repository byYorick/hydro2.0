"""PID persistence граница коррекции: clocks, I/D и fail-closed reset."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.services.correction_event_logger import CorrectionEventLogger
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.correction_planner import DosePlan
from ae3lite.infrastructure.metrics import CORRECTION_NO_EFFECT_RESET_FAILED

_logger = logging.getLogger(__name__)
_PID_RESET_ATTEMPTS = 2


class CorrectionPidState:
    def __init__(self, *, repository: Any, event_logger: CorrectionEventLogger) -> None:
        self._repository = repository
        self._event_logger = event_logger

    async def read_measurement_for_event(self, *, zone_id: int, pid_type: str) -> float | None:
        """Best-effort event enrichment; не используется для принятия решения о дозе."""
        if self._repository is None:
            return None
        try:
            return await self._repository.read_measured_value(zone_id=zone_id, pid_type=pid_type)
        except Exception:
            _logger.debug("Не удалось прочитать %s pid_state для события", pid_type, exc_info=True)
            return None

    async def clear_feedforward_bias(self, *, zone_id: int) -> None:
        if self._repository is not None:
            await self._repository.clear_feedforward_bias(zone_id=zone_id)

    @staticmethod
    def select_updates(
        *,
        dose_plan: DosePlan,
        selected_action: str,
    ) -> dict[str, Any]:
        """Commit plan PID I/D only for the controller about to dose.

        Peer controller (pending dual EC+PH) gets a measurement-clock touch
        without integral / prev_* — equivalent to ``accumulate_integral=False``
        so hold/observe of the active dose cannot wind up the pending loop.
        """
        raw = dose_plan.pid_state_updates
        if not isinstance(raw, Mapping):
            return {}

        def _clock_touch(entry: Mapping[str, Any]) -> dict[str, Any]:
            touch: dict[str, Any] = {}
            if "last_measurement_at" in entry:
                touch["last_measurement_at"] = entry["last_measurement_at"]
            if "last_measured_value" in entry:
                touch["last_measured_value"] = entry["last_measured_value"]
            # Sync D/prev without committing peer integral (full freeze contract).
            if "prev_error" in entry:
                touch["prev_error"] = entry["prev_error"]
            if "prev_derivative" in entry:
                touch["prev_derivative"] = entry["prev_derivative"]
            return touch

        out: dict[str, Any] = {}
        action = str(selected_action or "").strip().lower()
        if action == "ec":
            ec = raw.get("ec")
            if isinstance(ec, Mapping):
                out["ec"] = dict(ec)
            if (dose_plan.needs_ph_up or dose_plan.needs_ph_down):
                ph = raw.get("ph")
                if isinstance(ph, Mapping):
                    touch = _clock_touch(ph)
                    if touch:
                        out["ph"] = touch
        elif action in {"ph_up", "ph_down", "ph"}:
            ph = raw.get("ph")
            if isinstance(ph, Mapping):
                out["ph"] = dict(ph)
            if dose_plan.needs_ec:
                ec = raw.get("ec")
                if isinstance(ec, Mapping):
                    touch = _clock_touch(ec)
                    if touch:
                        out["ec"] = touch
        return out


    async def touch_measurement_clock(
        self,
        *,
        zone_id: int,
        now: datetime,
        current_ph: float,
        current_ec: float,
    ) -> None:
        """Advance last_measurement_at without committing plan integral (discard retry)."""
        if self._repository is None:
            return
        await self.persist(
            zone_id=zone_id,
            now=now,
            updates={
                "ec": {
                    "last_measurement_at": now,
                    "last_measured_value": round(float(current_ec), 6),
                    "prev_derivative": 0.0,
                },
                "ph": {
                    "last_measurement_at": now,
                    "last_measured_value": round(float(current_ph), 6),
                    "prev_derivative": 0.0,
                },
            },
        )


    async def reset_no_effect_counts(
        self,
        *,
        task: Any,
        corr: CorrectionState,
        context: str,
    ) -> None:
        """Reset no_effect_count with one retry; fail-closed on persistent error.

        Stale ``no_effect_count`` can block later corrections via alert-block
        policy — silently swallowing the failure leaves the zone stuck.
        """
        if self._repository is None:
            return
        zone_id = int(task.zone_id)
        last_exc: Exception | None = None
        for attempt in range(1, _PID_RESET_ATTEMPTS + 1):
            try:
                await self._repository.reset_no_effect_counts(zone_id=zone_id)
                return
            except Exception as exc:
                last_exc = exc
                _logger.warning(
                    "Failed to reset no_effect_count (%s) for zone %s attempt=%s",
                    context,
                    zone_id,
                    attempt,
                    exc_info=True,
                )
        CORRECTION_NO_EFFECT_RESET_FAILED.inc()
        try:
            await self._event_logger.log(
                zone_id=zone_id,
                event_type="CORRECTION_NO_EFFECT_RESET_FAILED",
                task=task,
                corr=corr,
                payload={"context": context, "error": str(last_exc) if last_exc else "unknown"},
            )
        except Exception:
            _logger.debug("Failed to emit CORRECTION_NO_EFFECT_RESET_FAILED", exc_info=True)
        raise TaskExecutionError(
            "corr_no_effect_reset_failed",
            f"Не удалось сбросить no_effect_count для зоны {zone_id} ({context})",
        ) from last_exc


    async def persist(
        self,
        *,
        zone_id: Any,
        updates: Mapping[str, Any],
        now: datetime,
    ) -> None:
        """Persist PID state updates (integral, prev_error, etc.) to the DB.

        Plan I/D updates are committed from ``_finalize_dose_plan_routing`` only
        after dose routing is confirmed (not on flow_hold / discard / cooldown).
        Observe finalize writes ``last_measurement_at`` without ΔI — equivalent
        to ``accumulate_integral=False`` for hold/observe dead time.
        ``last_dose_at`` is written only after terminal DONE in dose steps.
        No-op if no repository is wired or the update dict is empty.
        """
        if not updates or self._repository is None:
            return
        try:
            await self._repository.upsert_states(
                zone_id=int(zone_id),
                now=now,
                updates=[
                    {"pid_type": pid_type, **state_dict}
                    for pid_type, state_dict in updates.items()
                ],
            )
        except Exception:
            raise TaskExecutionError(
                "corr_pid_state_persist_failed",
                f"Не удалось сохранить PID state для зоны {zone_id}",
            )

