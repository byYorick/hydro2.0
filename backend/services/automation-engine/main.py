import asyncio
import json
import httpx
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from common.env import get_settings
from common.mqtt import MqttClient
from common.db import fetch, execute, create_zone_event, create_ai_log
from prometheus_client import Counter, Histogram, start_http_server

logger = logging.getLogger(__name__)
from recipe_utils import calculate_current_phase, advance_phase, get_phase_targets

# Metrics for error tracking
LOOP_ERRORS = Counter("automation_loop_errors_total", "Errors in automation main loop", ["error_type"])
CONFIG_FETCH_ERRORS = Counter("config_fetch_errors_total", "Errors fetching config from Laravel", ["error_type"])
CONFIG_FETCH_SUCCESS = Counter("config_fetch_success_total", "Successful config fetches from Laravel")
MQTT_PUBLISH_ERRORS = Counter("mqtt_publish_errors_total", "MQTT publish errors", ["error_type"])
from common.water_flow import (
    check_water_level,
    ensure_water_level_alert,
    ensure_no_flow_alert,
)
# tick_recirculation moved to irrigation_controller
from common.pump_safety import can_run_pump
from light_controller import check_and_control_lighting
from climate_controller import check_and_control_climate
from irrigation_controller import check_and_control_irrigation, check_and_control_recirculation
from health_monitor import calculate_zone_health, update_zone_health_in_db
from correction_cooldown import should_apply_correction, record_correction

ZONE_CHECKS = Counter("zone_checks_total", "Zone automation checks")
COMMANDS_SENT = Counter("automation_commands_sent_total", "Commands sent by automation", ["zone_id", "metric"])
CHECK_LAT = Histogram("zone_check_seconds", "Zone check duration seconds")


def _extract_gh_uid_from_config(cfg: Dict[str, Any]) -> Optional[str]:
    """Extract greenhouse uid from config."""
    # Config structure: {"greenhouses": [{"uid": "...", ...}]}
    gh_list = cfg.get("greenhouses", [])
    if gh_list and isinstance(gh_list, list):
        return gh_list[0].get("uid")
    return None


async def get_zone_recipe_and_targets(zone_id: int) -> Optional[Dict[str, Any]]:
    """Fetch active recipe phase and targets for zone."""
    rows = await fetch(
        """
        SELECT zri.zone_id, zri.current_phase_index, rp.targets, rp.name as phase_name
        FROM zone_recipe_instances zri
        JOIN recipe_phases rp ON rp.recipe_id = zri.recipe_id AND rp.phase_index = zri.current_phase_index
        WHERE zri.zone_id = $1
        """,
        zone_id,
    )
    if rows and len(rows) > 0:
        return {
            "zone_id": rows[0]["zone_id"],
            "phase_index": rows[0]["current_phase_index"],
            "targets": rows[0]["targets"],
            "phase_name": rows[0]["phase_name"],
        }
    return None


async def get_zone_telemetry_last(zone_id: int) -> Dict[str, Optional[float]]:
    """Fetch last telemetry values for zone."""
    rows = await fetch(
        """
        SELECT metric_type, value
        FROM telemetry_last
        WHERE zone_id = $1
        """,
        zone_id,
    )
    result: Dict[str, Optional[float]] = {}
    for row in rows:
        result[row["metric_type"]] = row["value"]
    return result


async def get_zone_nodes(zone_id: int) -> Dict[str, Dict[str, Any]]:
    """Fetch nodes for zone, keyed by type and channel."""
    rows = await fetch(
        """
        SELECT n.id, n.uid, n.type, nc.channel
        FROM nodes n
        LEFT JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1 AND n.status = 'online'
        """,
        zone_id,
    )
    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        node_type = row["type"]
        channel = row["channel"] or "default"
        key = f"{node_type}:{channel}"
        if key not in result:
            result[key] = {
                "node_id": row["id"],
                "node_uid": row["uid"],
                "type": node_type,
                "channel": channel,
            }
    return result


async def get_zone_capabilities(zone_id: int) -> Dict[str, bool]:
    """Fetch zone capabilities from database."""
    rows = await fetch(
        """
        SELECT capabilities
        FROM zones
        WHERE id = $1
        """,
        zone_id,
    )
    if rows and len(rows) > 0 and rows[0]["capabilities"]:
        return rows[0]["capabilities"]
    # Default capabilities (all False if not set)
    return {
        "ph_control": False,
        "ec_control": False,
        "climate_control": False,
        "light_control": False,
        "irrigation_control": False,
        "recirculation": False,
        "flow_sensor": False,
    }


