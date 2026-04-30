from typing import Optional, Dict, Any, Tuple
from common.alert_publisher import AlertPublisher
from common.biz_alerts import send_biz_alert
from common.db import fetch
from common.alerts import AlertSource, AlertCode


_publisher = AlertPublisher(default_source=AlertSource.BIZ.value)
_DEDUPE_SCOPE_KEYS = (
    "pump_channel",
    "channel",
    "node_uid",
    "hardware_id",
    "component",
    "service",
    "pid_type",
    "error_code",
    "workflow_phase",
    "stage",
    "task_id",
)

# Маппинг старых alert_type на новые (source, code)
ALERT_TYPE_MAPPING: Dict[str, Tuple[str, str]] = {
    'PH_HIGH': (AlertSource.BIZ.value, AlertCode.BIZ_HIGH_PH.value),
    'PH_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_LOW_PH.value),
    'EC_HIGH': (AlertSource.BIZ.value, AlertCode.BIZ_HIGH_EC.value),
    'EC_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_LOW_EC.value),
    'TEMP_HIGH': (AlertSource.BIZ.value, AlertCode.BIZ_HIGH_TEMP.value),
    'TEMP_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_LOW_TEMP.value),
    'HUMIDITY_HIGH': (AlertSource.BIZ.value, AlertCode.BIZ_HIGH_HUMIDITY.value),
    'HUMIDITY_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_LOW_HUMIDITY.value),
    'NO_FLOW': (AlertSource.BIZ.value, AlertCode.BIZ_NO_FLOW.value),
    'WATER_LEVEL_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_DRY_RUN.value),
    'LIGHT_FAILURE': (AlertSource.BIZ.value, AlertCode.BIZ_LIGHT_FAILURE.value),
}


def _get_alert_source_and_code(alert_type: str) -> Tuple[str, str]:
    """
    Получить source и code для alert_type.
    Если маппинга нет, использует дефолтные значения.
    """
    if alert_type in ALERT_TYPE_MAPPING:
        return ALERT_TYPE_MAPPING[alert_type]
    # Дефолт для неизвестных типов
    return (AlertSource.BIZ.value, AlertCode.BIZ_CONFIG_ERROR.value)


def _build_dedupe_key(zone_id: Optional[int], code: str, details: Optional[Dict[str, Any]] = None) -> str:
    payload = details if isinstance(details, dict) else {}
    explicit = str(payload.get("dedupe_key") or "").strip()
    if explicit:
        return explicit

    parts = [f"code_scope:{code}"]
    for key in _DEDUPE_SCOPE_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            parts.append(f"{key}:{normalized}")

    return _publisher.build_dedupe_key(code=code, zone_id=zone_id, parts=parts)


def _alert_message(alert_type: str, details: Dict[str, Any]) -> str:
    for key in ("message", "description"):
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return alert_type


async def ensure_alert(zone_id: int, alert_type: str, details: Dict[str, Any]) -> None:
    """
    Опубликовать intent активного alert-а через Laravel ingest.

    Lifecycle и дедупликацией владеет Laravel AlertService.
    
    Args:
        zone_id: ID зоны
        alert_type: Тип алерта (PH_HIGH, TEMP_LOW, и т.д.)
        details: Детали алерта (JSON-совместимый словарь)
    """
    source, code = _get_alert_source_and_code(alert_type)
    payload = dict(details or {})
    payload.setdefault("legacy_alert_type", alert_type)
    dedupe_key = _build_dedupe_key(zone_id=zone_id, code=code, details=payload)
    payload["dedupe_key"] = dedupe_key

    if source == AlertSource.BIZ.value:
        await send_biz_alert(
            zone_id=zone_id,
            code=code,
            alert_type=alert_type,
            message=_alert_message(alert_type, payload),
            details=payload,
            dedupe_key=dedupe_key,
        )
        return

    await _publisher.raise_active(
        zone_id=zone_id,
        source=source,
        code=code,
        alert_type=alert_type,
        details=payload,
        dedupe_key=dedupe_key,
        scoped=True,
    )


async def resolve_alert(zone_id: int, alert_type: str) -> bool:
    """
    Опубликовать intent закрытия alert-а через Laravel ingest.
    
    Args:
        zone_id: ID зоны
        alert_type: Тип алерта для закрытия
    
    Returns:
        True если intent доставлен сразу, False если он попал в retry-очередь.
    """
    source, code = _get_alert_source_and_code(alert_type)
    details = {
        "legacy_alert_type": alert_type,
        "resolved_via": "automation_engine",
    }
    dedupe_key = _build_dedupe_key(zone_id=zone_id, code=code, details=details)
    details["dedupe_key"] = dedupe_key

    return await _publisher.resolve(
        zone_id=zone_id,
        source=source,
        code=code,
        alert_type=alert_type,
        details=details,
        dedupe_key=dedupe_key,
        scoped=True,
    )


async def find_active_alert(zone_id: int, alert_type: str) -> Optional[Dict[str, Any]]:
    """
    Поиск активного алерта.
    
    Returns:
        Dict с данными алерта или None
    """
    _source, code = _get_alert_source_and_code(alert_type)
    dedupe_key = _build_dedupe_key(zone_id=zone_id, code=code, details={})
    rows = await fetch(
        """
        SELECT id, code, type, details, status, created_at
        FROM alerts
        WHERE zone_id = $1
          AND LOWER(code) = LOWER($2)
          AND status = 'ACTIVE'
          AND COALESCE(details->>'dedupe_key', '') = $3
        LIMIT 1
        """,
        zone_id,
        code,
        dedupe_key,
    )
    
    if rows:
        return {
            'id': rows[0]["id"],
            'code': rows[0]["code"],
            'type': rows[0]["type"],
            'details': rows[0]["details"],
            'status': rows[0]["status"],
            'created_at': rows[0]["created_at"],
        }
    return None
