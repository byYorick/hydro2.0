import asyncio
import json
import httpx
import logging
import os
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
from common.env import get_settings
from common.mqtt import MqttClient
from common.db import fetch, execute, create_zone_event, create_ai_log
from prometheus_client import Counter, Histogram, start_http_server
from common.service_logs import send_service_log

# Настройка логирования
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Явно указываем stdout для Docker
)

logger = logging.getLogger(__name__)
from recipe_utils import calculate_current_phase, advance_phase, get_phase_targets

# Metrics for error tracking
LOOP_ERRORS = Counter("automation_loop_errors_total", "Errors in automation main loop", ["error_type"])
CONFIG_FETCH_ERRORS = Counter("config_fetch_errors_total", "Errors fetching config from Laravel", ["error_type"])
CONFIG_FETCH_SUCCESS = Counter("config_fetch_success_total", "Successful config fetches from Laravel")
# MQTT_PUBLISH_ERRORS и COMMANDS_SENT перенесены в infrastructure/command_bus.py
# Импортируем метрики для регистрации в REGISTRY до запуска start_http_server
from infrastructure.command_bus import COMMANDS_SENT, MQTT_PUBLISH_ERRORS
from common.water_flow import (
    check_water_level,
    ensure_water_level_alert,
    ensure_no_flow_alert,
)
# tick_recirculation moved to irrigation_controller
from common.pump_safety import can_run_pump
from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository
from services import ZoneAutomationService
from infrastructure import CommandBus
from config.settings import get_settings as get_automation_settings
from error_handler import handle_automation_error, error_handler
from exceptions import InvalidConfigurationError

# Метрики перенесены в соответствующие модули:
# - ZONE_CHECKS и CHECK_LAT в services/zone_automation_service.py
# - COMMANDS_SENT и MQTT_PUBLISH_ERRORS в infrastructure/command_bus.py
# Импортируем метрики для регистрации в REGISTRY до запуска start_http_server
from services.zone_automation_service import ZONE_CHECKS, CHECK_LAT


