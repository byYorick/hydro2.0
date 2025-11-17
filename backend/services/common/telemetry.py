"""
Общий модуль для обработки телеметрии.
Реализует единую точку записи телеметрии через process_telemetry_batch.
"""
import json
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


async def process_telemetry_batch(samples: list[TelemetrySampleModel]):
    """
    Обработать батч телеметрии:
    1. По node_uid/zone_uid находим node_id, zone_id
    2. Проверяем, что нода зарегистрирована и validated
    3. Нормализуем metric_type через Enum
    4. Пишем в telemetry_samples
    5. Обновляем telemetry_last
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
        raw_json = json.dumps(sample.raw) if sample.raw else None
        ts_value = sample.ts if sample.ts else datetime.utcnow()
        
        # 4. Записываем в telemetry_samples
        await execute(
            """
            INSERT INTO telemetry_samples (zone_id, node_id, channel, metric_type, value, raw, ts, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            """,
            zone_id, node_id, sample.channel, normalized_metric_type, sample.value, raw_json, ts_value
        )
        
        # 5. Обновляем telemetry_last
        await upsert_telemetry_last(
            zone_id=zone_id,
            node_id=node_id,
            metric_type=normalized_metric_type,
            channel=sample.channel,
            value=sample.value
        )

