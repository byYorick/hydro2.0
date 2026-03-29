"""
Единый словарь типов алертов для системы hydro2.0.
Стандартизирует source и code для всех алертов.
"""
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from .db import fetch
from .alert_publisher import AlertPublisher

_publisher = AlertPublisher()
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


class AlertSource(str, Enum):
    """Источник алерта: бизнес или инфраструктура."""
    BIZ = "biz"  # Бизнес-алерты (pH, EC, no_flow, overcurrent, etc.)
    INFRA = "infra"  # Инфраструктурные алерты (MQTT down, DB unreachable, etc.)


class AlertCode(str, Enum):
    """Коды алертов."""
    # Бизнес-алерты
    BIZ_NO_FLOW = "biz_no_flow"
    BIZ_OVERCURRENT = "biz_overcurrent"
    BIZ_DRY_RUN = "biz_dry_run"
    BIZ_PUMP_STUCK_ON = "biz_pump_stuck_on"
    BIZ_HIGH_PH = "biz_high_ph"
    BIZ_LOW_PH = "biz_low_ph"
    BIZ_HIGH_EC = "biz_high_ec"
    BIZ_LOW_EC = "biz_low_ec"
    BIZ_HIGH_TEMP = "biz_high_temp"
    BIZ_LOW_TEMP = "biz_low_temp"
    BIZ_HIGH_HUMIDITY = "biz_high_humidity"
    BIZ_LOW_HUMIDITY = "biz_low_humidity"
    BIZ_LIGHT_FAILURE = "biz_light_failure"
    BIZ_NODE_OFFLINE = "biz_node_offline"
    BIZ_CONFIG_ERROR = "biz_config_error"
    
    # Инфраструктурные алерты
    INFRA_MQTT_DOWN = "infra_mqtt_down"
    INFRA_DB_UNREACHABLE = "infra_db_unreachable"
    INFRA_SERVICE_DOWN = "infra_service_down"
    INFRA_FRESHNESS_CHECK_FAILED = "infra_freshness_check_failed"


async def create_alert(
    zone_id: Optional[int],
    source: str,
    code: str,
    type: str,
    details: Optional[Dict[str, Any]] = None,
    suppression_window_sec: Optional[int] = None
):
    """
    Создать или обновить алерт в БД с дедупликацией.
    
    Ключ идемпотентности: (zone_id, code, status='ACTIVE')
    
    Логика:
    - Если активный алерт с таким (zone_id, code) уже существует:
      - Увеличивает details.count на 1
      - Обновляет details.last_seen_at на текущее время
      - Если suppression_window_sec указан и last_seen_at был недавно (в пределах окна),
        обновление не происходит (подавление)
    - Если алерт не найден:
      - Создает новый алерт с details.count=1 и details.last_seen_at=текущее время
    
    Args:
        zone_id: ID зоны (может быть None для глобальных алертов)
        source: Источник алерта (biz или infra)
        code: Код алерта (biz_no_flow, infra_mqtt_down и т.д.)
        type: Человекочитаемый тип алерта (для обратной совместимости)
        details: Дополнительные детали (JSON). При обновлении существующего алерта
                 текущие details сохраняются, добавляются/обновляются только count и last_seen_at
        suppression_window_sec: Опциональное окно подавления в секундах.
                                Если указано, то повторные алерты в пределах этого окна
                                после last_seen_at будут проигнорированы
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    
    payload_details = details.copy() if details else {}
    dedupe_key = _resolve_dedupe_key(zone_id=zone_id, source=source, code=code, details=payload_details)
    payload_details["last_seen_at"] = now_iso
    payload_details.setdefault("dedupe_key", dedupe_key)

    if suppression_window_sec is not None:
        existing = await _fetch_active_alert(zone_id=zone_id, code=code, dedupe_key=dedupe_key)
        if existing is not None:
            existing_details = existing.get("details")
            if isinstance(existing_details, dict):
                last_seen_at_str = existing_details.get("last_seen_at")
                if last_seen_at_str:
                    try:
                        last_seen_at_str_clean = str(last_seen_at_str).replace('Z', '+00:00')
                        last_seen_at = datetime.fromisoformat(last_seen_at_str_clean)
                        if last_seen_at.tzinfo is None:
                            last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
                        if (now - last_seen_at).total_seconds() < suppression_window_sec:
                            return
                    except (ValueError, TypeError, AttributeError):
                        pass

    await _publisher.raise_active(
        zone_id=zone_id,
        source=source,
        code=code,
        alert_type=type,
        details=payload_details,
        dedupe_key=dedupe_key,
        scoped=True,
    )


async def _fetch_active_alert(zone_id: Optional[int], code: str, dedupe_key: str) -> Optional[Dict[str, Any]]:
    rows = await fetch(
        """
        SELECT id, details
        FROM alerts
        WHERE zone_id IS NOT DISTINCT FROM $1
          AND code = $2
          AND status = 'ACTIVE'
          AND COALESCE(details->>'dedupe_key', '') = $3
        LIMIT 1
        """,
        zone_id,
        code,
        dedupe_key,
    )
    return rows[0] if rows else None


def _resolve_dedupe_key(zone_id: Optional[int], source: str, code: str, details: Dict[str, Any]) -> str:
    explicit = str(details.get("dedupe_key") or "").strip()
    if explicit:
        return explicit

    parts = []
    for key in _DEDUPE_SCOPE_KEYS:
        value = details.get(key)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized == "":
            continue
        parts.append(f"{key}:{normalized}")

    return _publisher.build_dedupe_key(
        code=code,
        zone_id=zone_id,
        parts=(source, *parts),
    )
