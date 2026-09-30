"""Единственный выход сбоя и паузы политики AE4."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from common.biz_alerts import send_biz_alert
from common.db import create_zone_event

logger = logging.getLogger(__name__)

_FAILURE_EVENT_TYPE = "AE4_TASK_FAILED"
_DECISION_EVENT_TYPE = "AE4_PLANTING_DECISION"
_STATE_DETAILS_EVENT_TYPE = "AE4_STATE_DETAILS"


async def report_failure(
    *,
    zone_id: int,
    reason_code: str,
    human_message: str,
    grow_cycle_id: Optional[int] = None,
    task_id: Optional[int] = None,
    error_code: Optional[str] = None,
    details: Optional[Mapping[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> None:
    """Сбой §2.4: журнал, zone_events, biz_alert, state_details.failed=true."""
    code = str(error_code or reason_code).strip() or "ae4_task_failed"
    message = str(human_message or "").strip() or "Сбой задачи автоматики"
    payload: dict[str, Any] = {
        "reason_code": reason_code,
        "error_code": code,
        "human_error_message": message,
        "failed": True,
        "grow_cycle_id": grow_cycle_id,
        "task_id": task_id,
    }
    if details:
        payload.update(dict(details))

    logger.error(
        "AE4 сбой: %s",
        message,
        extra={
            "zone_id": zone_id,
            "grow_cycle_id": grow_cycle_id,
            "reason_code": reason_code,
            "task_id": task_id,
            "error_code": code,
        },
    )

    await create_zone_event(zone_id, _FAILURE_EVENT_TYPE, payload)
    await _write_state_details(
        zone_id=zone_id,
        failed=True,
        error_code=code,
        human_error_message=message,
        reason_code=reason_code,
        task_id=task_id,
        grow_cycle_id=grow_cycle_id,
    )

    alert_dedupe = str(dedupe_key or f"ae4-fail:{zone_id}:{reason_code}").strip()
    try:
        await send_biz_alert(
            code=code,
            message=message,
            zone_id=zone_id,
            alert_type="AE4 Failure",
            severity="critical",
            details=payload,
            dedupe_key=alert_dedupe,
        )
    except Exception:
        # Сбой шага алерта не стирает текст журнала и state_details (E240).
        logger.exception(
            "AE4: не удалось отправить biz_alert",
            extra={
                "zone_id": zone_id,
                "reason_code": reason_code,
                "dedupe_key": alert_dedupe,
            },
        )


async def report_critical_call(
    *,
    zone_id: int,
    reason_code: str,
    human_message: str,
    grow_cycle_id: Optional[int] = None,
    details: Optional[Mapping[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> None:
    """Критический вызов §11.6 без failed=true. Повтор reason_code — без события и без вызова."""
    message = str(human_message or "").strip() or "Критический вызов автоматики"
    code = str(reason_code or "").strip() or "ae4_critical"
    previous = await _load_latest_failure_event(zone_id=zone_id, reason_code=code)
    if previous is not None:
        return

    payload: dict[str, Any] = {
        "reason_code": code,
        "error_code": code,
        "human_error_message": message,
        "failed": False,
        "grow_cycle_id": grow_cycle_id,
        "critical_call": True,
    }
    if details:
        payload.update(dict(details))

    logger.error(
        "AE4 критический вызов: %s",
        message,
        extra={"zone_id": zone_id, "reason_code": code, "grow_cycle_id": grow_cycle_id},
    )
    await create_zone_event(zone_id, _FAILURE_EVENT_TYPE, payload)
    await _send_critical_alert(
        zone_id=zone_id,
        code=code,
        message=message,
        payload=payload,
        dedupe_key=dedupe_key,
    )


async def _send_critical_alert(
    *,
    zone_id: int,
    code: str,
    message: str,
    payload: Mapping[str, Any],
    dedupe_key: Optional[str],
) -> None:
    alert_dedupe = str(dedupe_key or f"ae4-critical:{zone_id}:{code}").strip()
    try:
        await send_biz_alert(
            code=code,
            message=message,
            zone_id=zone_id,
            alert_type="AE4 Critical",
            severity="critical",
            details=dict(payload),
            dedupe_key=alert_dedupe,
        )
    except Exception:
        logger.exception(
            "AE4: не удалось отправить критический вызов",
            extra={"zone_id": zone_id, "reason_code": code, "dedupe_key": alert_dedupe},
        )


async def _load_latest_failure_event(
    *,
    zone_id: int,
    reason_code: str,
) -> Optional[dict[str, Any]]:
    from common.db import fetch

    rows = await fetch(
        """
        SELECT payload_json
        FROM zone_events
        WHERE zone_id = $1
          AND type = $2
        ORDER BY created_at DESC, id DESC
        LIMIT 20
        """,
        zone_id,
        _FAILURE_EVENT_TYPE,
    )
    for row in rows:
        payload = row.get("payload_json")
        if not isinstance(payload, dict):
            continue
        if str(payload.get("reason_code") or "") == reason_code:
            return dict(payload)
    return None


async def report_exception(
    *,
    zone_id: int,
    reason_code: str,
    human_message: str,
    exc: BaseException,
    grow_cycle_id: Optional[int] = None,
    task_id: Optional[int] = None,
) -> None:
    """Сбой из необработанного исключения."""
    logger.exception(
        "AE4 исключение: %s",
        human_message,
        extra={
            "zone_id": zone_id,
            "grow_cycle_id": grow_cycle_id,
            "reason_code": reason_code,
            "task_id": task_id,
        },
    )
    await report_failure(
        zone_id=zone_id,
        reason_code=reason_code,
        human_message=human_message,
        grow_cycle_id=grow_cycle_id,
        task_id=task_id,
        error_code=reason_code,
        details={"exception_type": type(exc).__name__, "exception": str(exc)},
    )


async def report_planting_decision(
    *,
    zone_id: int,
    reason_code: str,
    human_message: str,
    grow_cycle_id: Optional[int] = None,
    create_alert: bool = False,
    alert_dedupe_key: Optional[str] = None,
) -> None:
    """Пауза/решение политики: failed=false. Повтор reason_code не пишет новое событие."""
    message = str(human_message or "").strip()
    previous = await load_latest_planting_decision(zone_id=zone_id)
    if previous is not None and previous.get("reason_code") == reason_code:
        return
    payload = {
        "reason_code": reason_code,
        "human_message": message,
        "failed": False,
        "grow_cycle_id": grow_cycle_id,
    }
    await create_zone_event(zone_id, _DECISION_EVENT_TYPE, payload)
    await _write_state_details(
        zone_id=zone_id,
        failed=False,
        error_code=None,
        human_error_message=None,
        reason_code=reason_code,
        planting_message=message,
        grow_cycle_id=grow_cycle_id,
    )
    if not create_alert:
        return
    try:
        await send_biz_alert(
            code=reason_code,
            message=message,
            zone_id=zone_id,
            alert_type="AE4 Policy Pause",
            severity=(
                "critical" if reason_code == "solution_not_ready" else "warning"
            ),
            details=payload,
            dedupe_key=str(
                alert_dedupe_key or f"ae4-pause:{zone_id}:{reason_code}"
            ).strip(),
        )
    except Exception:
        logger.exception(
            "AE4: не удалось отправить алерт паузы",
            extra={"zone_id": zone_id, "reason_code": reason_code},
        )


async def _write_state_details(
    *,
    zone_id: int,
    failed: bool,
    error_code: Optional[str],
    human_error_message: Optional[str],
    reason_code: str,
    task_id: Optional[int] = None,
    grow_cycle_id: Optional[int] = None,
    planting_message: Optional[str] = None,
) -> None:
    """Пишет снимок state_details / решения посадки в zone_events."""
    payload: dict[str, Any] = {
        "failed": bool(failed),
        "error_code": error_code,
        "human_error_message": human_error_message,
        "reason_code": reason_code,
        "task_id": task_id,
        "grow_cycle_id": grow_cycle_id,
        "planting_decision": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not failed and planting_message:
        payload["planting_decision"] = {
            "reason_code": reason_code,
            "human_message": planting_message,
            "failed": False,
        }
    await create_zone_event(zone_id, _STATE_DETAILS_EVENT_TYPE, payload)


async def load_latest_state_overlay(*, zone_id: int) -> dict[str, Any]:
    """Читает последний снимок для ответа /zones/{id}/state."""
    from common.db import fetch

    rows = await fetch(
        """
        SELECT payload_json
        FROM zone_events
        WHERE zone_id = $1
          AND type = $2
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        zone_id,
        _STATE_DETAILS_EVENT_TYPE,
    )
    if not rows:
        return {}
    payload = rows[0].get("payload_json")
    return dict(payload) if isinstance(payload, dict) else {}


async def load_latest_planting_decision(*, zone_id: int) -> Optional[dict[str, Any]]:
    from common.db import fetch

    rows = await fetch(
        """
        SELECT payload_json
        FROM zone_events
        WHERE zone_id = $1
          AND type = $2
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        zone_id,
        _DECISION_EVENT_TYPE,
    )
    if not rows:
        return None
    payload = rows[0].get("payload_json")
    if not isinstance(payload, dict):
        return None
    return {
        "reason_code": str(payload.get("reason_code") or ""),
        "human_message": str(payload.get("human_message") or ""),
        "failed": False,
    }


__all__ = [
    "report_failure",
    "report_critical_call",
    "report_exception",
    "report_planting_decision",
    "load_latest_state_overlay",
    "load_latest_planting_decision",
]
