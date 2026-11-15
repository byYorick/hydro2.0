"""Dose feedback/calibration helpers and post-persistence accounting markers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Sequence

from ae3lite.domain.services.correction_planner import resolve_dose_feedback_from_response


def ml_per_sec_for_actuator(actuator: Any) -> float:
    if not isinstance(actuator, Mapping):
        return 0.0
    calibration = actuator.get("calibration")
    if not isinstance(calibration, Mapping):
        return 0.0
    try:
        return max(0.0, float(calibration.get("ml_per_sec") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def ml_per_sec_for_ec_item(*, actuators: Mapping[str, Any], item: Mapping[str, Any]) -> float:
    component = str(item.get("component") or "").strip().lower()
    ec_actuators = actuators.get("ec_actuators")
    if component and isinstance(ec_actuators, Mapping):
        actuator = ec_actuators.get(component) or ec_actuators.get(f"ec_{component}")
        ml_per_sec = ml_per_sec_for_actuator(actuator)
        if ml_per_sec > 0.0:
            return ml_per_sec
    return ml_per_sec_for_actuator(actuators.get("ec"))


def response_details_from_batch(
    batch_result: Mapping[str, Any],
    *,
    status_index: int = 0,
) -> Mapping[str, Any]:
    statuses = batch_result.get("command_statuses")
    if not isinstance(statuses, Sequence) or status_index < 0 or status_index >= len(statuses):
        return {}
    item = statuses[status_index]
    if not isinstance(item, Mapping):
        return {}
    details = item.get("response_details")
    return details if isinstance(details, Mapping) else {}


def resolve_dose_outcome(
    *,
    planned_ml: float,
    planned_duration_ms: int,
    ml_per_sec: float,
    batch_result: Mapping[str, Any],
    status_index: int = 0,
) -> tuple[float, int, bool]:
    return resolve_dose_feedback_from_response(
        planned_ml=planned_ml,
        planned_duration_ms=planned_duration_ms,
        ml_per_sec=ml_per_sec,
        response_details=response_details_from_batch(batch_result, status_index=status_index),
    )


async def mark_accounted_dose_commands(
    *,
    batch_result: Mapping[str, Any],
    now: datetime,
    mark_dose_accounted: Callable[..., Awaitable[Any]] | None,
    logger: Any,
) -> None:
    """Маркер учёта дозы — только после успешного PID persist этого шага.

    Startup больше не подхватывает ту же DONE-команду. Ошибка маркера не
    откатывает уже записанный PID: строка останется в выборке repair.
    """
    if not callable(mark_dose_accounted):
        return
    statuses = batch_result.get("command_statuses")
    if not isinstance(statuses, Sequence) or isinstance(statuses, (str, bytes)):
        return
    for status in statuses:
        if not isinstance(status, Mapping):
            continue
        command_id = status.get("ae_command_id")
        if command_id is None:
            continue
        cmd = str(status.get("cmd") or "dose").strip().lower()
        if cmd != "dose":
            continue
        terminal = str(status.get("terminal_status") or "").strip().upper()
        if terminal != "DONE":
            continue
        try:
            await mark_dose_accounted(ae_command_id=int(command_id), now=now)
        except Exception:
            logger.warning(
                "AE3 не записал маркер учёта дозы ae_command_id=%s",
                command_id,
                exc_info=True,
            )