def validate_config(cfg: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Валидация конфигурации из API.
    
    Returns:
        Tuple[is_valid, error_message]
    """
    if not isinstance(cfg, dict):
        return False, "Config must be a dictionary"
    
    if "greenhouses" not in cfg:
        return False, "Config missing 'greenhouses' key"
    
    if not isinstance(cfg["greenhouses"], list):
        return False, "'greenhouses' must be a list"
    
    if len(cfg["greenhouses"]) == 0:
        return False, "'greenhouses' list is empty"
    
    gh = cfg["greenhouses"][0]
    if not isinstance(gh, dict):
        return False, "Greenhouse must be a dictionary"
    
    if "uid" not in gh:
        return False, "Greenhouse must have 'uid' field"
    
    if not isinstance(gh["uid"], str) or not gh["uid"]:
        return False, "Greenhouse 'uid' must be a non-empty string"
    
    return True, None


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


# DEPRECATED: Используйте CommandBus вместо этой функции
# Оставлено для обратной совместимости
async def publish_correction_command(
    mqtt: MqttClient,
    gh_uid: str,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    params: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    DEPRECATED: Используйте CommandBus.publish_command() вместо этой функции.
    Оставлено для обратной совместимости.
    """
    from infrastructure import CommandBus
    command_bus = CommandBus(mqtt, gh_uid)
    return await command_bus.publish_command(zone_id, node_uid, channel, cmd, params)


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


def validate_zone_id(zone_id: Any) -> int:
    """Валидация zone_id."""
    if not isinstance(zone_id, int):
        raise ValueError(f"zone_id must be int, got {type(zone_id)}")
    if zone_id <= 0:
        raise ValueError(f"zone_id must be positive, got {zone_id}")
    return zone_id


async def process_zones_parallel(
    zones: List[Dict[str, Any]],
    zone_service: ZoneAutomationService,
    max_concurrent: int = 5
) -> None:
    """
    Обработка зон параллельно с ограничением количества одновременных операций.
    
    Args:
        zones: Список зон для обработки
        zone_service: Сервис автоматизации зон
        max_concurrent: Максимальное количество одновременных операций
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_zone(zone_row: Dict[str, Any]) -> None:
        """Обработка одной зоны с ограничением через semaphore."""
        async with semaphore:
            zone_id = zone_row["id"]
            try:
                await zone_service.process_zone(zone_id)
            except Exception as e:
                from error_handler import handle_zone_error
                handle_zone_error(zone_id, e, {"action": "process_zone"})
                # Продолжаем с другими зонами даже если одна упала
    
    # Создаем задачи для всех зон и выполняем их параллельно
    tasks = [process_zone(zone_row) for zone_row in zones]
    await asyncio.gather(*tasks, return_exceptions=True)


# DEPRECATED: Используйте ZoneAutomationService.process_zone() вместо этой функции
# Оставлено для обратной совместимости и тестов
async def check_and_correct_zone(
    zone_id: int,
    mqtt: MqttClient,
    gh_uid: str,
    cfg: Dict[str, Any],
    zone_repo: ZoneRepository,
    telemetry_repo: TelemetryRepository,
    node_repo: NodeRepository,
    recipe_repo: RecipeRepository
):
    """
    DEPRECATED: Используйте ZoneAutomationService.process_zone() вместо этой функции.
    Оставлено для обратной совместимости и тестов.
    """
    from infrastructure import CommandBus
    from services import ZoneAutomationService
    
    # Валидация zone_id
    try:
        zone_id = validate_zone_id(zone_id)
    except ValueError as e:
        logger.error(f"Invalid zone_id: {e}")
        return
    
    # Используем новый сервисный слой (метрики внутри сервиса)
    command_bus = CommandBus(mqtt, gh_uid)
    zone_service = ZoneAutomationService(
        zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus
    )
    await zone_service.process_zone(zone_id)


async def fetch_full_config(client: httpx.AsyncClient, base_url: str, token: str) -> Optional[Dict[str, Any]]:
    """Fetch full config from Laravel API with proper error handling and retry logic."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    max_retries = 3
    retry_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            r = await client.get(f"{base_url}/api/system/config/full", headers=headers, timeout=30.0)
            r.raise_for_status()
            response_data = r.json()
            # Laravel API returns {"status": "ok", "data": {...}}, extract "data" part
            if isinstance(response_data, dict) and "data" in response_data:
                data = response_data["data"]
            else:
                data = response_data
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
    automation_settings = get_automation_settings()
    
    # Start Prometheus metrics server
    start_http_server(automation_settings.PROMETHEUS_PORT)  # Prometheus metrics
    send_service_log(
        service="automation-engine",
        level="info",
        message="Automation Engine service started",
        context={"prometheus_port": automation_settings.PROMETHEUS_PORT},
    )
    
    mqtt = MqttClient(client_id_suffix="-auto")
    try:
        mqtt.start()
    except Exception as e:
        logger.critical(f"Failed to start MQTT client: {e}. Exiting.", exc_info=True)
        send_service_log(
            service="automation-engine",
            level="critical",
            message=f"Failed to start MQTT client: {e}",
            context={"error": str(e)},
        )
        # Exit on critical configuration errors
        raise

    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Fetch config
                cfg = await fetch_full_config(client, s.laravel_api_url, s.laravel_api_token)
                if not cfg:
                    logger.warning("Config fetch returned None, sleeping before retry")
                    await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
                    continue
                
                # Validate config structure
                is_valid, error_msg = validate_config(cfg)
                if not is_valid:
                    handle_automation_error(
                        InvalidConfigurationError(error_msg, cfg),
                        {"action": "config_validation"}
                    )
                    await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
                    continue
                
                gh_uid = _extract_gh_uid_from_config(cfg)
                if not gh_uid:
                    logger.warning("No greenhouse UID found in config, sleeping before retry")
                    await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
                    continue
                
                # Инициализация репозиториев
                zone_repo = ZoneRepository()
                telemetry_repo = TelemetryRepository()
                node_repo = NodeRepository()
                recipe_repo = RecipeRepository()
                
                # Инициализация Command Bus
                command_bus = CommandBus(mqtt, gh_uid)
                
                # Инициализация сервиса автоматизации зон
                zone_service = ZoneAutomationService(
                    zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus
                )
                
                # Get active zones with recipes
                zones = await zone_repo.get_active_zones()
                
                # Параллельная обработка зон с ограничением количества одновременных операций
                if zones:
                    await process_zones_parallel(
                        zones, zone_service,
                        max_concurrent=automation_settings.MAX_CONCURRENT_ZONES
                    )
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down")
                break
            except Exception as e:
                handle_automation_error(e, {"action": "main_loop"})
                # Sleep before retrying to avoid tight error loops
                await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
            await asyncio.sleep(automation_settings.MAIN_LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