async def publish_correction_command(
    mqtt: MqttClient,
    gh_uid: str,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    params: Optional[Dict[str, Any]] = None,
) -> bool:
    """Publish command via MQTT for zone automation."""
    try:
        if not mqtt.is_connected():
            error_type = "not_connected"
            MQTT_PUBLISH_ERRORS.labels(error_type=error_type).inc()
            logger.error(f"Zone {zone_id}: Cannot publish command - MQTT not connected")
            return False
        
        payload = {"cmd": cmd, **(({"params": params}) if params else {})}
        topic = f"hydro/{gh_uid}/zn-{zone_id}/{node_uid}/{channel}/command"
        mqtt.publish_json(topic, payload, qos=1, retain=False)
        COMMANDS_SENT.labels(zone_id=zone_id, metric=cmd).inc()
        return True
    except Exception as e:
        error_type = type(e).__name__
        MQTT_PUBLISH_ERRORS.labels(error_type=error_type).inc()
        logger.error(f"Zone {zone_id}: Failed to publish command {cmd} to {topic}: {e}", exc_info=True)
        return False


async def check_phase_transitions(zone_id: int):
    """Check and advance phases if needed based on elapsed time."""
    phase_calc = await calculate_current_phase(zone_id)
    if not phase_calc:
        return

    if phase_calc.get("should_transition") and phase_calc["target_phase_index"] > phase_calc["phase_index"]:
        # Advance to next phase
        new_phase_index = phase_calc["target_phase_index"]
        success = await advance_phase(zone_id, new_phase_index)
        if success:
            # Create zone event for phase transition
            await create_zone_event(
                zone_id,
                'PHASE_TRANSITION',
                {
                    'from_phase': phase_calc["phase_index"],
                    'to_phase': new_phase_index
                }
            )


