"""CorrectionAlertService — централизация business alerts коррекции.

Extracted from ``CorrectionHandler`` as part of the God-Object decomposition
(audit finding B1). Owns the three ``send_biz_alert`` call sites that were
scattered inline across ``_correction_exhausted`` (×2 — generic + irrigation
branch) and ``_no_effect_limit_reached``.

The service swallows transport errors silently with a WARNING log — by
design, correction cycle progress must not be blocked by a degraded alert
pipeline. Handler tests that monkeypatch ``send_biz_alert`` continue to
work because the default wiring routes through a lazy lambda closure
(same pattern used for ``create_zone_event`` in ``CorrectionEventLogger``).

Why a service rather than three free functions:
  * Single injection point — handler holds one reference, tests supply one
    fake, and future alert sinks (Slack, PagerDuty) plug in at one seam.
  * Consistent error handling — one place for the swallow/log pattern.
  * Domain vocabulary — method names describe the business event, not the
    underlying alert shape.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.domain.entities.workflow_state import CorrectionState

_logger = logging.getLogger(__name__)


# Signature matches ``common.biz_alerts.send_biz_alert``. Kept as a Callable
# rather than importing the concrete function so the service can be unit
# tested without touching common.biz_alerts wiring.
AlertSinkFn = Callable[..., Awaitable[Any]]


class CorrectionAlertService:
    """Publishes business alerts for correction cycle outcomes."""

    def __init__(self, *, alert_sink_fn: AlertSinkFn) -> None:
        self._alert_sink = alert_sink_fn

    async def emit_correction_exhausted(
        self,
        *,
        task: Any,
        corr: CorrectionState,
    ) -> None:
        """Generic attempt-exhausted alert.

        Fired whenever the correction loop burned through its attempt
        budget, regardless of stage. The irrigation stage additionally gets
        ``emit_irrigation_correction_exhausted`` so the downstream alert
        consumers can differentiate "normal correction failure" from
        "irrigation that will continue without corrections".
        """
        stage = str(getattr(task, "current_stage", "") or "")
        topology = str(getattr(task, "topology", "") or "")
        await self._safe_emit(
            label="CORRECTION_EXHAUSTED",
            zone_id=int(task.zone_id),
            code="biz_correction_exhausted",
            alert_type="AE3 Correction Exhausted",
            message="Цикл коррекции исчерпал все настроенные попытки.",
            severity="error",
            details={
                "task_id": int(getattr(task, "id", 0) or 0),
                "stage": stage,
                "topology": topology,
                "component": f"correction:{stage}",
                "attempt": corr.attempt,
                "max_attempts": corr.max_attempts,
                "ec_attempt": corr.ec_attempt,
                "ph_attempt": corr.ph_attempt,
                "message": (
                    "Цикл коррекции исчерпал все попытки дозирования, "
                    "проверьте оборудование дозирования pH/EC."
                ),
            },
            scope_parts=(f"stage:{stage}", f"topology:{topology}"),
        )

    async def emit_irrigation_correction_exhausted(
        self,
        *,
        task: Any,
        corr: CorrectionState,
    ) -> None:
        """Irrigation-specific exhausted alert.

        Irrigation stages keep running even after correction exhaustion
        (watering itself is still valuable), so the ops team needs a
        distinct signal to distinguish this path from "stop the cycle".
        """
        stage = str(getattr(task, "current_stage", "") or "")
        topology = str(getattr(task, "topology", "") or "")
        await self._safe_emit(
            label="irrigation_correction_exhausted",
            zone_id=int(task.zone_id),
            code="biz_irrigation_correction_exhausted",
            alert_type="AE3 Irrigation Correction Exhausted",
            message="Коррекция во время полива исчерпала все настроенные попытки.",
            severity="error",
            details={
                "task_id": int(getattr(task, "id", 0) or 0),
                "stage": stage,
                "topology": topology,
                "component": f"correction:{stage}",
                "attempt": corr.attempt,
                "max_attempts": corr.max_attempts,
                "message": (
                    "Коррекция полива исчерпана, полив продолжится без новых "
                    "попыток коррекции на этом этапе."
                ),
            },
            scope_parts=(f"stage:{stage}", f"topology:{topology}"),
        )

    async def emit_no_effect(
        self,
        *,
        task: Any,
        pid_type: str,
        baseline_value: float,
        observed_value: float,
        expected_effect: float,
        actual_effect: float,
        no_effect_limit: int,
    ) -> None:
        """Alert that N consecutive observations showed no measurable reaction.

        ``pid_type`` is expected to be ``"ec"`` or ``"ph"`` — the alert code
        embeds it as ``biz_{pid_type}_correction_no_effect`` so consumers
        can subscribe to EC-only or pH-only no-effect events.
        """
        stage = str(getattr(task, "current_stage", "") or "")
        await self._safe_emit(
            label="CORRECTION_NO_EFFECT",
            zone_id=int(task.zone_id),
            code=f"biz_{pid_type}_correction_no_effect",
            alert_type="AE3 Correction No Effect",
            message=(
                f"Коррекция {pid_type.upper()} не дала наблюдаемого эффекта "
                f"{no_effect_limit} раз подряд."
            ),
            severity="error",
            details={
                "task_id": int(getattr(task, "id", 0) or 0),
                "pid_type": pid_type,
                "stage": stage,
                "component": f"correction:{stage}",
                "baseline_value": baseline_value,
                "observed_value": observed_value,
                "expected_effect": expected_effect,
                "actual_effect": actual_effect,
                "no_effect_limit": no_effect_limit,
            },
            scope_parts=(f"pid_type:{pid_type}", f"stage:{stage}"),
        )

    # ── Private ─────────────────────────────────────────────────────

    async def _safe_emit(
        self,
        *,
        label: str,
        zone_id: int,
        code: str,
        alert_type: str,
        message: str,
        severity: str,
        details: Mapping[str, Any],
        scope_parts: tuple[str, ...],
    ) -> None:
        """Dispatch one alert, log + swallow on transport failure."""
        try:
            await self._alert_sink(
                code=code,
                alert_type=alert_type,
                message=message,
                severity=severity,
                zone_id=zone_id,
                details=dict(details),
                scope_parts=scope_parts,
            )
        except Exception:
            _logger.warning(
                "Не удалось отправить infra alert %s zone_id=%s",
                label,
                zone_id,
            )
