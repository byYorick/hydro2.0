import asyncio
import json
import logging
import os
from datetime import datetime, time
from typing import Optional, Dict, Any, List
from common.env import get_settings
from common.mqtt import MqttClient
from common.db import fetch, execute, create_scheduler_log, create_zone_event
from prometheus_client import Counter, Gauge, start_http_server
from common.water_flow import (
    check_water_level,
    check_flow,
    calculate_irrigation_volume,
    ensure_water_level_alert,
    ensure_no_flow_alert,
    check_dry_run_protection,
)
from common.water_cycle import (
    check_water_change_required,
    execute_water_change,
    get_zone_water_state,
    WATER_STATE_NORMAL_RECIRC,
    WATER_STATE_WATER_CHANGE_DRAIN,
    WATER_STATE_WATER_CHANGE_FILL,
    WATER_STATE_WATER_CHANGE_STABILIZE,
)

# Настройка логирования
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Явно указываем stdout для Docker
)

logger = logging.getLogger(__name__)

SCHEDULE_EXECUTIONS = Counter("schedule_executions_total", "Scheduled tasks executed", ["zone_id", "task_type"])
ACTIVE_SCHEDULES = Gauge("active_schedules", "Number of active schedules")


def _parse_time_spec(spec: str) -> Optional[time]:
    """Parse time spec like '08:00' or '14:30'."""
    try:
        parts = spec.split(":")
        if len(parts) == 2:
            return time(int(parts[0]), int(parts[1]))
    except Exception:
        pass
    return None


async def get_active_schedules() -> List[Dict[str, Any]]:
    """Fetch active schedules from recipe phases or zone configs."""
    # MVP: simple schedules from recipe_phases.targets (irrigation_schedule, lighting_schedule)
    # Example targets: {"ph": 6.5, "ec": 1.8, "irrigation_schedule": ["08:00", "14:00", "20:00"], "lighting_schedule": "06:00-22:00"}
    rows = await fetch(
        """
        SELECT zri.zone_id, zri.current_phase_index, rp.targets, z.status
        FROM zone_recipe_instances zri
        JOIN recipe_phases rp ON rp.recipe_id = zri.recipe_id AND rp.phase_index = zri.current_phase_index
        JOIN zones z ON z.id = zri.zone_id
        WHERE z.status IN ('online', 'warning')
        """
    )
    schedules: List[Dict[str, Any]] = []
    for row in rows:
        targets = row["targets"] or {}
        if not isinstance(targets, dict):
            continue
        zone_id = row["zone_id"]
        # Irrigation schedule
        irrigation_schedule = targets.get("irrigation_schedule")
        if irrigation_schedule:
            if isinstance(irrigation_schedule, list):
                for time_spec in irrigation_schedule:
                    t = _parse_time_spec(str(time_spec))
                    if t:
                        schedules.append({
                            "zone_id": zone_id,
                            "type": "irrigation",
                            "time": t,
                            "targets": targets,
                        })
            elif isinstance(irrigation_schedule, str):
                t = _parse_time_spec(irrigation_schedule)
                if t:
                    schedules.append({
                        "zone_id": zone_id,
                        "type": "irrigation",
                        "time": t,
                        "targets": targets,
                    })
        # Lighting schedule
        lighting_schedule = targets.get("lighting_schedule")
        if lighting_schedule and isinstance(lighting_schedule, str):
            # Parse "06:00-22:00"
            parts = lighting_schedule.split("-")
            if len(parts) == 2:
                start_t = _parse_time_spec(parts[0].strip())
                end_t = _parse_time_spec(parts[1].strip())
                if start_t and end_t:
                    schedules.append({
                        "zone_id": zone_id,
                        "type": "lighting",
                        "start_time": start_t,
                        "end_time": end_t,
                        "targets": targets,
                    })
    ACTIVE_SCHEDULES.set(len(schedules))
    return schedules


async def get_zone_nodes_for_type(zone_id: int, node_type: str) -> List[Dict[str, Any]]:
    """Fetch nodes of specific type for zone."""
    rows = await fetch(
        """
        SELECT n.id, n.uid, n.type, nc.channel
        FROM nodes n
        LEFT JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1 AND n.type = $2 AND n.status = 'online'
        """,
        zone_id, node_type,
    )
    result: List[Dict[str, Any]] = []
    for row in rows:
        result.append({
            "node_id": row["id"],
            "node_uid": row["uid"],
            "type": row["type"],
            "channel": row["channel"] or "default",
        })
    return result


async def get_gh_uid_for_zone(zone_id: int) -> Optional[str]:
    """Get greenhouse uid for zone."""
    rows = await fetch(
        """
        SELECT g.uid
        FROM zones z
        JOIN greenhouses g ON g.id = z.greenhouse_id
        WHERE z.id = $1
        """,
        zone_id,
    )
    if rows and len(rows) > 0:
        return rows[0]["uid"]
    return None


