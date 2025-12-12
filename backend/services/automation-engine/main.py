import asyncio
import json
import httpx
import logging
import os
import signal
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
from common.utils.time import utcnow
from common.env import get_settings
from common.mqtt import MqttClient
from common.db import fetch, execute, create_zone_event, create_ai_log
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import math
import time
from common.service_logs import send_service_log
from infrastructure.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from infrastructure.command_validator import CommandValidator
from infrastructure.command_tracker import CommandTracker
from infrastructure.command_audit import CommandAudit
from infrastructure.system_health import SystemHealthMonitor
from services.pid_state_manager import PidStateManager
from utils.logging_context import set_trace_id, set_zone_id
from utils.system_state_logger import log_system_state
from utils.zone_prioritizer import prioritize_zones

# Настройка логирования
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
from utils.logging_context import setup_structured_logging
setup_structured_logging(level=getattr(logging, log_level, logging.INFO))

logger = logging.getLogger(__name__)
from recipe_utils import calculate_current_phase, advance_phase, get_phase_targets

# Metrics for error tracking
LOOP_ERRORS = Counter("automation_loop_errors_total", "Errors in automation main loop", ["error_type"])
CONFIG_FETCH_ERRORS = Counter("config_fetch_errors_total", "Errors fetching config from Laravel", ["error_type"])
CONFIG_FETCH_SUCCESS = Counter("config_fetch_success_total", "Successful config fetches from Laravel")
# COMMANDS_SENT перенесена в infrastructure/command_bus.py
# Импортируем метрики для регистрации в REGISTRY до запуска start_http_server
from infrastructure.command_bus import COMMANDS_SENT
from common.water_flow import (
    check_water_level,
    ensure_water_level_alert,
    ensure_no_flow_alert,
)
# tick_recirculation moved to irrigation_controller
from common.pump_safety import can_run_pump
from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository
from services.zone_automation_service import ZoneAutomationService, ZONE_CHECKS, CHECK_LAT
from infrastructure import CommandBus
from config.settings import get_settings as get_automation_settings
from error_handler import handle_automation_error, error_handler
from exceptions import InvalidConfigurationError

# Метрики для адаптивной конкурентности
ZONE_PROCESSING_TIME = Histogram(
    "zone_processing_time_seconds",
    "Time to process a single zone",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)
ZONE_PROCESSING_ERRORS = Counter(
    "zone_processing_errors_total",
    "Errors during zone processing",
    ["zone_id", "error_type"]
)
OPTIMAL_CONCURRENCY = Gauge(
    "optimal_concurrency_zones",
    "Calculated optimal concurrency for zone processing"
)

# Глобальное хранилище для среднего времени обработки (скользящее среднее)
_avg_processing_time = 1.0
_processing_times = []  # Последние 100 измерений
_MAX_SAMPLES = 100
_processing_times_lock = asyncio.Lock()  # Блокировка для thread-safe доступа

# Graceful shutdown
_shutdown_event = asyncio.Event()
_zone_service: Optional[ZoneAutomationService] = None
_command_tracker: Optional[CommandTracker] = None
_command_bus: Optional[CommandBus] = None


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
    """
    DEPRECATED: Fetch active recipe phase and targets for zone.
    Используется только для тестов. В основном коде используйте RecipeRepository напрямую.
    """
    # Для обратной совместимости создаем репозиторий без circuit breaker
    # В основном коде circuit breaker передается из main()
    repo = RecipeRepository()
    return await repo.get_zone_recipe_and_targets(zone_id)


async def get_zone_telemetry_last(zone_id: int) -> Dict[str, Optional[float]]:
    """
    DEPRECATED: Fetch last telemetry values for zone.
    Используется только для тестов. В основном коде используйте TelemetryRepository напрямую.
    """
    # Для обратной совместимости создаем репозиторий без circuit breaker
    # В основном коде circuit breaker передается из main()
    repo = TelemetryRepository()
    return await repo.get_last_telemetry(zone_id)


