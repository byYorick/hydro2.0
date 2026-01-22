import asyncio
import json
import logging
import os
import httpx
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from common.utils.time import utcnow
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
from common.service_logs import send_service_log

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
COMMAND_REST_ERRORS = Counter("scheduler_command_rest_errors_total", "REST command errors from scheduler", ["error_type"])

# URL automation-engine для отправки команд
AUTOMATION_ENGINE_URL = os.getenv("AUTOMATION_ENGINE_URL", "http://automation-engine:9405")

# Временное хранилище последнего тика per zone (для sim-time пересечений)
_LAST_SCHEDULE_CHECKS: Dict[int, datetime] = {}


@dataclass(frozen=True)
class SimulationClock:
    real_start: datetime
    sim_start: datetime
    time_scale: float

    def now(self) -> datetime:
        real_now = utcnow().replace(tzinfo=None)
        elapsed = (real_now - self.real_start).total_seconds()
        return self.sim_start + timedelta(seconds=elapsed * self.time_scale)


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _to_naive_utc(parsed)


def _extract_simulation_clock(row: Dict[str, Any]) -> Optional[SimulationClock]:
    scenario = row.get("scenario") or {}
    sim_meta = scenario.get("simulation") or {}
    real_start = _parse_iso_datetime(sim_meta.get("real_started_at") or sim_meta.get("started_at"))
    sim_start = _parse_iso_datetime(sim_meta.get("sim_started_at") or sim_meta.get("sim_start_at"))
    if not real_start:
        created_at = row.get("created_at")
        if not created_at:
            return None
        real_start = _to_naive_utc(created_at)
    if not sim_start:
        sim_start = real_start

    time_scale = sim_meta.get("time_scale")
    if time_scale is None:
        duration_hours = row.get("duration_hours")
        real_minutes = sim_meta.get("real_duration_minutes")
        real_seconds = sim_meta.get("real_duration_seconds")
        if duration_hours and real_minutes:
            time_scale = (duration_hours * 60) / float(real_minutes)
        elif duration_hours and real_seconds:
            time_scale = (duration_hours * 3600) / float(real_seconds)

    try:
        time_scale_value = float(time_scale)
    except (TypeError, ValueError):
        return None
    if time_scale_value <= 0:
        return None

    return SimulationClock(
        real_start=real_start,
        sim_start=sim_start,
        time_scale=time_scale_value,
    )


def _get_last_check(zone_id: int, now_dt: datetime, sim_clock: Optional[SimulationClock]) -> datetime:
    last_check = _LAST_SCHEDULE_CHECKS.get(zone_id)
    if last_check is not None:
        return last_check
    delta_seconds = 60.0
    if sim_clock:
        delta_seconds *= sim_clock.time_scale
    return now_dt - timedelta(seconds=delta_seconds)


def _schedule_crossings(last_dt: datetime, now_dt: datetime, target: time) -> List[datetime]:
    if now_dt < last_dt:
        last_dt, now_dt = now_dt, last_dt
    start_date = last_dt.date()
    end_date = now_dt.date()
    days = (end_date - start_date).days
    crossings: List[datetime] = []
    for offset in range(days + 1):
        day = start_date + timedelta(days=offset)
        candidate = datetime.combine(day, target)
        if last_dt < candidate <= now_dt:
            crossings.append(candidate)
    return crossings


async def get_simulation_clocks(zone_ids: List[int]) -> Dict[int, SimulationClock]:
    if not zone_ids:
        return {}
    try:
        rows = await fetch(
            """
            SELECT DISTINCT ON (zone_id)
                zone_id,
                scenario,
                duration_hours,
                created_at
            FROM zone_simulations
            WHERE zone_id = ANY($1::int[]) AND status = 'running'
            ORDER BY zone_id, created_at DESC
            """,
            zone_ids,
        )
    except Exception as e:
        logger.warning(f"Failed to load simulation clocks: {e}")
        return {}
    clocks: Dict[int, SimulationClock] = {}
    for row in rows:
        clock = _extract_simulation_clock(row)
        if clock:
            clocks[row["zone_id"]] = clock
    return clocks