async def check_and_correct_zone(zone_id: int, mqtt: MqttClient, gh_uid: str, cfg: Dict[str, Any]):
    """Check zone telemetry against targets and send correction commands."""
    with CHECK_LAT.time():
        ZONE_CHECKS.inc()

        # Check phase transitions first
        await check_phase_transitions(zone_id)

        # Get recipe phase and targets
        recipe_info = await get_zone_recipe_and_targets(zone_id)
        if not recipe_info or not recipe_info.get("targets"):
            return
        targets = recipe_info["targets"]
        if not isinstance(targets, dict):
            return
        # Get current telemetry
        telemetry = await get_zone_telemetry_last(zone_id)
        # Get nodes for zone
        nodes = await get_zone_nodes(zone_id)
        # Get zone capabilities
        capabilities = await get_zone_capabilities(zone_id)
        
        # Check water level before any dosing/pumping operations
        water_level_ok, water_level = await check_water_level(zone_id)
        if water_level is not None:
            await ensure_water_level_alert(zone_id, water_level)
        
        # Light Controller (первый согласно ZONE_LOGIC_FLOW.md раздел 2.3)
        if capabilities.get("light_control", False):
            light_cmd = await check_and_control_lighting(zone_id, targets, datetime.now())
        if light_cmd:
            # Создаем событие
            if light_cmd.get('event_type'):
                await create_zone_event(zone_id, light_cmd['event_type'], light_cmd.get('event_details', {}))
            # Отправляем команду
            await publish_correction_command(
                mqtt, gh_uid, zone_id,
                light_cmd['node_uid'], light_cmd['channel'],
                light_cmd['cmd'], light_cmd.get('params'),
            )
        
        # Climate Controller (после Light, перед Irrigation согласно ZONE_LOGIC_FLOW.md)
        # Получаем команды от Climate Controller
        if capabilities.get("climate_control", False):
            climate_commands = await check_and_control_climate(zone_id, targets, telemetry)
        else:
            climate_commands = []
        for cmd in climate_commands:
            if cmd.get('event_type'):
                # Создаем событие
                await create_zone_event(zone_id, cmd['event_type'], cmd.get('event_details', {}))
            # Отправляем команду
            await publish_correction_command(
                mqtt, gh_uid, zone_id,
                cmd['node_uid'], cmd['channel'],
                cmd['cmd'], cmd.get('params'),
            )
        
        # Irrigation Controller (после Climate, перед pH согласно ZONE_LOGIC_FLOW.md)
        # Проверяем, нужно ли запустить полив по интервалу
        if capabilities.get("irrigation_control", False):
            irrigation_cmd = await check_and_control_irrigation(zone_id, targets, telemetry)
        else:
            irrigation_cmd = None
        
        # Проверяем безопасность перед запуском насоса
        if irrigation_cmd:
            pump_channel = irrigation_cmd.get('channel', 'default')
            can_run, error_msg = await can_run_pump(zone_id, pump_channel)
            if not can_run:
                logger.warning(f"Zone {zone_id}: Cannot run irrigation pump {pump_channel}: {error_msg}")
                irrigation_cmd = None
        
        if irrigation_cmd:
            # Создаем событие
            if irrigation_cmd.get('event_type'):
                await create_zone_event(zone_id, irrigation_cmd['event_type'], irrigation_cmd.get('event_details', {}))
            # Отправляем команду
            await publish_correction_command(
                mqtt, gh_uid, zone_id,
                irrigation_cmd['node_uid'], irrigation_cmd['channel'],
                irrigation_cmd['cmd'], irrigation_cmd.get('params'),
            )
        
        # Recirculation Controller (после Irrigation Controller) - используем новую логику с учётом NC-насоса
        if capabilities.get("recirculation", False):
            recirculation_cmd = await check_and_control_recirculation(zone_id, targets, telemetry)
        else:
            recirculation_cmd = None
        if recirculation_cmd:
            # Создаем событие
            if recirculation_cmd.get('event_type'):
                await create_zone_event(zone_id, recirculation_cmd['event_type'], recirculation_cmd.get('event_details', {}))
            # Отправляем команду
            await publish_correction_command(
                mqtt, gh_uid, zone_id,
                recirculation_cmd['node_uid'], recirculation_cmd['channel'],
                recirculation_cmd['cmd'], recirculation_cmd.get('params'),
            )
        
        # Check pH target (only if ph_control capability is enabled)
        if capabilities.get("ph_control", False):
            ph_target = targets.get("ph")
            ph_current = telemetry.get("ph")
            if ph_target is not None and ph_current is not None:
                ph_target_val = float(ph_target) if isinstance(ph_target, (int, float, str)) else None
                ph_current_val = float(ph_current) if isinstance(ph_current, (int, float)) else None
                if ph_target_val is not None and ph_current_val is not None:
                    # Simple rule: if pH is too low (diff > 0.2), add base; if too high (diff < -0.2), add acid
                    diff = ph_current_val - ph_target_val
                    if abs(diff) > 0.2:
                        # Проверяем cooldown и анализ тренда перед корректировкой
                        should_correct, reason = await should_apply_correction(
                            zone_id, "ph", ph_current_val, ph_target_val, diff
                        )
                        
                        if not should_correct:
                            logger.info(f"Zone {zone_id}: pH correction skipped - {reason}")
                            # Создаем событие о пропуске корректировки
                            await create_zone_event(
                                zone_id,
                                'PH_CORRECTION_SKIPPED',
                                {
                                    'current_ph': ph_current_val,
                                    'target_ph': ph_target_val,
                                    'diff': diff,
                                    'reason': reason
                                }
                            )
                        # Check water level before dosing
                        elif should_correct and water_level_ok:
                            # Find irrigation node for pH correction
                            irrig_node = None
                            for key, node_info in nodes.items():
                                if node_info["type"] == "irrig":
                                    irrig_node = node_info
                                    break
                            if irrig_node:
                                correction_type = "add_base" if diff < -0.2 else "add_acid"
                                await publish_correction_command(
                            mqtt, gh_uid, zone_id,
                            irrig_node["node_uid"], irrig_node["channel"],
                            "adjust_ph", {"amount": abs(diff) * 10, "type": correction_type},
                        )
                                # Записываем информацию о корректировке
                                await record_correction(zone_id, "ph", {
                                    "correction_type": correction_type,
                                    "current_ph": ph_current_val,
                                    "target_ph": ph_target_val,
                                    "diff": diff,
                                    "reason": reason
                                })
                                # Create zone events for pH correction
                                await create_zone_event(
                                    zone_id,
                                    'PH_CORRECTED',
                                    {
                                        'correction_type': correction_type,
                                        'current_ph': ph_current_val,
                                        'target_ph': ph_target_val,
                                        'diff': diff,
                                        'dose_ml': abs(diff) * 10
                                    }
                                )
                                # Also create DOSING event for compatibility
                                await create_zone_event(
                                    zone_id,
                                    'DOSING',
                                    {
                                        'type': 'ph_correction',
                                        'correction_type': correction_type,
                                        'current_ph': ph_current_val,
                                        'target_ph': ph_target_val,
                                        'diff': diff
                                    }
                                )
                                # Create PH_TOO_HIGH_DETECTED or PH_TOO_LOW_DETECTED if deviation is significant
                                if diff > 0.3:
                                    await create_zone_event(
                                        zone_id,
                                        'PH_TOO_HIGH_DETECTED',
                                        {
                                            'current_ph': ph_current_val,
                                            'target_ph': ph_target_val,
                                            'diff': diff
                                        }
                                    )
                                elif diff < -0.3:
                                    await create_zone_event(
                                        zone_id,
                                        'PH_TOO_LOW_DETECTED',
                                        {
                                            'current_ph': ph_current_val,
                                            'target_ph': ph_target_val,
                                            'diff': diff
                                        }
                                    )
                                # Create AI log
                                await create_ai_log(
                                    zone_id,
                                    'recommend',
                                    {
                                        'action': 'ph_correction',
                                        'metric': 'ph',
                                        'current': ph_current_val,
                                        'target': ph_target_val,
                                        'correction': correction_type
                                    }
                                )
        # Check EC target (only if ec_control capability is enabled)
        if capabilities.get("ec_control", False):
            ec_target = targets.get("ec")
            ec_current = telemetry.get("ec")
            if ec_target is not None and ec_current is not None:
                ec_target_val = float(ec_target) if isinstance(ec_target, (int, float, str)) else None
                ec_current_val = float(ec_current) if isinstance(ec_current, (int, float)) else None
                if ec_target_val is not None and ec_current_val is not None:
                    # Simple rule: if EC is too low (diff < -0.2), add nutrients; if too high (diff > 0.2), dilute
                    diff = ec_current_val - ec_target_val
                    if abs(diff) > 0.2:
                        # Проверяем cooldown и анализ тренда перед корректировкой
                        should_correct, reason = await should_apply_correction(
                            zone_id, "ec", ec_current_val, ec_target_val, diff
                        )
                        
                        if not should_correct:
                            logger.info(f"Zone {zone_id}: EC correction skipped - {reason}")
                            # Создаем событие о пропуске корректировки
                            await create_zone_event(
                                zone_id,
                                'EC_CORRECTION_SKIPPED',
                                {
                                    'current_ec': ec_current_val,
                                    'target_ec': ec_target_val,
                                    'diff': diff,
                                    'reason': reason
                                }
                            )
                        # Check water level before dosing
                        elif should_correct and water_level_ok:
                            irrig_node = None
                            for key, node_info in nodes.items():
                                if node_info["type"] == "irrig":
                                    irrig_node = node_info
                                    break
                            if irrig_node:
                                correction_type = "add_nutrients" if diff < -0.2 else "dilute"
                                await publish_correction_command(
                                    mqtt, gh_uid, zone_id,
                                    irrig_node["node_uid"], irrig_node["channel"],
                                    "adjust_ec", {"amount": abs(diff) * 100, "type": correction_type},
                                )
                                # Записываем информацию о корректировке
                                await record_correction(zone_id, "ec", {
                                    "correction_type": correction_type,
                                    "current_ec": ec_current_val,
                                    "target_ec": ec_target_val,
                                    "diff": diff,
                                    "reason": reason
                                })
                                # Create zone events for EC correction
                                await create_zone_event(
                                    zone_id,
                                    'EC_DOSING',
                                    {
                                        'correction_type': correction_type,
                                        'current_ec': ec_current_val,
                                        'target_ec': ec_target_val,
                                        'diff': diff,
                                        'dose_ml': abs(diff) * 100
                                    }
                                )
                                # Also create DOSING event for compatibility
                                await create_zone_event(
                                    zone_id,
                                    'DOSING',
                                    {
                                        'type': 'ec_correction',
                                        'correction_type': correction_type,
                                        'current_ec': ec_current_val,
                                        'target_ec': ec_target_val,
                                        'diff': diff
                                    }
                                )
                                # Create AI log
                                await create_ai_log(
                                    zone_id,
                                    'recommend',
                                    {
                                        'action': 'ec_correction',
                                        'metric': 'ec',
                                        'current': ec_current_val,
                                        'target': ec_target_val,
                                        'correction': correction_type
                                    }
                                )
        
        # Zone Health Monitor (после всех контроллеров согласно ZONE_CONTROLLER_FULL.md раздел 8)
        health_data = await calculate_zone_health(zone_id)
        await update_zone_health_in_db(zone_id, health_data)


