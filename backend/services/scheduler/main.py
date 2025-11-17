import asyncio
import json
from datetime import datetime, time
from typing import Optional, Dict, Any, List
from common.env import get_settings
from common.mqtt import MqttClient
from common.db import fetch, execute
from prometheus_client import Counter, Gauge, start_http_server

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
        SELECT n.id, n.uid, n.type, nc.name as channel_name, nc.channel_id
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
            "channel": row["channel_name"] or row["channel_id"] or "default",
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


async def execute_irrigation_schedule(
    zone_id: int, mqtt: MqttClient, gh_uid: str, schedule: Dict[str, Any],
):
    """Execute irrigation schedule for zone."""
    nodes = await get_zone_nodes_for_type(zone_id, "irrigation")
    if not nodes:
        return
    for node_info in nodes:
        payload = {"cmd": "irrigate", "params": {"duration_sec": 60, "amount_ml": 100}}
        topic = f"hydro/{gh_uid}/zn-{zone_id}/{node_info['node_uid']}/{node_info['channel']}/command"
        mqtt.publish_json(topic, payload, qos=1, retain=False)
    SCHEDULE_EXECUTIONS.labels(zone_id=zone_id, task_type="irrigation").inc()


async def execute_lighting_schedule(
    zone_id: int, mqtt: MqttClient, gh_uid: str, schedule: Dict[str, Any],
):
    """Execute lighting schedule for zone (on/off based on time)."""
    nodes = await get_zone_nodes_for_type(zone_id, "lighting")
    if not nodes:
        return
    now = datetime.now().time()
    start_time = schedule.get("start_time")
    end_time = schedule.get("end_time")
    if not start_time or not end_time:
        return
    # Check if current time is within lighting window
    should_be_on = start_time <= now <= end_time
    cmd = "light_on" if should_be_on else "light_off"
    for node_info in nodes:
        payload = {"cmd": cmd}
        topic = f"hydro/{gh_uid}/zn-{zone_id}/{node_info['node_uid']}/{node_info['channel']}/command"
        mqtt.publish_json(topic, payload, qos=1, retain=False)
    SCHEDULE_EXECUTIONS.labels(zone_id=zone_id, task_type="lighting").inc()


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


async def main():
    s = get_settings()
    mqtt = MqttClient(client_id_suffix="-scheduler")
    mqtt.start()
    start_http_server(9402)  # Prometheus metrics

    while True:
        try:
            await check_and_execute_schedules(mqtt)
        except Exception:
            pass
        # Check schedules every minute
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())