async def send_command_via_automation_engine(
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    params: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Отправить команду через automation-engine REST API.
    Scheduler не должен общаться с нодами напрямую, только через automation-engine.
    
    Args:
        zone_id: ID зоны
        node_uid: UID узла
        channel: Канал узла
        cmd: Команда
        params: Параметры команды
    
    Returns:
        True если команда успешно отправлена, False в противном случае
    """
    try:
        payload = {
            "zone_id": zone_id,
            "node_uid": node_uid,
            "channel": channel,
            "cmd": cmd,
        }
        if params:
            payload["params"] = params
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{AUTOMATION_ENGINE_URL}/scheduler/command",
                json=payload
            )
            
            if response.status_code == 200:
                logger.debug(
                    f"Scheduler command sent successfully: zone_id={zone_id}, node_uid={node_uid}, cmd={cmd}"
                )
                return True
            else:
                try:
                    error_msg = response.text
                except Exception:
                    error_msg = f"HTTP {response.status_code}"
                COMMAND_REST_ERRORS.labels(error_type=f"http_{response.status_code}").inc()
                logger.error(
                    f"Scheduler command failed: {response.status_code} - {error_msg}, "
                    f"zone_id={zone_id}, node_uid={node_uid}, cmd={cmd}"
                )
                return False
                
    except httpx.TimeoutException as e:
        COMMAND_REST_ERRORS.labels(error_type="timeout").inc()
        logger.error(f"Scheduler command timeout: {e}, zone_id={zone_id}, node_uid={node_uid}, cmd={cmd}")
        return False
    except httpx.RequestError as e:
        COMMAND_REST_ERRORS.labels(error_type="request_error").inc()
        logger.error(f"Scheduler command request error: {e}, zone_id={zone_id}, node_uid={node_uid}, cmd={cmd}")
        return False
    except Exception as e:
        COMMAND_REST_ERRORS.labels(error_type=type(e).__name__).inc()
        logger.error(f"Scheduler command error: {e}, zone_id={zone_id}, node_uid={node_uid}, cmd={cmd}", exc_info=True)
        return False


def _parse_time_spec(spec: str) -> Optional[time]:
    """Parse time spec like '08:00' or '14:30'."""
    try:
        parts = spec.split(":")
        if len(parts) == 2:
            return time(int(parts[0]), int(parts[1]))
    except Exception:
        pass
    return None


def _is_time_in_window(now: time, start_time: time, end_time: time) -> bool:
    """Check if time falls into a window, including midnight wrap."""
    if start_time == end_time:
        return True
    if start_time < end_time:
        return start_time <= now <= end_time
    return now >= start_time or now <= end_time


async def get_active_schedules() -> List[Dict[str, Any]]:
    """Fetch active schedules from effective targets (новая модель GrowCycle)."""
    # Получаем активные зоны
    zone_rows = await fetch(
        """
        SELECT z.id as zone_id
        FROM zones z
        WHERE z.status IN ('online', 'warning')
        """
    )
    
    if not zone_rows:
        ACTIVE_SCHEDULES.set(0)
        return []
    
    zone_ids = [row["zone_id"] for row in zone_rows]
    
    # Получаем effective targets через Laravel API
    try:
        from repositories.laravel_api_repository import LaravelApiRepository
        laravel_api = LaravelApiRepository()
        effective_targets_batch = await laravel_api.get_effective_targets_batch(zone_ids)
    except Exception as e:
        logger.error(f'Failed to get effective targets from Laravel API: {e}')
        ACTIVE_SCHEDULES.set(0)
        return []
    
    schedules: List[Dict[str, Any]] = []
    
    for zone_id in zone_ids:
        effective_targets = effective_targets_batch.get(zone_id)
        if not effective_targets or 'error' in effective_targets:
            continue
        
        targets = effective_targets.get('targets', {})
        if not isinstance(targets, dict):
            continue
        
        # Irrigation schedule из effective targets
        irrigation = targets.get("irrigation", {})
        if irrigation:
            # Используем interval_sec для создания расписания
            # Если есть явное расписание, используем его
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
        
        # Lighting schedule из effective targets
        lighting = targets.get("lighting", {})
        if lighting:
            # Используем photoperiod_hours и start_time для создания расписания
            photoperiod_hours = lighting.get("photoperiod_hours")
            start_time_str = lighting.get("start_time")
            
            if photoperiod_hours and start_time_str:
                start_t = _parse_time_spec(start_time_str)
                if start_t:
                    # Вычисляем end_time на основе photoperiod_hours
                    from datetime import timedelta
                    end_time_dt = datetime.combine(datetime.today(), start_t) + timedelta(hours=photoperiod_hours)
                    end_t = end_time_dt.time()
                    
                    schedules.append({
                        "zone_id": zone_id,
                        "type": "lighting",
                        "start_time": start_t,
                        "end_time": end_t,
                        "targets": targets,
                    })
            else:
                # Fallback на старый формат lighting_schedule
                lighting_schedule = targets.get("lighting_schedule")
                if lighting_schedule and isinstance(lighting_schedule, str):
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
    node_uid: str,
    channel: str
):
    """
    Мониторинг безопасности насоса - проверка на сухой ход.
    
    Через 3 секунды после запуска проверяет flow и останавливает насос
    при обнаружении сухого хода.
    Команды отправляются через automation-engine REST API.
    """
    # Ждем 3 секунды перед проверкой
    await asyncio.sleep(3)  # DRY_RUN_CHECK_DELAY_SEC
    
    # Проверяем защиту от сухого хода
    is_safe, error = await check_dry_run_protection(zone_id, pump_start_time)
    
    if not is_safe:
        # Отправляем команду остановки насоса через automation-engine
        await send_command_via_automation_engine(
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd="set_relay",
            params={"state": False}
        )
        
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
    zone_id: int, schedule: Dict[str, Any],
):
    """Execute irrigation schedule for zone with Water Flow Engine integration.
    Команды отправляются через automation-engine REST API."""
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
        
        # Get irrigation duration from targets (новая модель)
        targets = schedule.get("targets", {})
        irrigation = targets.get("irrigation", {})
        duration_sec = irrigation.get("duration_sec") or targets.get("irrigation_duration_sec", 60)
        duration_ms = max(0, int(duration_sec * 1000))
        
        # Create IRRIGATION_STARTED event
        irrigation_start_time = utcnow()
        await create_zone_event(
            zone_id,
            'IRRIGATION_STARTED',
            {
                'nodes_count': len(nodes),
                'duration_sec': duration_sec,
                'start_time': irrigation_start_time.isoformat()
            }
        )
        
        # Send irrigation commands через automation-engine
        monitoring_tasks = []  # Отслеживаем задачи для предотвращения утечек памяти
        for node_info in nodes:
            await send_command_via_automation_engine(
                zone_id=zone_id,
                node_uid=node_info['node_uid'],
                channel=node_info['channel'],
                cmd="run_pump",
                params={"duration_ms": duration_ms}
            )
            
            # Start async monitoring for dry run protection
            task = asyncio.create_task(
                monitor_pump_safety(
                    zone_id, irrigation_start_time,
                    node_info['node_uid'], node_info['channel']
                )
            )
            monitoring_tasks.append(task)
            
            # Добавляем обработку ошибок для предотвращения утечек
            def log_task_error(t):
                """Callback для логирования ошибок в задачах мониторинга."""
                try:
                    if t.done() and t.exception():
                        exc = t.exception()
                        logger.error(
                            f"Callback failure: Pump safety monitoring task failed for zone {zone_id}, "
                            f"node {node_info['node_uid']}, channel {node_info['channel']}: {exc}",
                            exc_info=True,
                            extra={
                                'zone_id': zone_id,
                                'node_uid': node_info['node_uid'],
                                'channel': node_info['channel'],
                                'error_type': type(exc).__name__,
                                'error_message': str(exc)
                            }
                        )
                        # Создаем событие для observability
                        asyncio.create_task(create_zone_event(
                            zone_id,
                            'PUMP_MONITORING_CALLBACK_FAILURE',
                            {
                                'node_uid': node_info['node_uid'],
                                'channel': node_info['channel'],
                                'error': str(exc),
                                'error_type': type(exc).__name__
                            }
                        ))
                except Exception as callback_error:
                    # Даже если сам callback упал, логируем это
                    logger.critical(
                        f"Critical: Callback error handler itself failed: {callback_error}",
                        exc_info=True,
                        extra={
                            'zone_id': zone_id,
                            'original_task': str(t),
                            'callback_error': str(callback_error)
                        }
                    )
            
            task.add_done_callback(log_task_error)
        
        SCHEDULE_EXECUTIONS.labels(zone_id=zone_id, task_type="irrigation").inc()
        
        # Wait for irrigation to complete (approximate)
        await asyncio.sleep(min(duration_sec, 10))  # Max wait 10 seconds for async check
        
        # Calculate volume and create IRRIGATION_FINISHED event
        irrigation_end_time = utcnow()
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
        logger.error(
            f"Callback failure: Irrigation schedule execution failed for zone {zone_id}: {e}",
            exc_info=True,
            extra={
                'zone_id': zone_id,
                'task_name': task_name,
                'error_type': type(e).__name__,
                'error_message': str(e)
            }
        )
        await create_scheduler_log(task_name, "failed", {"zone_id": zone_id, "error": str(e)})


async def execute_lighting_schedule(
    zone_id: int, schedule: Dict[str, Any], now_time: Optional[time] = None,
):
    """Execute lighting schedule for zone (on/off based on time).
    Команды отправляются через automation-engine REST API."""
    task_name = f"lighting_zone_{zone_id}"
    try:
        await create_scheduler_log(task_name, "running", {"zone_id": zone_id, "type": "lighting"})
        nodes = await get_zone_nodes_for_type(zone_id, "light")
        if not nodes:
            await create_scheduler_log(task_name, "failed", {"zone_id": zone_id, "error": "no_nodes"})
            return
        now = now_time or datetime.now().time()
        start_time = schedule.get("start_time")
        end_time = schedule.get("end_time")
        if not start_time or not end_time:
            await create_scheduler_log(task_name, "failed", {"zone_id": zone_id, "error": "no_time_range"})
            return
        # Check if current time is within lighting window (handles midnight wrap)
        should_be_on = _is_time_in_window(now, start_time, end_time)
        cmd = "light_on" if should_be_on else "light_off"
        for node_info in nodes:
            await send_command_via_automation_engine(
                zone_id=zone_id,
                node_uid=node_info['node_uid'],
                channel=node_info['channel'],
                cmd=cmd
            )
        SCHEDULE_EXECUTIONS.labels(zone_id=zone_id, task_type="lighting").inc()
        await create_scheduler_log(task_name, "completed", {"zone_id": zone_id, "command": cmd, "nodes_count": len(nodes)})
    except Exception as e:
        logger.error(
            f"Callback failure: Lighting schedule execution failed for zone {zone_id}: {e}",
            exc_info=True,
            extra={
                'zone_id': zone_id,
                'task_name': task_name,
                'error_type': type(e).__name__,
                'error_message': str(e)
            }
        )
        await create_scheduler_log(task_name, "failed", {"zone_id": zone_id, "error": str(e)})


async def check_water_changes(mqtt_client: MqttClient):
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
                    await execute_water_change(zone_id, mqtt_client=mqtt_client, gh_uid=gh_uid)
                elif current_state in [
                    WATER_STATE_WATER_CHANGE_DRAIN,
                    WATER_STATE_WATER_CHANGE_FILL,
                    WATER_STATE_WATER_CHANGE_STABILIZE
                ]:
                    # Продолжаем смену воды
                    await execute_water_change(zone_id, mqtt_client=mqtt_client, gh_uid=gh_uid)
        except Exception as e:
            logger.error(
                f"Callback failure: Error checking water change for zone {zone_id}: {e}",
                exc_info=True,
                extra={
                    'zone_id': zone_id,
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                }
            )
            # Создаем событие для observability
            try:
                await create_zone_event(
                    zone_id,
                    'WATER_CHANGE_CHECK_FAILURE',
                    {
                        'error': str(e),
                        'error_type': type(e).__name__
                    }
                )
            except Exception as event_error:
                logger.warning(
                    f"Failed to create zone event for water change check failure: {event_error}",
                    extra={'zone_id': zone_id, 'original_error': str(e)}
                )


async def check_and_execute_schedules(mqtt_client: MqttClient):
    """Check schedules and execute tasks if time matches.
    Команды отправляются через automation-engine REST API."""
    schedules = await get_active_schedules()
    zone_ids = sorted({schedule["zone_id"] for schedule in schedules})
    simulation_clocks = await get_simulation_clocks(zone_ids)
    real_now = datetime.now()
    # Group by zone and schedule signature to avoid duplicates within a tick
    executed: set = set()
    zone_now: Dict[int, datetime] = {}
    zone_last: Dict[int, datetime] = {}
    for schedule in schedules:
        zone_id = schedule["zone_id"]
        task_type = schedule["type"]
        key = (
            zone_id,
            task_type,
            schedule.get("time"),
            schedule.get("start_time"),
            schedule.get("end_time"),
        )
        if key in executed:
            continue
        if zone_id not in zone_now:
            sim_clock = simulation_clocks.get(zone_id)
            now_dt = sim_clock.now() if sim_clock else real_now
            zone_now[zone_id] = now_dt
            zone_last[zone_id] = _get_last_check(zone_id, now_dt, sim_clock)
        now_dt = zone_now[zone_id]
        last_dt = zone_last[zone_id]
        now_time = now_dt.time()
        if task_type == "irrigation":
            # Check if current time matches schedule time (within 1 minute window)
            schedule_time = schedule.get("time")
            if schedule_time:
                crossings = _schedule_crossings(last_dt, now_dt, schedule_time)
                for _ in crossings:
                    await execute_irrigation_schedule(zone_id, schedule)
                if crossings:
                    executed.add(key)
        elif task_type == "lighting":
            # Lighting is checked every cycle, execute if needed
            await execute_lighting_schedule(zone_id, schedule, now_time=now_time)
            executed.add(key)
    for zone_id, now_dt in zone_now.items():
        _LAST_SCHEDULE_CHECKS[zone_id] = now_dt
    
    # Проверяем смены воды
    await check_water_changes(mqtt_client)


async def main():
    s = get_settings()
    mqtt = MqttClient(client_id_suffix="-scheduler")
    try:
        mqtt.start()
    except Exception as e:
        logger.critical(f"Failed to start MQTT client: {e}. Exiting.", exc_info=True)
        send_service_log(
            service="scheduler",
            level="critical",
            message=f"Failed to start MQTT client: {e}",
            context={"error": str(e)},
        )
        # Exit on critical configuration errors
        raise
    
    start_http_server(9402)  # Prometheus metrics
    send_service_log(
        service="scheduler",
        level="info",
        message="Scheduler service started",
        context={"port": 9402},
    )

    while True:
        try:
            await check_and_execute_schedules(mqtt)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down")
            break
        except Exception as e:
            logger.exception(f"Error in scheduler main loop: {e}")
            send_service_log(
                service="scheduler",
                level="error",
                message="Error in scheduler main loop",
                context={"error": str(e)},
            )
            # Sleep before retrying to avoid tight error loops
            await asyncio.sleep(60)
        # Check schedules every minute
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