async def get_zone_nodes(zone_id: int) -> Dict[str, Dict[str, Any]]:
    """Fetch nodes for zone, keyed by type and channel."""
    repo = NodeRepository()
    return await repo.get_zone_nodes(zone_id)


async def get_zone_capabilities(zone_id: int) -> Dict[str, bool]:
    """Fetch zone capabilities from database."""
    repo = ZoneRepository()
    return await repo.get_zone_capabilities(zone_id)


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
    global _command_bus
    if _command_bus is not None:
        return await _command_bus.publish_command(zone_id, node_uid, channel, cmd, params)
    
    # Fallback: создаем временный CommandBus если глобальный не инициализирован
    from infrastructure import CommandBus
    history_logger_url = os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
    history_logger_token = os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
    command_bus = CommandBus(mqtt=None, gh_uid=gh_uid, history_logger_url=history_logger_url, history_logger_token=history_logger_token)
    await command_bus.start()
    try:
        return await command_bus.publish_command(zone_id, node_uid, channel, cmd, params)
    finally:
        await command_bus.stop()


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


async def calculate_optimal_concurrency(
    total_zones: int,
    target_cycle_time: int,
    avg_zone_processing_time: float
) -> int:
    """
    Вычислить оптимальное количество параллельных зон.
    
    Формула: concurrency = (total_zones * avg_time) / target_cycle_time
    
    Args:
        total_zones: Общее количество зон
        target_cycle_time: Целевое время цикла в секундах
        avg_zone_processing_time: Среднее время обработки одной зоны в секундах
    
    Returns:
        Оптимальное количество параллельных зон
    """
    if avg_zone_processing_time <= 0:
        # Если нет данных, используем дефолтное значение
        return 5
    
    optimal = math.ceil((total_zones * avg_zone_processing_time) / target_cycle_time)
    
    # Ограничиваем диапазон
    min_concurrency = 5
    max_concurrency = 50  # Защита от перегрузки
    
    return max(min_concurrency, min(optimal, max_concurrency))


async def process_zones_parallel(
    zones: List[Dict[str, Any]],
    zone_service: ZoneAutomationService,
    max_concurrent: int = 5
) -> Dict[str, Any]:
    """
    Обработка зон параллельно с ограничением количества одновременных операций и отслеживанием ошибок.
    
    Args:
        zones: Список зон для обработки
        zone_service: Сервис автоматизации зон
        max_concurrent: Максимальное количество одновременных операций
    
    Returns:
        Dict с результатами: {'total': int, 'success': int, 'failed': int, 'errors': List[Dict]}
    """
    results = {
        'total': len(zones),
        'success': 0,
        'failed': 0,
        'errors': []
    }
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_with_tracking(zone_row: Dict[str, Any]) -> None:
        """Обработка зоны с отслеживанием результата."""
        zone_id = zone_row.get("id")
        zone_name = zone_row.get("name", "unknown")
        
        # Устанавливаем zone_id в контекст для логирования
        set_zone_id(zone_id)
        set_trace_id()  # Новый trace ID для каждой зоны
        
        try:
            async with semaphore:
                try:
                    start = time.time()
                    await zone_service.process_zone(zone_id)
                    duration = time.time() - start
                    
                    ZONE_PROCESSING_TIME.observe(duration)
                    
                    # Обновляем скользящее среднее (thread-safe)
                    global _avg_processing_time, _processing_times, _processing_times_lock
                    async with _processing_times_lock:
                        _processing_times.append(duration)
                        if len(_processing_times) > _MAX_SAMPLES:
                            _processing_times.pop(0)
                        _avg_processing_time = sum(_processing_times) / len(_processing_times) if _processing_times else 1.0
                    
                    results['success'] += 1
                    
                    logger.debug(f"Zone {zone_id} processed successfully ({duration:.2f}s)")
                    
                except Exception as e:
                    results['failed'] += 1
                    error_info = {
                        'zone_id': zone_id,
                        'zone_name': zone_name,
                        'error': str(e),
                        'error_type': type(e).__name__,
                        'timestamp': utcnow().isoformat()
                    }
                    results['errors'].append(error_info)
                    
                    ZONE_PROCESSING_ERRORS.labels(
                        zone_id=str(zone_id),
                        error_type=type(e).__name__
                    ).inc()
                    
                    from error_handler import handle_zone_error
                    handle_zone_error(zone_id, e, {"action": "process_zone"})
                    
                    logger.error(
                        f"Error processing zone {zone_id}: {e}",
                        exc_info=True,
                        extra={'zone_id': zone_id, 'zone_name': zone_name}
                    )
        finally:
            # Очищаем контекст
            set_zone_id(None)
    
    # Создаем задачи для всех зон и выполняем их параллельно
    tasks = [process_with_tracking(zone_row) for zone_row in zones]
    await asyncio.gather(*tasks)
    
    # Логируем общий результат
    logger.info(
        f"Zone processing completed: {results['success']}/{results['total']} success, "
        f"{results['failed']} failed"
    )
    
    # Отправляем алерты при критическом количестве ошибок
    if results['failed'] > 0 and results['total'] > 0:
        failure_rate = results['failed'] / results['total']
        
        if failure_rate > 0.1:  # >10% ошибок
            severity = 'warning' if failure_rate < 0.3 else 'critical'
            logger.warning(
                f"High zone processing failure rate: {failure_rate:.1%}",
                extra={
                    'total': results['total'],
                    'failed': results['failed'],
                    'failure_rate': failure_rate,
                    'severity': severity,
                    'errors': results['errors'][:10]  # Первые 10 ошибок
                }
            )
    
    return results


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
    global _command_bus
    if _command_bus is None:
        history_logger_url = os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
        history_logger_token = os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
        _command_bus = CommandBus(mqtt=None, gh_uid=gh_uid, history_logger_url=history_logger_url, history_logger_token=history_logger_token)
        await _command_bus.start()
    
    command_bus = _command_bus
    zone_service = ZoneAutomationService(
        zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus
    )
    await zone_service.process_zone(zone_id)