async def fetch_full_config(client: httpx.AsyncClient, base_url: str, token: str) -> Optional[Dict[str, Any]]:
    """Fetch full config from Laravel API with proper error handling and retry logic."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    max_retries = 3
    retry_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            r = await client.get(f"{base_url}/api/system/config/full", headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            CONFIG_FETCH_SUCCESS.inc()
            return data
        except httpx.HTTPStatusError as e:
            error_type = f"http_{e.response.status_code}"
            CONFIG_FETCH_ERRORS.labels(error_type=error_type).inc()
            if e.response.status_code == 401:
                logger.error(f"Config fetch failed: Unauthorized (401) - invalid or missing token. Attempt {attempt + 1}/{max_retries}")
                # Don't retry on 401 - it's a configuration issue
                return None
            elif e.response.status_code >= 500:
                logger.warning(f"Config fetch failed: Server error {e.response.status_code}. Attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"Config fetch failed after {max_retries} attempts: Server error {e.response.status_code}")
                    return None
            else:
                logger.error(f"Config fetch failed: HTTP {e.response.status_code}. Attempt {attempt + 1}/{max_retries}")
                return None
        except httpx.TimeoutException:
            error_type = "timeout"
            CONFIG_FETCH_ERRORS.labels(error_type=error_type).inc()
            logger.warning(f"Config fetch failed: Timeout. Attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            else:
                logger.error(f"Config fetch failed after {max_retries} attempts: Timeout")
                return None
        except httpx.NetworkError as e:
            error_type = "network_error"
            CONFIG_FETCH_ERRORS.labels(error_type=error_type).inc()
            logger.warning(f"Config fetch failed: Network error - {e}. Attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            else:
                logger.error(f"Config fetch failed after {max_retries} attempts: Network error - {e}")
                return None
        except Exception as e:
            error_type = type(e).__name__
            CONFIG_FETCH_ERRORS.labels(error_type=error_type).inc()
            logger.exception(f"Config fetch failed: Unexpected error - {e}. Attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            else:
                logger.error(f"Config fetch failed after {max_retries} attempts: {e}")
                return None
    
    return None


async def main():
    s = get_settings()
    mqtt = MqttClient(client_id_suffix="-auto")
    try:
        mqtt.start()
    except Exception as e:
        logger.critical(f"Failed to start MQTT client: {e}. Exiting.", exc_info=True)
        # Exit on critical configuration errors
        raise
    
    start_http_server(9401)  # Prometheus metrics

    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Fetch config
                cfg = await fetch_full_config(client, s.laravel_api_url, s.laravel_api_token)
                if not cfg:
                    logger.warning("Config fetch returned None, sleeping before retry")
                    await asyncio.sleep(15)
                    continue
                
                gh_uid = _extract_gh_uid_from_config(cfg)
                if not gh_uid:
                    logger.warning("No greenhouse UID found in config, sleeping before retry")
                    await asyncio.sleep(15)
                    continue
                
                # Get active zones with recipes
                zones = await fetch(
                    """
                    SELECT DISTINCT z.id, z.status
                    FROM zones z
                    JOIN zone_recipe_instances zri ON zri.zone_id = z.id
                    WHERE z.status IN ('online', 'warning')
                    """
                )
                # Check each zone
                for zone_row in zones:
                    zone_id = zone_row["id"]
                    try:
                        await check_and_correct_zone(zone_id, mqtt, gh_uid, cfg)
                    except Exception as e:
                        error_type = type(e).__name__
                        LOOP_ERRORS.labels(error_type=error_type).inc()
                        logger.error(f"Error checking zone {zone_id}: {e}", exc_info=True)
                        # Continue with other zones even if one fails
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down")
                break
            except Exception as e:
                error_type = type(e).__name__
                LOOP_ERRORS.labels(error_type=error_type).inc()
                logger.exception(f"Critical error in automation main loop: {e}")
                # Sleep before retrying to avoid tight error loops
                await asyncio.sleep(15)
            await asyncio.sleep(15)


if __name__ == "__main__":
    asyncio.run(main())
