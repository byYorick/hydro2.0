import json
import logging
from typing import List, Optional

# Максимальный размер MQTT/HTTP payload (64KB) для защиты от DoS
MAX_PAYLOAD_SIZE = 64 * 1024

# Максимальный размер raw JSON для защиты от раздувания БД
MAX_RAW_JSON_SIZE = 10 * 1024

logger = logging.getLogger(__name__)


def _calculate_broadcast_backoff(
    error_count: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> float:
    """Вычисляет задержку для exponential backoff при ошибках broadcast."""
    if error_count == 0:
        return 0.0
    delay = base_delay * (2 ** min(error_count - 1, 6))
    return min(delay, max_delay)


def _filter_raw_data(raw_data: Optional[dict]) -> Optional[dict]:
    """Фильтрует и ограничивает размер raw данных для сохранения в БД."""
    if not raw_data or not isinstance(raw_data, dict):
        return raw_data

    allowed_raw_fields = {
        "metric_type",
        "value",
        "ts",
        "channel",
        "node_id",
        "raw",
        "stub",
        "stable",
        "tds",
        "error_code",
        "temperature",
        "state",
        "event",
        "health",
        "zone_uid",
        "node_uid",
        "gh_uid",
    }

    filtered = {k: v for k, v in raw_data.items() if k in allowed_raw_fields}

    try:
        json_str = json.dumps(filtered, default=str)
        if len(json_str.encode("utf-8")) > MAX_RAW_JSON_SIZE:
            minimal = {
                "metric_type": filtered.get("metric_type"),
                "value": filtered.get("value"),
                "ts": filtered.get("ts"),
            }
            json_str = json.dumps(minimal, default=str)
            if len(json_str.encode("utf-8")) > MAX_RAW_JSON_SIZE:
                logger.warning(
                    "Raw data too large even after filtering, dropping",
                    extra={
                        "original_size": len(json.dumps(raw_data, default=str).encode("utf-8"))
                    },
                )
                return None
            return minimal
        return filtered
    except Exception as e:
        logger.warning(f"Failed to filter raw data: {e}")
        return None


def _parse_json(payload: bytes) -> Optional[dict]:
    """Parse JSON payload with size validation."""
    try:
        if len(payload) > MAX_PAYLOAD_SIZE:
            logger.error(
                f"Payload too large: {len(payload)} bytes (max: {MAX_PAYLOAD_SIZE})"
            )
            return None

        return json.loads(payload.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}")
        return None


def extract_zone_id_from_uid(zone_uid: Optional[str]) -> Optional[int]:
    """
    Извлечь zone_id из zone_uid (формат: zn-{id} или zone-{uid}).
    """
    if not zone_uid:
        return None

    if zone_uid.startswith("zn-"):
        try:
            return int(zone_uid.split("-")[1])
        except (ValueError, IndexError):
            return None

    return None


def _extract_topic_part(topic: str, index: int) -> Optional[str]:
    """
    Универсальная функция для извлечения части топика по индексу.
    """
    parts = topic.split("/")
    if 0 <= index < len(parts):
        return parts[index]
    return None


def _extract_zone_uid(topic: str) -> Optional[str]:
    """Извлечь zone_uid из топика."""
    return _extract_topic_part(topic, 2)


def _extract_node_uid(topic: str) -> Optional[str]:
    """Извлечь node_uid из топика."""
    return _extract_topic_part(topic, 3)


def _extract_gh_uid(topic: str) -> Optional[str]:
    """Извлечь gh_uid (greenhouse UID) из топика."""
    return _extract_topic_part(topic, 1)


def _extract_channel_from_topic(topic: str) -> Optional[str]:
    """Извлечь channel из топика телеметрии."""
    return _extract_topic_part(topic, 4)


def _has_rows(rows: Optional[List]) -> bool:
    """Проверить, есть ли результаты в rows."""
    return rows is not None and len(rows) > 0
