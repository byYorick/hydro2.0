"""
Pump Safety Engine - проверки безопасности насосов.
Реализует проверки: no_flow, overcurrent, dry_run, pump_stuck_on.
Согласно BACKEND_REFACTOR_PLAN.md раздел 14.
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from .db import fetch, execute
from .alerts import create_alert, AlertSource, AlertCode
from .water_flow import check_water_level, check_flow, MIN_FLOW_THRESHOLD

logger = logging.getLogger(__name__)

# Пороги для безопасности насосов
MIN_WATER_LEVEL = 0.15  # 15% - минимальный уровень для работы насоса
CURRENT_IDLE_THRESHOLD = 50.0  # mA - порог тока в режиме простоя (по умолчанию)
DRY_RUN_CHECK_DELAY_SEC = 3  # Задержка перед проверкой flow после запуска насоса
MAX_RECENT_FAILURES = 3  # Максимальное количество недавних ошибок
FAILURE_WINDOW_MINUTES = 30  # Окно времени для подсчёта ошибок
MCU_OFFLINE_TIMEOUT_SEC = 300  # 5 минут - время без телеметрии для определения offline


async def check_dry_run(zone_id: int, min_water_level: Optional[float] = None) -> tuple[bool, Optional[str]]:
    """
    Проверка защиты от сухого хода.
    
    Перед попыткой включить насос проверяем water_level.
    
    Args:
        zone_id: ID зоны
        min_water_level: Минимальный уровень воды (по умолчанию MIN_WATER_LEVEL)
    
    Returns:
        (is_safe, error_message): True если безопасно, False если обнаружен сухой ход
    """
    min_level = min_water_level or MIN_WATER_LEVEL
    
    water_level_ok, water_level = await check_water_level(zone_id)
    
    if water_level is not None and water_level < min_level:
        # Создаём alert
        await create_alert(
            zone_id=zone_id,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_DRY_RUN.value,
            type='Dry run protection activated',
            details={
                "water_level": water_level,
                "min_level": min_level,
                "zone_id": zone_id
            }
        )
        logger.warning(
            f"Zone {zone_id}: Dry run protection activated - water_level={water_level} < {min_level}"
        )
        return False, f"Water level too low: {water_level} < {min_level}"
    
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
    now = datetime.utcnow()
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


async def check_mcu_offline(zone_id: int, node_id: Optional[int] = None) -> tuple[bool, Optional[str]]:
    """
    Проверка, не оффлайн ли MCU (узел).
    
    Проверяет последнюю телеметрию или heartbeat узла.
    
    Args:
        zone_id: ID зоны
        node_id: ID узла (опционально, если не указан, проверяются все узлы зоны)
    
    Returns:
        (is_online, error_message): True если MCU онлайн, False если оффлайн
    """
    if node_id is not None:
        # Проверяем конкретный узел
        rows = await fetch(
            """
            SELECT n.id, n.status, MAX(tl.updated_at) as last_telemetry
            FROM nodes n
            LEFT JOIN telemetry_last tl ON tl.node_id = n.id
            WHERE n.id = $1 AND n.zone_id = $2
            GROUP BY n.id, n.status
            """,
            node_id,
            zone_id,
        )
    else:
        # Проверяем все узлы зоны
        rows = await fetch(
            """
            SELECT n.id, n.status, MAX(tl.updated_at) as last_telemetry
            FROM nodes n
            LEFT JOIN telemetry_last tl ON tl.node_id = n.id
            WHERE n.zone_id = $1
            GROUP BY n.id, n.status
            """,
            zone_id,
        )
    
    if not rows:
        return False, "No nodes found for zone"
    
    now = datetime.utcnow()
    for row in rows:
        node_status = row.get("status")
        last_telemetry = row.get("last_telemetry")
        
        # Проверяем статус узла
        if node_status != "online":
            return False, f"Node {row['id']} status is {node_status}"
        
        # Проверяем последнюю телеметрию
        if last_telemetry:
            elapsed_sec = (now - last_telemetry).total_seconds()
            if elapsed_sec > MCU_OFFLINE_TIMEOUT_SEC:
                return False, f"Node {row['id']} offline: no telemetry for {elapsed_sec:.0f}s"
        else:
            # Если нет телеметрии вообще, считаем оффлайн
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
    window_start = datetime.utcnow() - timedelta(minutes=window_minutes)
    
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


async def can_run_pump(
    zone_id: int,
    pump_channel: str,
    min_water_level: Optional[float] = None,
    node_id: Optional[int] = None
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
    
    Returns:
        (can_run, error_message): True если можно запустить, False если нельзя
    """
    # Проверяем MCU offline
    mcu_online, mcu_error = await check_mcu_offline(zone_id, node_id)
    if not mcu_online:
        return False, f"MCU offline: {mcu_error}"
    
    # Проверяем активные критические алерты
    active_alerts = await get_active_critical_alerts(zone_id)
    critical_codes = {
        AlertCode.BIZ_OVERCURRENT.value,
        AlertCode.BIZ_NO_FLOW.value,
        AlertCode.BIZ_DRY_RUN.value,
        AlertCode.BIZ_PUMP_STUCK_ON.value,
    }
    
    for alert in active_alerts:
        if alert["code"] in critical_codes:
            return False, f"Active critical alert: {alert['code']}"
    
    # Проверяем уровень воды (dry_run)
    dry_run_ok, dry_run_msg = await check_dry_run(zone_id, min_water_level)
    if not dry_run_ok:
        return False, dry_run_msg
    
    # Проверяем количество недавних ошибок
    if await too_many_recent_failures(zone_id, pump_channel):
        return False, f"Too many recent failures for pump {pump_channel}"
    
    return True, None