async def fetch_full_config(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    circuit_breaker: Optional[CircuitBreaker] = None
) -> Optional[Dict[str, Any]]:
    """Fetch full config from Laravel API with proper error handling and retry logic."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    max_retries = 3
    retry_delay = 2.0
    
    async def _fetch():
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
    
    for attempt in range(max_retries):
        try:
            if circuit_breaker:
                return await circuit_breaker.call(_fetch)
            else:
                return await _fetch()
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


def signal_handler(signum, frame):
    """Обработчик сигналов для graceful shutdown."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    _shutdown_event.set()


async def _finish_current_zones(zone_service: ZoneAutomationService, active_zones: List[Dict[str, Any]]) -> None:
    """Завершить обработку текущих зон."""
    if not active_zones:
        return
    
    logger.info(f"Finishing processing of {len(active_zones)} zones...")
    # Даем время завершить текущие операции (упрощенная версия)
    await asyncio.sleep(2.0)




async def main():
    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    s = get_settings()
    automation_settings = get_automation_settings()
    
    # Start Prometheus metrics server
    start_http_server(automation_settings.PROMETHEUS_PORT)  # Prometheus metrics
    
    # Start FastAPI server for REST API (scheduler endpoint) в отдельном потоке
    import threading
    import uvicorn
    from api import app as api_app
    
    api_port = int(os.getenv("AUTOMATION_ENGINE_API_PORT", "9405"))
    
    def run_api_server():
        """Запуск FastAPI сервера в отдельном потоке."""
        import sys
        # Создаем новый event loop для этого потока
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        config = uvicorn.Config(
            api_app,
            host="0.0.0.0",
            port=api_port,
            log_level="info",
            access_log=False
        )
        server = uvicorn.Server(config)
        try:
            loop.run_until_complete(server.serve())
        except Exception as e:
            logger.error(f"FastAPI server error: {e}", exc_info=True)
            sys.exit(1)
    
    # Запускаем API сервер в отдельном потоке
    api_thread = threading.Thread(target=run_api_server, daemon=True)
    api_thread.start()
    logger.info(f"FastAPI server started on port {api_port}")
    
    send_service_log(
        service="automation-engine",
        level="info",
        message="Automation Engine service started",
        context={
            "prometheus_port": automation_settings.PROMETHEUS_PORT,
            "api_port": api_port
        },
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
    
    # Инициализация Circuit Breakers
    db_circuit_breaker = CircuitBreaker("database", failure_threshold=5, timeout=60.0)
    api_circuit_breaker = CircuitBreaker("laravel_api", failure_threshold=5, timeout=60.0)
    mqtt_circuit_breaker = CircuitBreaker("mqtt", failure_threshold=3, timeout=30.0)
    
    # Инициализация Command Tracker
    global _command_tracker
    _command_tracker = CommandTracker(command_timeout=300, poll_interval=5)
    
    # Восстанавливаем pending команды из БД после рестарта
    await _command_tracker.restore_pending_commands()
    
    # Запускаем периодическую проверку статусов команд из БД
    await _command_tracker.start_polling()
    
    # Инициализация Command Validator
    command_validator = CommandValidator()
    
    # Инициализация Health Monitor
    health_monitor = SystemHealthMonitor(
        mqtt,
        db_circuit_breaker,
        api_circuit_breaker,
        mqtt_circuit_breaker
    )
    
    # Инициализация PID State Manager
    pid_state_manager = PidStateManager()
    
    # Периодическая проверка здоровья (каждые 30 секунд)
    async def health_check_loop():
        while not _shutdown_event.is_set():
            try:
                health = await health_monitor.check_health()
                if health['status'] != 'healthy':
                    logger.warning(f"System health: {health['status']}", extra=health)
            except Exception as e:
                logger.error(f"Health check failed: {e}", exc_info=True)
            await asyncio.sleep(30)
    
    health_task = asyncio.create_task(health_check_loop())
    
    # Убрана подписка на command_response - статусы команд теперь отслеживаются через БД (таблица commands)
    # history-logger обрабатывает command_response и обновляет статусы через Laravel API
    # CommandTracker периодически проверяет статусы из БД
    
    try:
        async with httpx.AsyncClient() as client:
            active_zones: List[Dict[str, Any]] = []
            global _zone_service
            
            while not _shutdown_event.is_set():
                try:
                    # Fetch config через Circuit Breaker
                    try:
                        cfg = await fetch_full_config(
                            client, s.laravel_api_url, s.laravel_api_token, api_circuit_breaker
                        )
                    except CircuitBreakerOpenError:
                        logger.warning("API Circuit Breaker is OPEN, using cached config or skipping")
                        await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
                        continue
                    
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
                    
                    # Инициализация репозиториев с circuit breakers
                    zone_repo = ZoneRepository()
                    telemetry_repo = TelemetryRepository(db_circuit_breaker=db_circuit_breaker)
                    node_repo = NodeRepository()
                    recipe_repo = RecipeRepository(db_circuit_breaker=db_circuit_breaker)
                    
                    # Инициализация Command Audit
                    command_audit = CommandAudit()
                    
                    # Инициализация Command Bus с валидатором, трекером и аудитом
                    # Все команды отправляются через history-logger REST API
                    global _command_bus
                    if _command_bus is None:
                        history_logger_url = os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
                        history_logger_token = os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
                        _command_bus = CommandBus(
                            mqtt=None,  # MQTT больше не используется для команд
                            gh_uid=gh_uid,
                            history_logger_url=history_logger_url,
                            history_logger_token=history_logger_token,
                            command_validator=command_validator,
                            command_tracker=_command_tracker,
                            command_audit=command_audit,
                            api_circuit_breaker=api_circuit_breaker
                        )
                        await _command_bus.start()
                        logger.info("CommandBus initialized with long-lived HTTP client")
                    
                    command_bus = _command_bus
                    
                    # Устанавливаем CommandBus в API для scheduler endpoint
                    try:
                        from api import set_command_bus
                        set_command_bus(command_bus, gh_uid)
                    except ImportError:
                        logger.warning("API module not available, scheduler endpoint will not work")
                    
                    # Инициализация сервиса автоматизации зон
                    _zone_service = ZoneAutomationService(
                        zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus, pid_state_manager
                    )
                    
                    # Get active zones with recipes через Circuit Breaker
                    try:
                        async def _get_zones():
                            return await zone_repo.get_active_zones()
                        
                        zones = await db_circuit_breaker.call(_get_zones)
                    except CircuitBreakerOpenError:
                        logger.warning("Database Circuit Breaker is OPEN, skipping zone processing")
                        await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
                        continue
                    
                    # Приоритизация зон
                    zones = prioritize_zones(zones)
                    active_zones = zones
                    
                    # Параллельная обработка зон с адаптивной конкурентностью
                    if zones:
                        # Вычисляем оптимальную конкурентность, если включена адаптивность
                        if automation_settings.ADAPTIVE_CONCURRENCY:
                            global _avg_processing_time
                            optimal_concurrency = await calculate_optimal_concurrency(
                                total_zones=len(zones),
                                target_cycle_time=automation_settings.TARGET_CYCLE_TIME_SEC,
                                avg_zone_processing_time=_avg_processing_time
                            )
                            
                            OPTIMAL_CONCURRENCY.set(optimal_concurrency)
                            
                            logger.info(
                                f"Adaptive concurrency: {optimal_concurrency} zones "
                                f"(avg time: {_avg_processing_time:.2f}s, target cycle: {automation_settings.TARGET_CYCLE_TIME_SEC}s)"
                            )
                            
                            max_concurrent = optimal_concurrency
                        else:
                            max_concurrent = automation_settings.MAX_CONCURRENT_ZONES
                        
                        # Обрабатываем зоны с отслеживанием результатов
                        results = await process_zones_parallel(
                            zones, _zone_service,
                            max_concurrent=max_concurrent
                        )
                        
                        # Логируем результаты для мониторинга
                        if results['failed'] > 0:
                            logger.warning(
                                f"Zone processing completed with errors: {results['success']}/{results['total']} success, "
                                f"{results['failed']} failed"
                            )
                        
                        # Логируем состояние системы (каждые 5 минут)
                        import time
                        if int(time.time()) % 300 == 0:  # Каждые 5 минут
                            await log_system_state(
                                _zone_service,
                                zones,
                                _command_tracker,
                                db_circuit_breaker,
                                api_circuit_breaker,
                                mqtt_circuit_breaker
                            )
                except KeyboardInterrupt:
                    logger.info("Received interrupt signal, shutting down")
                    _shutdown_event.set()
                    break
                except Exception as e:
                    handle_automation_error(e, {"action": "main_loop"})
                    # Sleep before retrying to avoid tight error loops
                    await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
                
                # Проверяем shutdown event
                if _shutdown_event.is_set():
                    break
                
                await asyncio.sleep(automation_settings.MAIN_LOOP_SLEEP_SECONDS)
    finally:
        # Graceful shutdown
        logger.info("Graceful shutdown initiated")
        
        # Отменяем health check task
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass
        
        # 1. Завершаем обработку текущих зон
        if _zone_service and active_zones:
            try:
                await asyncio.wait_for(
                    _finish_current_zones(_zone_service, active_zones),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for zones to finish")
        
        # 2. Сохраняем состояние PID контроллеров
        if _zone_service:
            try:
                await asyncio.wait_for(
                    _zone_service.save_all_pid_states(),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("Timeout saving PID state")
            except Exception as e:
                logger.error(f"Error saving PID state: {e}", exc_info=True)
        
        # 3. Останавливаем polling статусов команд
        if _command_tracker:
            try:
                await _command_tracker.stop_polling()
            except Exception as e:
                logger.warning(f"Failed to stop command polling: {e}")
        
        # 4. Закрываем CommandBus HTTP клиент
        if _command_bus:
            try:
                await _command_bus.stop()
            except Exception as e:
                logger.warning(f"Failed to stop CommandBus: {e}")
        
        # 5. Закрываем соединения
        try:
            mqtt.stop()
        except Exception as e:
            logger.warning(f"Error stopping MQTT: {e}")
        
        logger.info("Graceful shutdown completed")


if __name__ == "__main__":
    asyncio.run(main())
