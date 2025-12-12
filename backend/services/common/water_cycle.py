"""
Water Cycle Engine - управление циркуляцией и сменой воды.
Реализует логику замкнутого контура и плановой смены раствора.
Согласно BACKEND_REFACTOR_PLAN.md разделы 10, 12, 13.
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from .db import fetch, execute, create_zone_event
from .alerts import create_alert, AlertSource, AlertCode
from .water_flow import check_water_level, check_flow, execute_fill_mode, execute_drain_mode
from .pump_safety import can_run_pump, check_pump_stuck_on
from .command_orchestrator import send_command

logger = logging.getLogger(__name__)

# Состояния зоны для водного цикла
WATER_STATE_NORMAL_RECIRC = "NORMAL_RECIRC"
WATER_STATE_WATER_CHANGE_DRAIN = "WATER_CHANGE_DRAIN"
WATER_STATE_WATER_CHANGE_FILL = "WATER_CHANGE_FILL"
WATER_STATE_WATER_CHANGE_STABILIZE = "WATER_CHANGE_STABILIZE"


async def get_zone_water_cycle_config(zone_id: int) -> Dict[str, Any]:
    """
    Получить конфигурацию водного цикла зоны из zones.settings.
    
    Returns:
        Конфигурация water_cycle или значения по умолчанию
    """
    rows = await fetch(
        """
        SELECT settings
        FROM zones
        WHERE id = $1
        """,
        zone_id,
    )
    
    if not rows or not rows[0].get("settings"):
        # Значения по умолчанию
        return {
            "mode": "RECIRCULATING",
            "recirc": {
                "enabled": False,
                "schedule": [{"from": "00:00", "to": "23:59", "duty_cycle": 0.5}],
                "max_recirc_off_minutes": 10,
            },
            "water_change": {
                "enabled": False,
                "interval_days": 7,
                "time_of_day": "09:00",
                "max_solution_age_days": 10,
                "trigger_by_ec_drift": True,
                "ec_drift_threshold": 30,
            },
        }
    
    settings = rows[0]["settings"]
    if isinstance(settings, dict):
        water_cycle_config = settings.get("water_cycle", {})
        # Если water_cycle пустой или не найден, возвращаем дефолтные значения
        if not water_cycle_config or not isinstance(water_cycle_config, dict):
            return {
                "mode": "RECIRCULATING",
                "recirc": {
                    "enabled": False,
                    "schedule": [{"from": "00:00", "to": "23:59", "duty_cycle": 0.5}],
                    "max_recirc_off_minutes": 10,
                },
                "water_change": {
                    "enabled": False,
                    "interval_days": 7,
                    "time_of_day": "09:00",
                    "max_solution_age_days": 10,
                    "trigger_by_ec_drift": True,
                    "ec_drift_threshold": 30,
                },
            }
        return water_cycle_config
    
    # Если settings не словарь, возвращаем дефолтные значения
    return {
        "mode": "RECIRCULATING",
        "recirc": {
            "enabled": False,
            "schedule": [{"from": "00:00", "to": "23:59", "duty_cycle": 0.5}],
            "max_recirc_off_minutes": 10,
        },
        "water_change": {
            "enabled": False,
            "interval_days": 7,
            "time_of_day": "09:00",
            "max_solution_age_days": 10,
            "trigger_by_ec_drift": True,
            "ec_drift_threshold": 30,
        },
    }


async def get_zone_water_state(zone_id: int) -> str:
    """
    Получить текущее состояние водного цикла зоны.
    
    Returns:
        WATER_STATE_* или NORMAL_RECIRC по умолчанию
    """
    rows = await fetch(
        """
        SELECT water_state
        FROM zones
        WHERE id = $1
        """,
        zone_id,
    )
    
    if rows and rows[0].get("water_state"):
        return rows[0]["water_state"]
    
    return WATER_STATE_NORMAL_RECIRC


async def set_zone_water_state(zone_id: int, state: str) -> None:
    """
    Установить состояние водного цикла зоны.
    
    Args:
        zone_id: ID зоны
        state: WATER_STATE_*
    """
    await execute(
        """
        UPDATE zones
        SET water_state = $1, updated_at = NOW()
        WHERE id = $2
        """,
        state,
        zone_id,
    )


async def get_solution_started_at(zone_id: int) -> Optional[datetime]:
    """
    Получить время начала текущего раствора.
    
    Returns:
        datetime начала раствора или None
    """
    rows = await fetch(
        """
        SELECT solution_started_at
        FROM zones
        WHERE id = $1
        """,
        zone_id,
    )
    
    if rows and rows[0].get("solution_started_at"):
        return rows[0]["solution_started_at"]
    
    return None


async def set_solution_started_at(zone_id: int, started_at: Optional[datetime] = None) -> None:
    """
    Установить время начала текущего раствора.
    
    Args:
        zone_id: ID зоны
        started_at: Время начала (по умолчанию сейчас)
    """
    if started_at is None:
        started_at = datetime.utcnow()
    
    await execute(
        """
        UPDATE zones
        SET solution_started_at = $1, updated_at = NOW()
        WHERE id = $2
        """,
        started_at,
        zone_id,
    )


def in_schedule_window(now: datetime, schedule: List[Dict[str, str]]) -> bool:
    """
    Проверить, попадает ли текущее время в окно расписания.
    
    Args:
        now: Текущее время
        schedule: Список окон расписания [{"from": "HH:MM", "to": "HH:MM"}]
    
    Returns:
        True если в окне расписания
    """
    if not schedule:
        return True  # Если расписание не задано, считаем что всегда активно
    
    current_time = now.time()
    
    for window in schedule:
        from_time_str = window.get("from", "00:00")
        to_time_str = window.get("to", "23:59")
        
        try:
            from_parts = from_time_str.split(":")
            to_parts = to_time_str.split(":")
            from_time = datetime.strptime(from_time_str, "%H:%M").time()
            to_time = datetime.strptime(to_time_str, "%H:%M").time()
            
            if from_time <= to_time:
                # Обычное окно (в пределах одного дня)
                if from_time <= current_time <= to_time:
                    return True
            else:
                # Окно переходит через полночь (например, 22:00-06:00)
                if current_time >= from_time or current_time <= to_time:
                    return True
        except Exception:
            continue
    
    return False


async def tick_recirculation(
    zone_id: int,
    mqtt_client: Any = None,  # Deprecated, не используется
    gh_uid: Optional[str] = None,  # Опционально, будет получен из БД
    now: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    """
    Проверка и управление циркуляцией с учётом NC-насоса.
    
    Для NC-насоса (normaly-closed relay):
    - В норме насос ON (реле закрыто, контакты замкнуты)
    - Для реализации duty_cycle нужно периодически размыкать реле (отключать насос)
    - При падении электроники реле отпускает, насос работает постоянно (fail-safe)
    
    Args:
        zone_id: ID зоны
        mqtt_client: MQTT клиент для отправки команд
        gh_uid: UID теплицы
        now: Текущее время (опционально)
    
    Returns:
        Команда для управления насосом или None
    """
    if now is None:
        now = datetime.utcnow()
    
    # Получаем конфигурацию водного цикла
    water_cycle = await get_zone_water_cycle_config(zone_id)
    recirc_cfg = water_cycle.get("recirc", {})
    
    if not recirc_cfg.get("enabled", False):
        # Рециркуляция отключена - насос ON (NC, не трогаем реле)
        return None
    
    # Проверяем расписание
    schedule = recirc_cfg.get("schedule", [])
    if not in_schedule_window(now, schedule):
        # Вне окна расписания - насос OFF (размыкаем реле)
        desired_state = "OFF"
    else:
        # В окне расписания - проверяем duty_cycle
        duty_cycle = schedule[0].get("duty_cycle", 0.5) if schedule else 0.5
        
        # Точная логика duty_cycle: разбиваем время на циклы
        # Цикл = 10 минут (600 секунд) - можно настроить
        cycle_duration_sec = 600
        cycle_position_sec = int(now.timestamp()) % cycle_duration_sec
        
        # Вычисляем, должен ли насос быть ON в текущий момент цикла
        on_duration_sec = int(cycle_duration_sec * duty_cycle)
        
        if cycle_position_sec < on_duration_sec:
            desired_state = "ON"
        else:
            desired_state = "OFF"
    
    # Проверяем ограничение max_recirc_off_minutes
    max_off_minutes = recirc_cfg.get("max_recirc_off_minutes", 10)
    if desired_state == "OFF":
        # Проверяем, сколько времени насос уже OFF
        # Получаем последнее состояние насоса из событий или команд
        last_state_rows = await fetch(
            """
            SELECT created_at, details->>'pump_state' as pump_state
            FROM zone_events
            WHERE zone_id = $1 
              AND type IN ('RECIRCULATION_STATE_CHANGED', 'RECIRCULATION_CYCLE')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            zone_id,
        )
        
        if last_state_rows:
            last_state_time = last_state_rows[0]["created_at"]
            last_state = last_state_rows[0].get("pump_state")
            
            if last_state == "OFF":
                off_duration_minutes = (now - last_state_time).total_seconds() / 60.0
                if off_duration_minutes > max_off_minutes:
                    # Превышено максимальное время OFF - включаем насос
                    desired_state = "ON"
    
    # Получаем узлы для рециркуляции
    rows = await fetch(
        """
        SELECT n.id, n.uid, n.type, nc.channel, nc.config
        FROM nodes n
        LEFT JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1 
          AND n.status = 'online'
          AND (n.type = 'recirculation' OR nc.channel = 'pump_recirc')
        LIMIT 1
        """,
        zone_id,
    )
    
    if not rows:
        return None
    
    node_info = rows[0]
    pump_channel = node_info.get("channel") or "pump_recirc"
    node_config = node_info.get("config") or {}
    
    # Проверяем, является ли насос NC (normaly-closed)
    fail_safe_mode = node_config.get("fail_safe_mode", "NO")  # По умолчанию NO
    is_nc_pump = fail_safe_mode == "NC"
    
    # Проверяем текущее состояние насоса (по телеметрии тока/flow)
    # Получаем текущий ток из telemetry_last
    current_rows = await fetch(
        """
        SELECT value
        FROM telemetry_last
        WHERE zone_id = $1 AND metric_type = 'pump_current' AND node_id = $2
        LIMIT 1
        """,
        zone_id,
        node_info["id"],
    )
    current_ma = float(current_rows[0]["value"]) if current_rows and current_rows[0].get("value") else None
    
    # Получаем текущий flow из telemetry_last (используем FLOW_RATE из metrics)
    flow_rows = await fetch(
        """
        SELECT value
        FROM telemetry_last
        WHERE zone_id = $1 AND metric_type = 'flow_rate'
        LIMIT 1
        """,
        zone_id,
    )
    flow_value = float(flow_rows[0]["value"]) if flow_rows and flow_rows[0].get("value") else None
    
    # Проверяем pump_stuck_on если желаемое состояние OFF
    if desired_state == "OFF":
        stuck_ok, stuck_msg = await check_pump_stuck_on(
            zone_id, pump_channel, desired_state, current_ma, flow_value
        )
        if not stuck_ok:
            logger.warning(f"Zone {zone_id}: {stuck_msg}")
            # Не меняем состояние, оставляем как есть
    
    # Проверяем безопасность перед включением насоса
    if desired_state == "ON":
        can_run, error_msg = await can_run_pump(zone_id, pump_channel)
        if not can_run:
            logger.warning(f"Zone {zone_id}: Cannot run pump {pump_channel}: {error_msg}")
            return None
    
    # Формируем команду для насоса
    # Для NC-насоса: relay OPEN = насос OFF, relay CLOSED = насос ON
    relay_state = "OPEN" if desired_state == "OFF" else "CLOSED"
    
    # Если включаем насос, добавляем информацию для мониторинга no_flow
    event_details = {
        'desired_state': desired_state,
        'relay_state': relay_state,
        'is_nc_pump': is_nc_pump,
        'max_off_minutes': max_off_minutes,
    }
    
    if desired_state == "ON":
        # Добавляем время запуска для мониторинга no_flow
        event_details['pump_start_time'] = now.isoformat()
        event_details['monitor_no_flow'] = True
    
    # Возвращаем информацию о команде для отправки через оркестратор
    # Вызывающий код должен использовать send_command() для отправки
    return {
        'node_uid': node_info["uid"],
        'channel': pump_channel,
        'cmd': 'set_relay_state',
        'params': {
            'state': relay_state,  # OPEN или CLOSED
            'reason': 'recirculation_control'
        },
        'event_type': 'RECIRCULATION_STATE_CHANGED',
        'event_details': event_details,
        'zone_id': zone_id,
        'greenhouse_uid': gh_uid
    }


