"""
Общий модуль для обработки телеметрии.
Реализует единую точку записи телеметрии через process_telemetry_batch.
"""
import logging
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from .db import execute, upsert_telemetry_last, fetch
from .env import get_settings
from .metrics import normalize_metric_type, UnknownMetricError

logger = logging.getLogger(__name__)


class TelemetrySampleModel(BaseModel):
    """Модель входных данных телеметрии."""
    node_uid: str
    zone_uid: Optional[str] = None  # Может быть zn-{id} или None
    zone_id: Optional[int] = None   # Альтернативно можно передать zone_id напрямую
    metric_type: str
    value: float
    ts: Optional[datetime] = None
    raw: Optional[dict] = None
    channel: Optional[str] = None


def _normalize_metric_type(metric_type: str) -> str:
    return (metric_type or "").strip().upper()


def _infer_sensor_type(metric_type: str) -> str:
    normalized = _normalize_metric_type(metric_type)
    valid_types = {
        "PH",
        "EC",
        "TEMPERATURE",
        "HUMIDITY",
        "CO2",
        "LIGHT_INTENSITY",
        "WATER_LEVEL",
        "FLOW_RATE",
        "PUMP_CURRENT",
        "SOIL_MOISTURE",
        "PRESSURE",
        "WIND_SPEED",
        "WIND_DIRECTION",
        "OTHER",
    }
    if normalized in valid_types:
        return normalized
    return "OTHER"


def _build_sensor_label(metric_type: str, channel: Optional[str], sensor_type: str) -> str:
    if channel:
        return channel
    if metric_type:
        return metric_type
    return sensor_type


async def process_telemetry_batch(samples: list[TelemetrySampleModel]):
    """
    Обработать батч телеметрии:
    1. По node_uid/zone_uid находим node_id, zone_id
    2. Проверяем, что нода зарегистрирована и validated
    3. Нормализуем metric_type через Enum
    4. Создаем/находим sensor_id
    5. Пишем в telemetry_samples
    6. Обновляем telemetry_last
    """
    for sample in samples:
        # 1. Получаем node_id и zone_id
        node_id = None
        zone_id = sample.zone_id  # Может быть передано напрямую
        
        # Получаем node_id по node_uid
        if sample.node_uid:
            node_rows = await fetch(
                "SELECT id, zone_id, validated FROM nodes WHERE uid=$1",
                sample.node_uid
            )
            if node_rows:
                node_id = node_rows[0]["id"]
                # Если zone_id не указан в sample, берём из ноды
                if not zone_id and node_rows[0]["zone_id"]:
                    zone_id = node_rows[0]["zone_id"]
                # Проверяем validated
                if not node_rows[0].get("validated", False):
                    logger.warning(
                        "Telemetry from unvalidated node ignored",
                        extra={"node_uid": sample.node_uid, "metric_type": sample.metric_type}
                    )
                    continue
            else:
                logger.warning(
                    "Telemetry from unknown node ignored",
                    extra={"node_uid": sample.node_uid, "metric_type": sample.metric_type}
                )
                continue
        
        # Получаем zone_id по zone_uid, если указан (формат zn-{id})
        if not zone_id and sample.zone_uid:
            # zone_uid может быть в формате "zn-1" или просто числом как строка
            zone_uid_str = sample.zone_uid
            if zone_uid_str.startswith("zn-"):
                try:
                    zone_id = int(zone_uid_str[3:])
                except ValueError:
                    # Попробуем найти по uid, если он есть в БД (для будущей реализации)
                    zone_rows = await fetch(
                        "SELECT id FROM zones WHERE uid=$1",
                        zone_uid_str
                    )
                    if zone_rows:
                        zone_id = zone_rows[0]["id"]
            else:
                # Если это просто число
                try:
                    zone_id = int(zone_uid_str)
                except ValueError:
                    pass
        
        # Если не удалось определить zone_id, пропускаем
        if not zone_id:
            logger.warning(
                "Telemetry without zone_id ignored",
                extra={"node_uid": sample.node_uid, "metric_type": sample.metric_type}
            )
            continue
        
        # 2. Нормализация metric_type через Enum
        try:
            normalized_metric_type = normalize_metric_type(sample.metric_type)
        except UnknownMetricError as e:
            logger.warning(
                "Unknown metric type ignored",
                extra={
                    "node_uid": sample.node_uid,
                    "zone_id": zone_id,
                    "metric_type": sample.metric_type,
                    "error": str(e)
                }
            )
            continue
        
        # 3. Подготовка данных
        stored_metric_type = normalized_metric_type
        ts_value = sample.ts if sample.ts else datetime.utcnow()
        sensor_type = _infer_sensor_type(normalized_metric_type)
        sensor_label = _build_sensor_label(stored_metric_type, sample.channel, sensor_type)

        sensor_rows = await fetch(
            """
            SELECT id
            FROM sensors
            WHERE zone_id = $1
              AND node_id IS NOT DISTINCT FROM $2
              AND scope = $3
              AND type = $4
              AND label = $5
            LIMIT 1
            """,
            zone_id,
            node_id,
            "inside",
            sensor_type,
            sensor_label,
        )
        if sensor_rows:
            sensor_id = sensor_rows[0]["id"]
        else:
            greenhouse_rows = await fetch(
                """
                SELECT greenhouse_id
                FROM zones
                WHERE id = $1
                """,
                zone_id,
            )
            greenhouse_id = greenhouse_rows[0]["greenhouse_id"] if greenhouse_rows else None
            if greenhouse_id is None:
                logger.warning(
                    "Telemetry without greenhouse_id ignored",
                    extra={
                        "node_uid": sample.node_uid,
                        "zone_id": zone_id,
                        "metric_type": sample.metric_type,
                    }
                )
                continue

            sensor_rows = await fetch(
                """
                INSERT INTO sensors (
                    greenhouse_id, zone_id, node_id, scope, type, label, is_active,
                    created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, TRUE, NOW(), NOW())
                ON CONFLICT (zone_id, node_id, scope, type, label)
                DO UPDATE SET
                    updated_at = EXCLUDED.updated_at
                RETURNING id
                """,
                greenhouse_id,
                zone_id,
                node_id,
                "inside",
                sensor_type,
                sensor_label,
            )
            if not sensor_rows:
                logger.warning(
                    "Telemetry sensor creation failed",
                    extra={
                        "node_uid": sample.node_uid,
                        "zone_id": zone_id,
                        "metric_type": sample.metric_type,
                    }
                )
                continue
            sensor_id = sensor_rows[0]["id"]

        metadata = {
            "metric_type": stored_metric_type,
            "channel": sample.channel,
            "node_uid": sample.node_uid,
            "raw": sample.raw,
        }
        metadata = {key: value for key, value in metadata.items() if value is not None}

        # 4. Записываем в telemetry_samples
        await execute(
            """
            INSERT INTO telemetry_samples (sensor_id, ts, zone_id, value, quality, metadata)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            sensor_id,
            ts_value,
            zone_id,
            sample.value,
            "GOOD",
            metadata or None,
        )
        
        # 5. Обновляем telemetry_last
        await upsert_telemetry_last(
            sensor_id=sensor_id,
            value=sample.value,
            ts=ts_value,
            quality="GOOD",
        )
