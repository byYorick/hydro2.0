"""
Pump Safety Engine - проверки безопасности насосов.
Реализует проверки: no_flow, overcurrent, dry_run, pump_stuck_on.
Контракт sanity caps: doc_ai/03_TRANSPORT_MQTT/COMMAND_VALIDATION_ENGINE.md.
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from .db import fetch, execute
from .alerts import create_alert, AlertSource, AlertCode
from .alert_publisher import AlertPublisher
from .water_flow import check_water_level, check_flow, MIN_FLOW_THRESHOLD
from .utils.time import utcnow

logger = logging.getLogger(__name__)
_alert_publisher = AlertPublisher(default_source=AlertSource.BIZ.value)

# Пороги для безопасности насосов
MIN_WATER_LEVEL = 0.15  # 15% - минимальный уровень для работы насоса
CURRENT_IDLE_THRESHOLD = 50.0  # mA - порог тока в режиме простоя (по умолчанию)
DRY_RUN_CHECK_DELAY_SEC = 3  # Задержка перед проверкой flow после запуска насоса
DRY_RUN_LEVEL_MAX_AGE_SEC = 120  # Старше — уровень нельзя считать живым

_SOLUTION_TANK_HINTS = ("solution", "раствор", "level_solution")
_NON_SOURCE_TANK_HINTS = ("clean", "fresh", "чист", "drain", "waste", "слив")
MAX_RECENT_FAILURES = 3  # Максимальное количество недавних ошибок
FAILURE_WINDOW_MINUTES = 30  # Окно времени для подсчёта ошибок
MCU_OFFLINE_TIMEOUT_SEC = 300  # 5 минут - время без телеметрии для определения offline


def _to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if getattr(value, "tzinfo", None):
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _is_telemetry_grace_active(
    *,
    row: Dict[str, Any],
    now: datetime,
    telemetry_grace_sec: int,
    grace_node_types: set[str],
) -> bool:
    if telemetry_grace_sec <= 0 or not grace_node_types:
        return False

    node_type = str(row.get("type") or "").strip().lower()
    if not node_type or node_type not in grace_node_types:
        return False

    last_seen_at = _to_naive_utc(row.get("last_seen_at"))
    last_heartbeat_at = _to_naive_utc(row.get("last_heartbeat_at"))
    reference_ts = max(
        ts for ts in (last_seen_at, last_heartbeat_at) if ts is not None
    ) if (last_seen_at is not None or last_heartbeat_at is not None) else None
    if reference_ts is None:
        return False

    elapsed_sec = (now - reference_ts).total_seconds()
    return elapsed_sec <= telemetry_grace_sec


def _tank_label_is_source(label: str, *, source: str, channel: Optional[str]) -> bool:
    """Чистый бак и дренаж не являются источником полива и дозирования."""
    text = (label or "").strip().lower()
    if source == "dose" and channel:
        token = channel.strip().lower()
        if token and token in text:
            return True
    if any(hint in text for hint in _NON_SOURCE_TANK_HINTS):
        return False
    return any(hint in text for hint in _SOLUTION_TANK_HINTS)


def _pick_source_level_row(rows: List[Dict[str, Any]], *, source: str, channel: Optional[str]) -> Optional[Dict[str, Any]]:
    matched = [row for row in rows if _tank_label_is_source(str(row.get("label") or ""), source=source, channel=channel)]
    if source == "dose" and channel:
        token = channel.strip().lower()
        dedicated = [row for row in matched if token and token in str(row.get("label") or "").lower()]
        if dedicated:
            matched = dedicated
    if not matched:
        return None

    def _rank(row: Dict[str, Any]) -> tuple[int, datetime]:
        label = str(row.get("label") or "").lower()
        prefers_min = 1 if "min" in label else 0
        ts = _to_naive_utc(row.get("ts")) or datetime.min
        return (prefers_min, ts)

    return max(matched, key=_rank)


async def _alert_dry_run(zone_id: int, details: Dict[str, Any]) -> None:
    await create_alert(
        zone_id=zone_id,
        source=AlertSource.BIZ.value,
        code=AlertCode.BIZ_DRY_RUN.value,
        type="Dry run protection activated",
        details=details,
    )


async def check_dry_run(
    zone_id: int,
    min_water_level: Optional[float] = None,
    *,
    source: str = "solution",
    channel: Optional[str] = None,
    max_age_sec: int = DRY_RUN_LEVEL_MAX_AGE_SEC,
    now: Optional[datetime] = None,
) -> tuple[bool, Optional[str]]:
    """Уровень бака-источника перед пуском. Нет свежих данных — не безопасно.

    Полив и дозирование смотрят бак раствора (или датчик канала дозы),
    не бак чистой воды.
    """
    min_level = MIN_WATER_LEVEL if min_water_level is None else float(min_water_level)
    moment = _to_naive_utc(now) or utcnow().replace(tzinfo=None)
    details: Dict[str, Any] = {
        "zone_id": zone_id,
        "source": source,
        "channel": channel,
        "min_level": min_level,
        "max_age_sec": int(max_age_sec),
    }
    try:
        rows = await fetch(
            """
            SELECT
              s.label AS label,
              tl.last_value AS value,
              COALESCE(tl.last_ts, tl.updated_at) AS ts,
              tl.last_quality::text AS quality
            FROM sensors s
            LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
            WHERE s.zone_id = $1
              AND s.is_active IS TRUE
              AND UPPER(COALESCE(s.type, '')) = 'WATER_LEVEL'
            """,
            zone_id,
        )
    except Exception as exc:
        details["error"] = str(exc)
        logger.warning("Zone %s: dry-run check failed", zone_id, exc_info=True)
        try:
            await _alert_dry_run(zone_id, details)
        except Exception:
            logger.warning("Zone %s: dry-run alert failed", zone_id, exc_info=True)
        return False, "dry_run_check_failed"

    chosen = _pick_source_level_row(list(rows or []), source=source, channel=channel)
    if chosen is None:
        details["reason"] = "source_level_missing"
        logger.warning("Zone %s: dry-run blocked, source level missing (%s)", zone_id, source)
        await _alert_dry_run(zone_id, details)
        return False, "Source tank level is unavailable"

    quality = str(chosen.get("quality") or "").strip().upper()
    ts = _to_naive_utc(chosen.get("ts"))
    age_sec = None if ts is None else (moment - ts).total_seconds()
    details.update({"label": chosen.get("label"), "quality": quality, "age_sec": age_sec, "value": chosen.get("value")})
    if quality in {"BAD", "STUB"} or ts is None or age_sec is None or age_sec > float(max_age_sec) or age_sec < 0:
        details["reason"] = "source_level_stale"
        logger.warning("Zone %s: dry-run blocked, source level stale or bad", zone_id)
        await _alert_dry_run(zone_id, details)
        return False, "Source tank level is stale"

    try:
        level = float(chosen.get("value"))
    except (TypeError, ValueError):
        details["reason"] = "source_level_missing"
        await _alert_dry_run(zone_id, details)
        return False, "Source tank level is unavailable"

    if level < min_level:
        details["reason"] = "source_level_low"
        details["water_level"] = level
        logger.warning("Zone %s: dry-run blocked, level=%s < %s", zone_id, level, min_level)
        await _alert_dry_run(zone_id, details)
        return False, f"Water level too low: {level} < {min_level}"

    return True, None


async def check_no_flow(
    zone_id: int,
    pump_channel: str,
    cmd_id: Optional[str],
    pump_start_time: datetime,
    min_flow: float = MIN_FLOW_THRESHOLD
) -> tuple[bool, Optional[str]]:
    """
    Проверка отсутствия потока воды.
    
    Проверяет flow_rate или изменение water_level после запуска насоса.
    
    Args:
        zone_id: ID зоны
        pump_channel: Канал насоса (например, "pump_recirc")
        cmd_id: ID команды (опционально)
        pump_start_time: Время запуска насоса
        min_flow: Минимальный порог расхода (L/min)
    
    Returns:
        (is_ok, error_message): True если поток есть, False если отсутствует
    """
    now = utcnow().replace(tzinfo=None)
    pump_start_time = _to_naive_utc(pump_start_time)
    elapsed_sec = (now - pump_start_time).total_seconds()
    
    # Проверяем только если прошло больше DRY_RUN_CHECK_DELAY_SEC секунд
    if elapsed_sec < DRY_RUN_CHECK_DELAY_SEC:
        return True, None
    
    # Проверяем flow
    flow_ok, flow_value = await check_flow(zone_id, min_flow)
    
    if not flow_ok:
        # Создаём alert
        await create_alert(
            zone_id=zone_id,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type='No water flow detected',
            details={
                "zone_id": zone_id,
                "pump_channel": pump_channel,
                "cmd_id": cmd_id,
                "flow_value": flow_value,
                "min_flow": min_flow,
                "elapsed_sec": elapsed_sec,
                "pump_start_time": pump_start_time.isoformat()
            }
        )
        logger.warning(
            f"Zone {zone_id}, pump {pump_channel}: No flow detected - "
            f"flow={flow_value} L/min < {min_flow} L/min after {elapsed_sec:.1f}s"
        )
        return False, f"NO_FLOW detected: flow={flow_value} L/min < {min_flow} L/min"
    
    return True, None


async def check_mcu_offline(
    zone_id: int,
    node_id: Optional[int] = None,
    telemetry_grace_sec: int = 0,
    grace_node_types: Optional[List[str]] = None,
) -> tuple[bool, Optional[str]]:
    """
    Проверка, не оффлайн ли MCU (узел).
    
    Проверяет последнюю телеметрию или heartbeat узла.
    
    Args:
        zone_id: ID зоны
        node_id: ID узла (опционально, если не указан, проверяются все узлы зоны)
        telemetry_grace_sec: Допустимая задержка телеметрии для selected типов нод
        grace_node_types: Типы нод, для которых разрешен grace при отсутствии/stale telemetry
    
    Returns:
        (is_online, error_message): True если MCU онлайн, False если оффлайн
    """
    if node_id is not None:
        # Проверяем конкретный узел
        rows = await fetch(
            """
            SELECT n.id, n.type, n.status, n.last_seen_at, n.last_heartbeat_at, MAX(tl.updated_at) as last_telemetry
            FROM nodes n
            LEFT JOIN sensors s ON s.node_id = n.id
            LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
            WHERE n.id = $1 AND n.zone_id = $2
            GROUP BY n.id, n.type, n.status, n.last_seen_at, n.last_heartbeat_at
            """,
            node_id,
            zone_id,
        )
    else:
        # Проверяем все узлы зоны
        rows = await fetch(
            """
            SELECT n.id, n.type, n.status, n.last_seen_at, n.last_heartbeat_at, MAX(tl.updated_at) as last_telemetry
            FROM nodes n
            LEFT JOIN sensors s ON s.node_id = n.id
            LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
            WHERE n.zone_id = $1
            GROUP BY n.id, n.type, n.status, n.last_seen_at, n.last_heartbeat_at
            """,
            zone_id,
        )
    
    if not rows:
        return False, "No nodes found for zone"
    
    now = utcnow().replace(tzinfo=None)
    grace_types = {
        str(item).strip().lower()
        for item in (grace_node_types or [])
        if str(item).strip()
    }
    telemetry_grace_sec = max(0, int(telemetry_grace_sec or 0))
    for row in rows:
        node_status = row.get("status")
        last_telemetry = _to_naive_utc(row.get("last_telemetry"))
        
        # Проверяем статус узла
        if node_status != "online":
            return False, f"Node {row['id']} status is {node_status}"
        
        # Проверяем последнюю телеметрию
        grace_active = _is_telemetry_grace_active(
            row=row,
            now=now,
            telemetry_grace_sec=telemetry_grace_sec,
            grace_node_types=grace_types,
        )
        if last_telemetry:
            elapsed_sec = (now - last_telemetry).total_seconds()
            if elapsed_sec > MCU_OFFLINE_TIMEOUT_SEC:
                if grace_active:
                    continue
                return False, f"Node {row['id']} offline: no telemetry for {elapsed_sec:.0f}s"
        else:
            # Если нет телеметрии вообще, считаем оффлайн
            if grace_active:
                continue
            return False, f"Node {row['id']} offline: no telemetry data"
    
    return True, None


async def get_pump_thresholds(zone_id: int, pump_channel: str) -> Dict[str, float]:
    """
    Получить пороги безопасности для насоса из конфигурации узла.
    
    Args:
        zone_id: ID зоны
        pump_channel: Канал насоса
    
    Returns:
        Словарь с порогами: {"current_min": float, "current_max": float, "idle_threshold": float}
    """
    rows = await fetch(
        """
        SELECT n.config, nc.config as channel_config
        FROM nodes n
        LEFT JOIN node_channels nc ON nc.node_id = n.id AND nc.channel = $1
        WHERE n.zone_id = $2 AND n.status = 'online'
        LIMIT 1
        """,
        pump_channel,
        zone_id,
    )
    
    if not rows:
        # Возвращаем значения по умолчанию
        return {
            "current_min": 0.1,
            "current_max": 2.5,
            "idle_threshold": CURRENT_IDLE_THRESHOLD
        }
    
    node_config = rows[0].get("config") or {}
    channel_config = rows[0].get("channel_config") or {}
    
    # Получаем пороги из limits в NodeConfig
    limits = node_config.get("limits", {})
    current_min = float(limits.get("currentMin", 0.1))
    current_max = float(limits.get("currentMax", 2.5))
    
    # Idle threshold = 10% от current_max или значение по умолчанию
    idle_threshold = max(CURRENT_IDLE_THRESHOLD, current_max * 0.1)
    
    return {
        "current_min": current_min,
        "current_max": current_max,
        "idle_threshold": idle_threshold
    }


async def check_pump_stuck_on(
    zone_id: int,
    pump_channel: str,
    desired_state: str,
    current_ma: Optional[float] = None,
    flow_value: Optional[float] = None,
    node_id: Optional[int] = None
) -> tuple[bool, Optional[str]]:
    """
    Проверка залипшего насоса (pump_stuck_on).
    
    Сценарий: автоматика думает, что насос OFF (relay OPEN),
    а по телеметрии ток/flow > порога → реле залипло или есть обход.
    
    Args:
        zone_id: ID зоны
        pump_channel: Канал насоса
        desired_state: Желаемое состояние ("ON" или "OFF")
        current_ma: Текущий ток в мА (опционально)
        flow_value: Текущий расход в L/min (опционально)
    
    Returns:
        (is_ok, error_message): True если насос не залип, False если обнаружен stuck_on
    """
    if desired_state.upper() != "OFF":
        # Проверяем только если желаемое состояние OFF
        return True, None
    
    # Проверяем MCU offline
    mcu_online, mcu_error = await check_mcu_offline(zone_id, node_id)
    if not mcu_online:
        logger.warning(f"Zone {zone_id}, pump {pump_channel}: {mcu_error}")
        # Если MCU оффлайн, не можем проверить stuck_on, возвращаем True (не блокируем)
        return True, None
    
    # Получаем пороги из конфигурации
    thresholds = await get_pump_thresholds(zone_id, pump_channel)
    idle_threshold = thresholds["idle_threshold"]
    
    # Проверяем ток
    if current_ma is not None and current_ma > idle_threshold:
        # Создаём alert
        await create_alert(
            zone_id=zone_id,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_PUMP_STUCK_ON.value,
            type='Recirculation pump stuck ON',
            details={
                "zone_id": zone_id,
                "pump_channel": pump_channel,
                "desired_state": desired_state,
                "current_ma": current_ma,
                "threshold_ma": idle_threshold
            }
        )
        logger.error(
            f"Zone {zone_id}, pump {pump_channel}: Pump stuck ON - "
            f"desired_state={desired_state}, current_ma={current_ma} > {idle_threshold}"
        )
        return False, f"Pump stuck ON: current={current_ma} mA > {idle_threshold} mA"
    
    # Проверяем flow (если ток не доступен)
    if current_ma is None and flow_value is not None and flow_value > MIN_FLOW_THRESHOLD:
        await create_alert(
            zone_id=zone_id,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_PUMP_STUCK_ON.value,
            type='Recirculation pump stuck ON (by flow)',
            details={
                "zone_id": zone_id,
                "pump_channel": pump_channel,
                "desired_state": desired_state,
                "flow_value": flow_value,
                "threshold_flow": MIN_FLOW_THRESHOLD
            }
        )
        logger.error(
            f"Zone {zone_id}, pump {pump_channel}: Pump stuck ON (by flow) - "
            f"desired_state={desired_state}, flow={flow_value} L/min > {MIN_FLOW_THRESHOLD} L/min"
        )
        return False, f"Pump stuck ON: flow={flow_value} L/min > {MIN_FLOW_THRESHOLD} L/min"
    
    return True, None


async def get_active_critical_alerts(zone_id: int) -> List[Dict[str, Any]]:
    """
    Получить активные критические алерты для зоны.
    
    Args:
        zone_id: ID зоны
    
    Returns:
        Список активных критических алертов
    """
    critical_codes = [
        AlertCode.BIZ_OVERCURRENT.value,
        AlertCode.BIZ_NO_FLOW.value,
        AlertCode.BIZ_DRY_RUN.value,
        AlertCode.BIZ_PUMP_STUCK_ON.value,
    ]
    
    rows = await fetch(
        """
        SELECT id, code, type, details, created_at
        FROM alerts
        WHERE zone_id = $1 
          AND code = ANY($2)
          AND status = 'ACTIVE'
        ORDER BY created_at DESC
        """,
        zone_id,
        critical_codes,
    )
    
    return rows or []


async def resolve_active_critical_alerts_by_code(zone_id: int, codes: List[str]) -> None:
    """Resolve ACTIVE alerts by code for the zone."""
    normalized_codes = [str(code).strip().lower() for code in codes if str(code).strip()]
    if not normalized_codes:
        return
    rows = await fetch(
        """
        SELECT code, type, details, node_uid, hardware_id
        FROM alerts
        WHERE zone_id = $1
          AND LOWER(code) = ANY($2)
          AND status = 'ACTIVE'
        """,
        zone_id,
        normalized_codes,
    )
    for row in rows or []:
        details = row.get("details") if isinstance(row.get("details"), dict) else {}
        await _alert_publisher.resolve(
            zone_id=zone_id,
            source=AlertSource.BIZ.value,
            code=str(row.get("code") or ""),
            alert_type=str(row.get("type") or "biz"),
            details=details,
            dedupe_key=details.get("dedupe_key") if isinstance(details, dict) else None,
            scoped=isinstance(details, dict) and bool(details.get("dedupe_key")),
            node_uid=row.get("node_uid"),
            hardware_id=row.get("hardware_id"),
        )


async def too_many_recent_failures(
    zone_id: int,
    pump_channel: str,
    max_failures: int = MAX_RECENT_FAILURES,
    window_minutes: int = FAILURE_WINDOW_MINUTES
) -> bool:
    """
    Проверка, не слишком ли много недавних ошибок насоса.
    
    Args:
        zone_id: ID зоны
        pump_channel: Канал насоса
        max_failures: Максимальное количество ошибок
        window_minutes: Окно времени в минутах
    
    Returns:
        True если слишком много ошибок, False если нормально
    """
    window_start = utcnow().replace(tzinfo=None) - timedelta(minutes=window_minutes)
    
    critical_codes = [
        AlertCode.BIZ_OVERCURRENT.value,
        AlertCode.BIZ_NO_FLOW.value,
        AlertCode.BIZ_DRY_RUN.value,
    ]
    
    rows = await fetch(
        """
        SELECT COUNT(*) as count
        FROM alerts
        WHERE zone_id = $1 
          AND code = ANY($2)
          AND status IN ('ACTIVE', 'RESOLVED')
          AND created_at >= $3
          AND details->>'pump_channel' = $4
        """,
        zone_id,
        critical_codes,
        window_start,
        pump_channel,
    )
    
    failure_count = rows[0]["count"] if rows else 0
    return failure_count >= max_failures


async def _resolve_pump_node_ids(zone_id: int, pump_channel: str) -> List[int]:
    rows = await fetch(
        """
        SELECT DISTINCT n.id
        FROM nodes n
        JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1
          AND LOWER(TRIM(COALESCE(nc.channel, ''))) = LOWER(TRIM($2))
        ORDER BY n.id
        """,
        zone_id,
        pump_channel,
    )
    resolved: List[int] = []
    for row in rows or []:
        raw_id = row.get("id")
        try:
            resolved.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    return resolved


async def can_run_pump(
    zone_id: int,
    pump_channel: str,
    min_water_level: Optional[float] = None,
    node_id: Optional[int] = None,
    telemetry_grace_sec: int = 0,
    grace_node_types: Optional[List[str]] = None,
) -> tuple[bool, Optional[str]]:
    """
    Общая функция проверки безопасности перед запуском насоса.
    
    Проверяет:
    - MCU offline
    - Активные критические алерты
    - Уровень воды (dry_run)
    - Количество недавних ошибок
    
    Args:
        zone_id: ID зоны
        pump_channel: Канал насоса
        min_water_level: Минимальный уровень воды (опционально)
        node_id: ID узла (опционально, для проверки конкретного узла)
        telemetry_grace_sec: Допустимая задержка телеметрии для grace-типов нод
        grace_node_types: Типы нод, которым разрешен grace при старте после активации
    
    Returns:
        (can_run, error_message): True если можно запустить, False если нельзя
    """
    target_node_ids: List[int] = []
    if node_id is not None:
        target_node_ids = [int(node_id)]
    else:
        target_node_ids = await _resolve_pump_node_ids(zone_id, pump_channel)

    if target_node_ids:
        for target_node_id in target_node_ids:
            mcu_online, mcu_error = await check_mcu_offline(
                zone_id,
                target_node_id,
                telemetry_grace_sec=telemetry_grace_sec,
                grace_node_types=grace_node_types,
            )
            if not mcu_online:
                return False, f"MCU offline: {mcu_error}"
    else:
        mcu_online, mcu_error = await check_mcu_offline(
            zone_id,
            None,
            telemetry_grace_sec=telemetry_grace_sec,
            grace_node_types=grace_node_types,
        )
        if not mcu_online:
            return False, f"MCU offline: {mcu_error}"

    # Проверяем уровень воды (dry_run) в реальном времени
    dry_run_ok, dry_run_msg = await check_dry_run(zone_id, min_water_level)
    if not dry_run_ok:
        return False, dry_run_msg

    # Если уровень восстановился, закрываем sticky dry-run alert.
    # Dry-run валидируется динамически выше и не должен блокировать бесконечно.
    await resolve_active_critical_alerts_by_code(zone_id, [AlertCode.BIZ_DRY_RUN.value])

    # Проверяем активные критические алерты
    active_alerts = await get_active_critical_alerts(zone_id)
    critical_codes = {
        AlertCode.BIZ_OVERCURRENT.value,
        AlertCode.BIZ_NO_FLOW.value,
        AlertCode.BIZ_PUMP_STUCK_ON.value,
    }
    
    for alert in active_alerts:
        if alert["code"] in critical_codes:
            return False, f"Active critical alert: {alert['code']}"
    
    # Проверяем количество недавних ошибок
    if await too_many_recent_failures(zone_id, pump_channel):
        return False, f"Too many recent failures for pump {pump_channel}"
    
    return True, None