async def check_water_change_required(zone_id: int) -> Tuple[bool, Optional[str]]:
    """
    Проверить, требуется ли смена воды.
    
    Проверяет:
    - Прошло ли interval_days с solution_started_at
    - Превышен ли max_solution_age_days
    - Превышен ли ec_drift_threshold (если trigger_by_ec_drift включён)
    
    Args:
        zone_id: ID зоны
    
    Returns:
        (required, reason): True если требуется смена воды, False если нет
    """
    water_cycle = await get_zone_water_cycle_config(zone_id)
    water_change_cfg = water_cycle.get("water_change", {})
    
    if not water_change_cfg.get("enabled", False):
        return False, None
    
    solution_started_at = await get_solution_started_at(zone_id)
    if solution_started_at is None:
        # Если раствор ещё не был начат, не требуется смена
        return False, None
    
    now = datetime.utcnow()
    
    # Проверяем interval_days
    interval_days = water_change_cfg.get("interval_days", 7)
    if (now - solution_started_at).days >= interval_days:
        return True, f"Interval {interval_days} days exceeded"
    
    # Проверяем max_solution_age_days
    max_age_days = water_change_cfg.get("max_solution_age_days", 10)
    if (now - solution_started_at).days >= max_age_days:
        return True, f"Max solution age {max_age_days} days exceeded"
    
    # Проверяем EC drift (если включён)
    if water_change_cfg.get("trigger_by_ec_drift", False):
        ec_drift_threshold = water_change_cfg.get("ec_drift_threshold", 30)
        
        # Получаем начальное значение EC (при solution_started_at или в течение первых 2 часов)
        initial_ec_window = solution_started_at + timedelta(hours=2)
        initial_ec_rows = await fetch(
            """
            SELECT AVG(value) as avg_value
            FROM telemetry_samples
            WHERE zone_id = $1 
              AND metric_type = 'EC'
              AND created_at >= $2
              AND created_at <= $3
            """,
            zone_id,
            solution_started_at,
            initial_ec_window,
        )
        
        if initial_ec_rows and initial_ec_rows[0].get("avg_value") is not None:
            initial_ec = float(initial_ec_rows[0]["avg_value"])
            
            # Получаем текущее значение EC (последние 2 часа)
            recent_cutoff = now - timedelta(hours=2)
            current_ec_rows = await fetch(
                """
                SELECT AVG(value) as avg_value
                FROM telemetry_samples
                WHERE zone_id = $1 
                  AND metric_type = 'EC'
                  AND created_at >= $2
                """,
                zone_id,
                recent_cutoff,
            )
            
            if current_ec_rows and current_ec_rows[0].get("avg_value") is not None:
                current_ec = float(current_ec_rows[0]["avg_value"])
                
                # Вычисляем процент дрифта: |current - initial| / initial * 100
                if initial_ec > 0:
                    ec_drift_percent = abs(current_ec - initial_ec) / initial_ec * 100.0
                    
                    if ec_drift_percent >= ec_drift_threshold:
                        logger.info(
                            f"Zone {zone_id}: EC drift detected - "
                            f"initial={initial_ec:.3f}, current={current_ec:.3f}, "
                            f"drift={ec_drift_percent:.1f}% >= {ec_drift_threshold}%"
                        )
                        return True, f"EC drift {ec_drift_percent:.1f}% >= {ec_drift_threshold}%"
    
    return False, None


