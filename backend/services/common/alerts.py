"""
Единый словарь типов алертов для системы hydro2.0.
Стандартизирует source и code для всех алертов.
"""
from enum import Enum
from typing import Optional, Dict, Any

from .db import execute
import json


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


async def create_alert(
    zone_id: Optional[int],
    source: str,
    code: str,
    type: str,
    details: Optional[Dict[str, Any]] = None
):
    """
    Создать алерт в БД.
    
    Args:
        zone_id: ID зоны (может быть None для глобальных алертов)
        source: Источник алерта (biz или infra)
        code: Код алерта (biz_no_flow, infra_mqtt_down и т.д.)
        type: Человекочитаемый тип алерта (для обратной совместимости)
        details: Дополнительные детали (JSON)
    """
    details_json = json.dumps(details) if details else None
    await execute(
        """
        INSERT INTO alerts (zone_id, source, code, type, details, status, created_at)
        VALUES ($1, $2, $3, $4, $5, 'ACTIVE', NOW())
        """,
        zone_id, source, code, type, details_json
    )

