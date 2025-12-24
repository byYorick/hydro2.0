"""
Единый словарь типов алертов для системы hydro2.0.
Стандартизирует source и code для всех алертов.
"""
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from .db import execute, fetch
from .alert_queue import send_alert_to_laravel
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
    
    # Ищем существующий активный алерт по ключу идемпотентности
    existing = await fetch(
        """
        SELECT id, details
        FROM alerts
        WHERE zone_id IS NOT DISTINCT FROM $1 
          AND code = $2 
          AND status = 'ACTIVE'
        LIMIT 1
        """,
        zone_id, code
    )
    
    if existing:
        alert_id = existing[0]["id"]
        existing_details_raw = existing[0]["details"]
        
        # asyncpg автоматически парсит JSONB в dict, но может быть None
        if isinstance(existing_details_raw, str):
            existing_details = json.loads(existing_details_raw) if existing_details_raw else {}
        elif existing_details_raw is None:
            existing_details = {}
        else:
            existing_details = existing_details_raw
        
        # Проверяем окно подавления, если указано
        if suppression_window_sec is not None:
            last_seen_at_str = existing_details.get("last_seen_at")
            if last_seen_at_str:
                try:
                    # Парсим ISO формат datetime
                    last_seen_at_str_clean = last_seen_at_str.replace('Z', '+00:00')
                    last_seen_at = datetime.fromisoformat(last_seen_at_str_clean)
                    if last_seen_at.tzinfo is None:
                        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
                    
                    time_diff = (now - last_seen_at).total_seconds()
                    if time_diff < suppression_window_sec:
                        # Подавляем алерт - не обновляем
                        return
                except (ValueError, TypeError, AttributeError):
                    # Если не удалось распарсить, продолжаем с обновлением
                    pass
        
        # Обновляем существующий алерт
        # Объединяем существующие details с новыми, добавляем count и last_seen_at
        updated_details = existing_details.copy()
        if details:
            updated_details.update(details)
        
        # Увеличиваем счетчик и обновляем last_seen_at
        current_count = updated_details.get("count", 0)
        updated_details["count"] = current_count + 1
        updated_details["last_seen_at"] = now_iso
        
        details_json = json.dumps(updated_details)
        await execute(
            """
            UPDATE alerts
            SET details = $1
            WHERE id = $2
            """,
            details_json, alert_id
        )
    else:
        # Создаем новый алерт через Laravel API (с автоматической очередью при ошибках)
        new_details = details.copy() if details else {}
        new_details["count"] = 1
        new_details["last_seen_at"] = now_iso
        
        await send_alert_to_laravel(
            zone_id=zone_id,
            source=source,
            code=code,
            type=type,
            status="ACTIVE",
            details=new_details
        )