async def execute_water_change(
    zone_id: int,
    mqtt_client: Any = None,  # Deprecated, не используется
    gh_uid: Optional[str] = None  # Опционально, будет получен из БД
) -> Dict[str, Any]:
    """
    Выполнить смену воды для зоны.
    
    Алгоритм:
    1. WATER_CHANGE_DRAIN - осознанно выключаем recirc-насос, запускаем drain
    2. WATER_CHANGE_FILL - запускаем fill
    3. WATER_CHANGE_STABILIZE - ждём стабилизации, фиксируем параметры
    4. NORMAL_RECIRC - возвращаем зону в нормальный режим
    
    Args:
        zone_id: ID зоны
        mqtt_client: MQTT клиент для отправки команд
        gh_uid: UID теплицы
    
    Returns:
        Результат выполнения смены воды
    """
    current_state = await get_zone_water_state(zone_id)
    
    if current_state == WATER_STATE_NORMAL_RECIRC:
        # Начинаем смену воды
        await set_zone_water_state(zone_id, WATER_STATE_WATER_CHANGE_DRAIN)
        await create_zone_event(
            zone_id,
            'WATER_CHANGE_STARTED',
            {
                'zone_id': zone_id,
                'start_time': datetime.utcnow().isoformat()
            }
        )
        # После изменения состояния перечитываем его для следующего блока
        current_state = WATER_STATE_WATER_CHANGE_DRAIN
    
    if current_state == WATER_STATE_WATER_CHANGE_DRAIN:
        # Выключаем recirc-насос (для NC - размыкаем реле)
        # Получаем узлы рециркуляции
        rows = await fetch(
            """
            SELECT n.id, n.uid, n.type, nc.channel
            FROM nodes n
            LEFT JOIN node_channels nc ON nc.node_id = n.id
            WHERE n.zone_id = $1 
              AND (n.type = 'recirculation' OR nc.channel = 'pump_recirc')
            LIMIT 1
            """,
            zone_id,
        )
        
        if rows:
            node_info = rows[0]
            pump_channel = node_info.get("channel") or "pump_recirc"
            # Отключаем насос (для NC - размыкаем реле) через единый оркестратор
            await send_command(
                zone_id=zone_id,
                node_uid=node_info['uid'],
                channel=pump_channel,
                cmd="set_relay_state",
                params={"state": "OPEN"},
                greenhouse_uid=gh_uid,
            )
        
        # Запускаем drain
        drain_result = await execute_drain_mode(
            zone_id,
            target_level=0.1,  # Дренируем до 10%
            mqtt_client=mqtt_client,
            gh_uid=gh_uid,
            max_duration_sec=600  # Максимум 10 минут
        )
        
        if drain_result.get("success"):
            await set_zone_water_state(zone_id, WATER_STATE_WATER_CHANGE_FILL)
            # После изменения состояния перечитываем его для следующего блока
            current_state = WATER_STATE_WATER_CHANGE_FILL
        else:
            # Ошибка при дренаже
            await set_zone_water_state(zone_id, WATER_STATE_NORMAL_RECIRC)
            return {
                'success': False,
                'error': 'drain_failed',
                'details': drain_result
            }
    
    if current_state == WATER_STATE_WATER_CHANGE_FILL:
        # Запускаем fill
        fill_result = await execute_fill_mode(
            zone_id,
            target_level=0.9,  # Заполняем до 90%
            mqtt_client=mqtt_client,
            gh_uid=gh_uid,
            max_duration_sec=600  # Максимум 10 минут
        )
        
        if fill_result.get("success"):
            await set_zone_water_state(zone_id, WATER_STATE_WATER_CHANGE_STABILIZE)
            # После изменения состояния перечитываем его для следующего блока
            current_state = WATER_STATE_WATER_CHANGE_STABILIZE
        else:
            # Ошибка при заполнении
            await set_zone_water_state(zone_id, WATER_STATE_NORMAL_RECIRC)
            return {
                'success': False,
                'error': 'fill_failed',
                'details': fill_result
            }
    
    if current_state == WATER_STATE_WATER_CHANGE_STABILIZE:
        # Ждём стабилизации (например, 30 минут)
        stabilize_minutes = 30
        solution_started_at = await get_solution_started_at(zone_id)
        
        if solution_started_at is None:
            # Устанавливаем время начала стабилизации
            await set_solution_started_at(zone_id)
            return {
                'success': True,
                'state': WATER_STATE_WATER_CHANGE_STABILIZE,
                'stabilizing': True,
                'stabilize_minutes': stabilize_minutes
            }
        
        # Проверяем, прошло ли время стабилизации
        elapsed_minutes = (datetime.utcnow() - solution_started_at).total_seconds() / 60.0
        
        if elapsed_minutes >= stabilize_minutes:
            # Фиксируем параметры после стабилизации
            # Получаем текущие pH, EC, temperature из telemetry_last
            params_rows = await fetch(
                """
                SELECT metric_type, value
                FROM telemetry_last
                WHERE zone_id = $1 
                  AND metric_type IN ('PH', 'EC', 'TEMPERATURE')
                """,
                zone_id,
            )
            
            stabilized_params = {}
            for row in params_rows:
                metric_type = row["metric_type"]
                value = row.get("value")
                if value is not None:
                    stabilized_params[metric_type.lower()] = float(value)
            
            # Создаём событие завершения смены воды
            await create_zone_event(
                zone_id,
                'WATER_CHANGE_COMPLETED',
                {
                    'zone_id': zone_id,
                    'solution_started_at': solution_started_at.isoformat(),
                    'completed_at': datetime.utcnow().isoformat(),
                    'stabilized_params': stabilized_params
                }
            )
            
            # Обновляем solution_started_at
            await set_solution_started_at(zone_id)
            
            # Возвращаем зону в нормальный режим
            await set_zone_water_state(zone_id, WATER_STATE_NORMAL_RECIRC)
            
            return {
                'success': True,
                'state': WATER_STATE_NORMAL_RECIRC,
                'solution_started_at': solution_started_at.isoformat()
            }
        else:
            return {
                'success': True,
                'state': WATER_STATE_WATER_CHANGE_STABILIZE,
                'stabilizing': True,
                'elapsed_minutes': elapsed_minutes,
                'stabilize_minutes': stabilize_minutes
            }
    
    return {
        'success': True,
        'state': current_state
    }