async def monitor_pump_safety(
    zone_id: int,
    pump_start_time: datetime,
    mqtt: MqttClient,
    gh_uid: str,
    node_uid: str,
    channel: str
):
    """
    Мониторинг безопасности насоса - проверка на сухой ход.
    
    Через 3 секунды после запуска проверяет flow и останавливает насос
    при обнаружении сухого хода.
    """
    # Ждем 3 секунды перед проверкой
    await asyncio.sleep(3)  # DRY_RUN_CHECK_DELAY_SEC
    
    # Проверяем защиту от сухого хода
    is_safe, error = await check_dry_run_protection(zone_id, pump_start_time)
    
    if not is_safe:
        # Отправляем команду остановки насоса
        payload = {"cmd": "stop"}
        topic = f"hydro/{gh_uid}/zn-{zone_id}/{node_uid}/{channel}/command"
        mqtt.publish_json(topic, payload, qos=1, retain=False)
        
        # Создаем событие остановки насоса
        await create_zone_event(
            zone_id,
            'PUMP_STOPPED',
            {
                'reason': 'dry_run_detected',
                'error': error,
                'node_uid': node_uid,
                'channel': channel,
                'pump_start_time': pump_start_time.isoformat()
            }
        )
        
        # Обновляем scheduler log
        await create_scheduler_log(
            f"irrigation_zone_{zone_id}",
            "failed",
            {
                "zone_id": zone_id,
                "error": "dry_run_detected",
                "error_message": error
            }
        )


async def execute_irrigation_schedule(
    zone_id: int, mqtt: MqttClient, gh_uid: str, schedule: Dict[str, Any],
):
    """Execute irrigation schedule for zone with Water Flow Engine integration."""
    task_name = f"irrigation_zone_{zone_id}"
    try:
        await create_scheduler_log(task_name, "running", {"zone_id": zone_id, "type": "irrigation"})
        
        # Check water level before irrigation
        water_level_ok, water_level = await check_water_level(zone_id)
        if water_level is not None:
            await ensure_water_level_alert(zone_id, water_level)
        
        if not water_level_ok:
            await create_scheduler_log(
                task_name, "failed", 
                {"zone_id": zone_id, "error": "water_level_low", "level": water_level}
            )
            return
        
        nodes = await get_zone_nodes_for_type(zone_id, "irrig")
        if not nodes:
            await create_scheduler_log(task_name, "failed", {"zone_id": zone_id, "error": "no_nodes"})
            return
        
        # Get irrigation duration from targets
        targets = schedule.get("targets", {})
        duration_sec = targets.get("irrigation_duration_sec", 60)
        
        # Create IRRIGATION_STARTED event
        irrigation_start_time = datetime.utcnow()
        await create_zone_event(
            zone_id,
            'IRRIGATION_STARTED',
            {
                'nodes_count': len(nodes),
                'duration_sec': duration_sec,
                'start_time': irrigation_start_time.isoformat()
            }
        )
        
        # Send irrigation commands
        for node_info in nodes:
            payload = {"cmd": "irrigate", "params": {"duration_sec": duration_sec}}
            topic = f"hydro/{gh_uid}/zn-{zone_id}/{node_info['node_uid']}/{node_info['channel']}/command"
            mqtt.publish_json(topic, payload, qos=1, retain=False)
            
            # Start async monitoring for dry run protection
            asyncio.create_task(
                monitor_pump_safety(
                    zone_id, irrigation_start_time, mqtt, gh_uid,
                    node_info['node_uid'], node_info['channel']
                )
            )
        
        SCHEDULE_EXECUTIONS.labels(zone_id=zone_id, task_type="irrigation").inc()
        
        # Wait for irrigation to complete (approximate)
        await asyncio.sleep(min(duration_sec, 10))  # Max wait 10 seconds for async check
        
        # Calculate volume and create IRRIGATION_FINISHED event
        irrigation_end_time = datetime.utcnow()
        volume = await calculate_irrigation_volume(zone_id, irrigation_start_time, irrigation_end_time)
        
        # Check flow after irrigation
        flow_ok, flow_value = await check_flow(zone_id)
        if not flow_ok:
            await ensure_no_flow_alert(zone_id, flow_value, 0.1)
        
        await create_zone_event(
            zone_id,
            'IRRIGATION_FINISHED',
            {
                'nodes_count': len(nodes),
                'duration_sec': duration_sec,
                'actual_duration_sec': (irrigation_end_time - irrigation_start_time).total_seconds(),
                'volume_l': volume,
                'flow_value': flow_value,
                'start_time': irrigation_start_time.isoformat(),
                'end_time': irrigation_end_time.isoformat()
            }
        )
        
        await create_scheduler_log(
            task_name, "completed", 
            {"zone_id": zone_id, "nodes_count": len(nodes), "volume_l": volume}
        )
    except Exception as e:
        await create_scheduler_log(task_name, "failed", {"zone_id": zone_id, "error": str(e)})


async def execute_lighting_schedule(
    zone_id: int, mqtt: MqttClient, gh_uid: str, schedule: Dict[str, Any],
):
    """Execute lighting schedule for zone (on/off based on time)."""
    task_name = f"lighting_zone_{zone_id}"
    try:
        await create_scheduler_log(task_name, "running", {"zone_id": zone_id, "type": "lighting"})
        nodes = await get_zone_nodes_for_type(zone_id, "light")
        if not nodes:
            await create_scheduler_log(task_name, "failed", {"zone_id": zone_id, "error": "no_nodes"})
            return
        now = datetime.now().time()
        start_time = schedule.get("start_time")
        end_time = schedule.get("end_time")
        if not start_time or not end_time:
            await create_scheduler_log(task_name, "failed", {"zone_id": zone_id, "error": "no_time_range"})
            return
        # Check if current time is within lighting window
        should_be_on = start_time <= now <= end_time
        cmd = "light_on" if should_be_on else "light_off"
        for node_info in nodes:
            payload = {"cmd": cmd}
            topic = f"hydro/{gh_uid}/zn-{zone_id}/{node_info['node_uid']}/{node_info['channel']}/command"
            mqtt.publish_json(topic, payload, qos=1, retain=False)
        SCHEDULE_EXECUTIONS.labels(zone_id=zone_id, task_type="lighting").inc()
        await create_scheduler_log(task_name, "completed", {"zone_id": zone_id, "command": cmd, "nodes_count": len(nodes)})
    except Exception as e:
        await create_scheduler_log(task_name, "failed", {"zone_id": zone_id, "error": str(e)})


async def check_water_changes(mqtt: MqttClient):
    """Проверить и выполнить смены воды для всех активных зон."""
    # Получаем все активные зоны
    rows = await fetch(
        """
        SELECT id
        FROM zones
        WHERE status IN ('online', 'warning')
        """
    )
    
    for row in rows:
        zone_id = row["id"]
        
        try:
            # Проверяем, требуется ли смена воды
            required, reason = await check_water_change_required(zone_id)
            
            if required:
                gh_uid = await get_gh_uid_for_zone(zone_id)
                if not gh_uid:
                    continue
                
                # Получаем текущее состояние
                current_state = await get_zone_water_state(zone_id)
                
                if current_state == WATER_STATE_NORMAL_RECIRC:
                    # Начинаем смену воды
                    logger.info(f"Zone {zone_id}: Starting water change - {reason}")
                    await execute_water_change(zone_id, mqtt, gh_uid)
                elif current_state in [
                    WATER_STATE_WATER_CHANGE_DRAIN,
                    WATER_STATE_WATER_CHANGE_FILL,
                    WATER_STATE_WATER_CHANGE_STABILIZE
                ]:
                    # Продолжаем смену воды
                    await execute_water_change(zone_id, mqtt, gh_uid)
        except Exception as e:
            logger.error(f"Zone {zone_id}: Error checking water change: {e}")


async def check_and_execute_schedules(mqtt: MqttClient):
    """Check schedules and execute tasks if time matches."""
    schedules = await get_active_schedules()
    now = datetime.now().time()
    # Group by zone and type
    executed: set = set()  # (zone_id, type) to avoid duplicates
    for schedule in schedules:
        zone_id = schedule["zone_id"]
        task_type = schedule["type"]
        key = (zone_id, task_type)
        if key in executed:
            continue
        gh_uid = await get_gh_uid_for_zone(zone_id)
        if not gh_uid:
            continue
        if task_type == "irrigation":
            # Check if current time matches schedule time (within 1 minute window)
            schedule_time = schedule.get("time")
            if schedule_time:
                time_diff = abs(
                    (now.hour * 60 + now.minute) - (schedule_time.hour * 60 + schedule_time.minute)
                )
                if time_diff <= 1:
                    await execute_irrigation_schedule(zone_id, mqtt, gh_uid, schedule)
                    executed.add(key)
        elif task_type == "lighting":
            # Lighting is checked every cycle, execute if needed
            await execute_lighting_schedule(zone_id, mqtt, gh_uid, schedule)
            executed.add(key)
    
    # Проверяем смены воды
    await check_water_changes(mqtt)


async def main():
    s = get_settings()
    mqtt = MqttClient(client_id_suffix="-scheduler")
    try:
        mqtt.start()
    except Exception as e:
        logger.critical(f"Failed to start MQTT client: {e}. Exiting.", exc_info=True)
        # Exit on critical configuration errors
        raise
    
    start_http_server(9402)  # Prometheus metrics

    while True:
        try:
            await check_and_execute_schedules(mqtt)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down")
            break
        except Exception as e:
            logger.exception(f"Error in scheduler main loop: {e}")
            # Sleep before retrying to avoid tight error loops
            await asyncio.sleep(60)
        # Check schedules every minute
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())

