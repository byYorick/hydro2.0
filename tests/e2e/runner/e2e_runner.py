
#!/usr/bin/env python3
"""
E2E Test Runner - выполняет YAML сценарии с проверками API/DB/WS/MQTT.
"""

import asyncio
import yaml
import logging
import sys
import os
import time
import re
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from urllib.parse import urlparse, urljoin

try:
    # When run as module
    from .api_client import APIClient, AuthenticationError
    from .auth_client import AuthClient
    from .ws_client import WSClient
    from .db_probe import DBProbe
    from .mqtt_probe import MQTTProbe
    from .assertions import Assertions, AssertionError
    from .reporting import TestReporter

    # New modular imports
    from .schema.validation import SchemaValidator
    from .schema.variables import VariableResolver
    from .steps.api import APIStepExecutor
    from .steps.websocket import WebSocketStepExecutor
    from .steps.database import DatabaseStepExecutor
    from .steps.mqtt import MQTTStepExecutor
    from .steps.waiting import WaitingStepExecutor
except ImportError:
    # When run directly - use absolute imports
    from api_client import APIClient, AuthenticationError
    from auth_client import AuthClient
    from ws_client import WSClient
    from db_probe import DBProbe
    from mqtt_probe import MQTTProbe
    from assertions import Assertions, AssertionError
    from reporting import TestReporter

    # New modular imports
    from schema.validation import SchemaValidator
    from schema.variables import VariableResolver
    from steps.api import APIStepExecutor
    from steps.websocket import WebSocketStepExecutor
    from steps.database import DatabaseStepExecutor
    from steps.mqtt import MQTTStepExecutor
    from steps.waiting import WaitingStepExecutor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class E2ERunner:
    """Раннер для выполнения E2E тестов из YAML сценариев."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Инициализация раннера.
        
        Args:
            config: Конфигурация (API URL, WS URL, DB path, MQTT settings)
        """
        config = config or {}
        
        # Конфигурация из переменных окружения или значений по умолчанию
        self.api_url = config.get("api_url") or os.getenv("LARAVEL_URL", "http://localhost:8081")
        
        # Инициализируем AuthClient (singleton)
        auth_email = config.get("auth_email", "e2e@test.local")
        auth_role = config.get("auth_role", "agronomist")  # По умолчанию agronomist для работы с ревизиями и циклами
        self.auth_client = AuthClient(
            api_url=self.api_url,
            email=auth_email,
            role=auth_role
        )
        
        # Старый способ через api_token - используется только если явно указан через config
        # Переменная окружения LARAVEL_API_TOKEN игнорируется, чтобы использовать AuthClient
        # Это обеспечивает автоматическое управление токенами и обновление при 401
        self.api_token = config.get("api_token")  # Только из config, не из env
        if self.api_token:
            logger.info(f"E2E Runner: api_token provided in config (length: {len(self.api_token)}), using it instead of AuthClient")
        else:
            logger.info(f"E2E Runner: Using AuthClient for automatic token management (LARAVEL_API_TOKEN from env will be ignored)")
        
        self.ws_url = config.get("ws_url") or os.getenv("WS_URL", "ws://localhost:6002/app/local")
        # Используем DATABASE_URL если есть, иначе формируем из переменных
        self.db_path = config.get("db_path") or os.getenv("DATABASE_URL") or os.getenv("DB_DATABASE")
        self.mqtt_host = config.get("mqtt_host") or os.getenv("MQTT_HOST", "localhost")
        # Выравниваем дефолтный порт под docker-compose.e2e.yml (1884 -> 1883 внутри)
        self.mqtt_port = config.get("mqtt_port") or int(os.getenv("MQTT_PORT", "1884"))
        self.mqtt_user = config.get("mqtt_user") or os.getenv("MQTT_USER")
        self.mqtt_pass = config.get("mqtt_pass") or os.getenv("MQTT_PASS")
        
        # Клиенты
        self.api: Optional[APIClient] = None
        self.ws: Optional[WSClient] = None
        self.db: Optional[DBProbe] = None
        self.mqtt: Optional[MQTTProbe] = None
        self.assertions = Assertions()
        self.reporter = TestReporter()

        # Новые модульные компоненты (инициализируются в setup())
        self.variable_resolver: Optional[VariableResolver] = None
        self.schema_validator: Optional[SchemaValidator] = None
        self.api_executor: Optional[APIStepExecutor] = None
        self.ws_executor: Optional[WebSocketStepExecutor] = None
        self.db_executor: Optional[DatabaseStepExecutor] = None
        self.mqtt_executor: Optional[MQTTStepExecutor] = None
        self.waiting_executor: Optional[WaitingStepExecutor] = None

        # Контекст для хранения переменных между шагами
        self.context: Dict[str, Any] = {}
        
        # Путь к docker-compose файлу для fault injection
        self.compose_file = config.get("compose_file") or os.getenv(
            "COMPOSE_FILE", 
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "docker-compose.e2e.yml")
        )
        
        # Отслеживание остановленных сервисов для автоматического восстановления
        self._stopped_services: List[str] = []
        # Отмечаем, запускали ли инфраструктуру сами, чтобы корректно чистить
        self._infra_started_by_runner = False

    def _use_docker_cli(self) -> bool:
        """Use docker CLI instead of docker-compose (e.g., in container mode)."""
        return os.getenv("E2E_CONTAINER") == "1" or os.getenv("E2E_DOCKER_CLI") == "1"

    def _docker_compose_available(self) -> bool:
        return shutil.which("docker-compose") is not None

    def _compose_project(self) -> str:
        project = os.getenv("COMPOSE_PROJECT_NAME")
        if project:
            return project
        compose_dir = os.path.dirname(self.compose_file) if os.path.dirname(self.compose_file) else os.getcwd()
        return os.path.basename(compose_dir) or "e2e"

    def _resolve_container_name(self, compose_service: str) -> str:
        project = self._compose_project()
        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--filter",
                    f"label=com.docker.compose.project={project}",
                    "--filter",
                    f"label=com.docker.compose.service={compose_service}",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                name = result.stdout.strip().splitlines()
                if name:
                    return name[0]
        except Exception:
            pass
        return f"{project}-{compose_service}-1"

    def _wait_laravel_health_simple(self, timeout: float = 60.0):
        """Wait for Laravel health without docker-compose (container-safe)."""
        import httpx

        url = os.getenv("LARAVEL_URL", "http://localhost:8081") + "/api/system/health"
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = httpx.get(url, timeout=2.0)
                if resp.status_code == 200:
                    return
            except Exception:
                pass
            time.sleep(2)
        logger.warning("Laravel health wait timed out in container mode")
    
    async def setup(self):
        """Инициализация клиентов."""
        logger.info("Setting up E2E runner...")
        
        # Автоматически поднимаем инфраструктуру, если она не запущена
        # Этот метод синхронный, но безопасно вызывается из async контекста
        try:
            self._ensure_infra_started()
        except Exception as e:
            logger.warning(f"Failed to ensure infrastructure is started: {e}")
            logger.info("Continuing anyway, assuming infrastructure is already running...")
        
        # Получаем токен через AuthClient (если не был предоставлен явно в config)
        token = None
        if not self.api_token:
            try:
                token = await self.auth_client.get_token()
                logger.info(f"✓ Token obtained via AuthClient (length: {len(token)})")
            except Exception as e:
                logger.error(f"Failed to get token via AuthClient: {e}")
                raise RuntimeError("Cannot proceed without authentication token") from e
        else:
            token = self.api_token
            logger.info(f"Using provided api_token from config (length: {len(token)})")
        
        # Создаем APIClient с AuthClient для автоматического управления токенами
        self.api = APIClient(
            base_url=self.api_url,
            api_token=token if self.api_token else None,  # Передаем токен только если был явно указан
            auth_client=self.auth_client if not self.api_token else None  # AuthClient только если не используется явный токен
        )
        
        # Для WebSocket используем AuthClient для автоматического получения токена
        self.ws = WSClient(
            ws_url=self.ws_url,
            api_token=token if self.api_token else None,  # Токен только если был явно указан
            auth_client=self.auth_client if not self.api_token else None,  # AuthClient для автоматического управления
            api_url=self.api_url
        )
        
        self.db = DBProbe(db_path=self.db_path)
        
        self.mqtt = MQTTProbe(
            host=self.mqtt_host,
            port=self.mqtt_port,
            username=self.mqtt_user,
            password=self.mqtt_pass
        )
        
        # Подключаемся к сервисам
        try:
            await self.ws.connect()
            logger.info("✓ WebSocket connected")
        except Exception as e:
            logger.warning(f"⚠ WebSocket connection failed: {e}")
        
        try:
            self.mqtt.connect()
            logger.info("✓ MQTT connected")
        except Exception as e:
            logger.warning(f"⚠ MQTT connection failed: {e}")
        
        try:
            self.db.connect()
            logger.info("✓ Database connected")
        except Exception as e:
            logger.warning(f"⚠ Database connection failed: {e}")

        # Инициализация модульных компонентов (нужны для резолвинга переменных в сценариях)
        self.variable_resolver = VariableResolver(self.context)
        self.schema_validator = SchemaValidator(self.context)
        self.api_executor = APIStepExecutor(self.api, self.variable_resolver)
        self.ws_executor = WebSocketStepExecutor(self.ws, self.schema_validator)
        self.db_executor = DatabaseStepExecutor(self.db, self.variable_resolver)
        self.mqtt_executor = MQTTStepExecutor(self.mqtt, self.variable_resolver)
        self.waiting_executor = WaitingStepExecutor(self.variable_resolver)
    
    async def teardown(self):
        """Очистка ресурсов."""
        logger.info("Tearing down E2E runner...")
        
        # Восстанавливаем все остановленные сервисы
        for service in list(self._stopped_services):
            try:
                await self._fault_restore(service)
            except Exception as e:
                logger.warning(f"Failed to restore service {service} during teardown: {e}")
        
        if self.ws:
            await self.ws.disconnect()
        if self.mqtt:
            self.mqtt.disconnect()
        if self.db:
            self.db.disconnect()
        if self.api:
            await self.api.close()
        
        # Если мы сами поднимали инфраструктуру, останавливаем node-sim для чистоты (остальное оставляем)
        if self._infra_started_by_runner:
            try:
                await self._fault_inject("node-sim", "stop", None)
            except Exception:
                pass
    
    async def _fault_inject(self, service: str, action: str, duration_s: Optional[float] = None):
        """
        Выполнить fault injection для Docker сервиса.
        
        Args:
            service: Имя сервиса (laravel, mosquitto, postgres, history-logger, automation-engine)
            action: Действие (stop, start, pause, unpause)
            duration_s: Длительность в секундах (для stop, после которой нужно восстановить)
        """
        compose_file = self.compose_file
        compose_dir = os.path.dirname(compose_file) if os.path.dirname(compose_file) else os.getcwd()
        
        # Маппинг имен сервисов на имена в docker-compose
        # reverb запускается внутри Laravel контейнера, поэтому маппим на laravel
        service_map = {
            "laravel": "laravel",
            "mosquitto": "mosquitto",
            "postgres": "postgres",
            "history-logger": "history-logger",
            "automation-engine": "automation-engine",
            "redis": "redis",
            "reverb": "laravel",  # Reverb запускается внутри Laravel (REVERB_AUTO_START=true)
            "node-sim": "node-sim",
        }
        compose_service = service_map.get(service, service)
        
        try:
            if action == "stop":
                logger.info(f"[FAULT_INJECT] Stopping service: {compose_service}")
                if self._use_docker_cli():
                    container = self._resolve_container_name(compose_service)
                    result = subprocess.run(
                        ["docker", "stop", container],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                else:
                    result = subprocess.run(
                        ["docker-compose", "-f", compose_file, "stop", compose_service],
                        cwd=compose_dir,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                if result.returncode != 0:
                    logger.error(f"[FAULT_INJECT] Failed to stop {compose_service}: {result.stderr}")
                    raise RuntimeError(f"Failed to stop service {compose_service}: {result.stderr}")
                self._stopped_services.append(compose_service)
                logger.info(f"[FAULT_INJECT] ✓ Service {compose_service} stopped")
                
                if duration_s:
                    # Запланировать автоматическое восстановление
                    asyncio.create_task(self._auto_restore_after_delay(compose_service, duration_s))
                    
            elif action == "start":
                await self._fault_restore(service)
                
            elif action == "pause":
                logger.info(f"[FAULT_INJECT] Pausing service: {compose_service}")
                if self._use_docker_cli():
                    container = self._resolve_container_name(compose_service)
                    result = subprocess.run(
                        ["docker", "pause", container],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                else:
                    result = subprocess.run(
                        ["docker-compose", "-f", compose_file, "pause", compose_service],
                        cwd=compose_dir,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                if result.returncode != 0:
                    logger.error(f"[FAULT_INJECT] Failed to pause {compose_service}: {result.stderr}")
                    raise RuntimeError(f"Failed to pause service {compose_service}: {result.stderr}")
                logger.info(f"[FAULT_INJECT] ✓ Service {compose_service} paused")
                
            elif action == "unpause":
                logger.info(f"[FAULT_INJECT] Unpausing service: {compose_service}")
                if self._use_docker_cli():
                    container = self._resolve_container_name(compose_service)
                    result = subprocess.run(
                        ["docker", "unpause", container],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                else:
                    result = subprocess.run(
                        ["docker-compose", "-f", compose_file, "unpause", compose_service],
                        cwd=compose_dir,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                if result.returncode != 0:
                    logger.error(f"[FAULT_INJECT] Failed to unpause {compose_service}: {result.stderr}")
                    raise RuntimeError(f"Failed to unpause service {compose_service}: {result.stderr}")
                logger.info(f"[FAULT_INJECT] ✓ Service {compose_service} unpaused")
                
            else:
                raise ValueError(f"Unknown fault action: {action}. Use: stop, start, pause, unpause")
                
        except subprocess.TimeoutExpired:
            logger.error(f"[FAULT_INJECT] Timeout while {action}ing service {compose_service}")
            raise RuntimeError(f"Timeout while {action}ing service {compose_service}")
        except Exception as e:
            logger.error(f"[FAULT_INJECT] Error {action}ing service {compose_service}: {e}", exc_info=True)
            raise
    
    async def _fault_restore(self, service: str):
        """
        Восстановить сервис после fault injection.
        
        Args:
            service: Имя сервиса
        """
        compose_file = self.compose_file
        compose_dir = os.path.dirname(compose_file) if os.path.dirname(compose_file) else os.getcwd()
        
        service_map = {
            "laravel": "laravel",
            "mosquitto": "mosquitto",
            "postgres": "postgres",
            "history-logger": "history-logger",
            "automation-engine": "automation-engine",
            "redis": "redis",
            "reverb": "laravel",  # Reverb запускается внутри Laravel (REVERB_AUTO_START=true)
            "node-sim": "node-sim",
        }
        compose_service = service_map.get(service, service)
        
        try:
            logger.info(f"[FAULT_INJECT] Restoring service: {compose_service}")
            if self._use_docker_cli():
                container = self._resolve_container_name(compose_service)
                result = subprocess.run(
                    ["docker", "start", container],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            else:
                result = subprocess.run(
                    ["docker-compose", "-f", compose_file, "start", compose_service],
                    cwd=compose_dir,
                    capture_output=True,
                    text=True,
                    timeout=60  # Больше времени для старта
                )
            if result.returncode != 0:
                logger.error(f"[FAULT_INJECT] Failed to start {compose_service}: {result.stderr}")
                raise RuntimeError(f"Failed to start service {compose_service}: {result.stderr}")
            
            if compose_service in self._stopped_services:
                self._stopped_services.remove(compose_service)
            
            # Ждем готовности сервиса
            await asyncio.sleep(2)
            logger.info(f"[FAULT_INJECT] ✓ Service {compose_service} restored")
            
        except subprocess.TimeoutExpired:
            logger.error(f"[FAULT_INJECT] Timeout while restoring service {compose_service}")
            raise RuntimeError(f"Timeout while restoring service {compose_service}")
        except Exception as e:
            logger.error(f"[FAULT_INJECT] Error restoring service {compose_service}: {e}", exc_info=True)
            raise
    
    async def _auto_restore_after_delay(self, service: str, delay_s: float):
        """Автоматически восстановить сервис после задержки."""
        await asyncio.sleep(delay_s)
        try:
            await self._fault_restore(service)
        except Exception as e:
            logger.warning(f"[FAULT_INJECT] Auto-restore failed for {service}: {e}")

    def _ensure_infra_started(self):
        """
        Поднять docker-compose инфраструктуру, если она еще не запущена.
        
        Использует COMPOSE_FILE (по умолчанию tests/e2e/docker-compose.e2e.yml).
        Можно отключить через env E2E_SKIP_COMPOSE_UP=1.
        """
        if os.getenv("E2E_SKIP_COMPOSE_UP") == "1":
            logger.info("E2E_SKIP_COMPOSE_UP=1, пропускаем docker-compose up")
            return
        if self._use_docker_cli():
            logger.info("E2E_CONTAINER=1: пропускаем docker-compose up, ожидаем Laravel")
            self._wait_laravel_health_simple()
            return
        if not self._docker_compose_available():
            logger.warning("docker-compose не найден, пропускаем docker-compose up")
            self._wait_laravel_health_simple()
            return

        compose_file = self.compose_file
        compose_dir = os.path.dirname(compose_file) if os.path.dirname(compose_file) else os.getcwd()

        # Быстрая проверка: порт Postgres слушает именно в docker-compose сети
        # Если на localhost:POSTGRES_PORT уже что-то есть, проверяем env marker E2E_EXPECT_COMPOSE=1
        try:
            import socket
            with socket.create_connection(("127.0.0.1", int(os.getenv("POSTGRES_PORT", "5433"))), timeout=1):
                if os.getenv("E2E_EXPECT_COMPOSE") == "1":
                    logger.info("E2E_EXPECT_COMPOSE=1, форсим docker-compose up даже при доступном Postgres")
                else:
                    logger.info("PostgreSQL уже доступен, docker-compose up пропущен")
                    return
        except Exception:
            pass

        services = [
            "postgres",
            "redis",
            "mosquitto",
            "laravel",  # Reverb запускается внутри Laravel контейнера (REVERB_AUTO_START=true)
            "history-logger",
            "mqtt-bridge",
            "automation-engine",  # Включаем automation-engine по умолчанию для E2E
            "node-sim",
        ]

        logger.info(f"docker-compose up -d для сервисов: {', '.join(services)}")
        try:
            result = subprocess.run(
                ["docker-compose", "-f", compose_file, "up", "-d", *services],
                cwd=compose_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode != 0:
                logger.error(f"docker-compose up failed: {result.stderr}")
                raise RuntimeError(f"docker-compose up failed: {result.stderr}")
            self._infra_started_by_runner = True
            logger.info("✓ docker-compose инфраструктура поднята")
            # Ждем готовности ключевых сервисов
            time.sleep(5)
            self._wait_infra_health(compose_file, compose_dir)
            self._run_migrations()
        except subprocess.TimeoutExpired:
            raise RuntimeError("docker-compose up timed out")
        except Exception as e:
            logger.error(f"Ошибка при docker-compose up: {e}")
            raise

    def _wait_infra_health(self, compose_file: str, compose_dir: str, timeout: float = 60.0):
        """
        Ожидание готовности основных сервисов после docker-compose up.
        Проверяем postgres, redis, mosquitto, laravel.
        """
        start = time.time()
        services_ok = {"postgres": False, "redis": False, "mosquitto": False, "laravel": False}
        while time.time() - start < timeout:
            all_ok = True
            # postgres
            if not services_ok["postgres"]:
                try:
                    import socket
                    with socket.create_connection(("127.0.0.1", int(os.getenv("POSTGRES_PORT", "5433"))), timeout=1):
                        services_ok["postgres"] = True
                        logger.info("Health: postgres ready")
                except Exception:
                    all_ok = False
            # redis
            if not services_ok["redis"]:
                try:
                    result = subprocess.run(
                        ["docker-compose", "-f", compose_file, "exec", "-T", "redis", "redis-cli", "ping"],
                        cwd=compose_dir,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0 and "PONG" in result.stdout:
                        services_ok["redis"] = True
                        logger.info("Health: redis ready")
                    else:
                        all_ok = False
                except Exception:
                    all_ok = False
            # mosquitto
            if not services_ok["mosquitto"]:
                try:
                    result = subprocess.run(
                        ["docker-compose", "-f", compose_file, "exec", "-T", "mosquitto", "mosquitto_sub", "-h", "localhost", "-p", "1883", "-t", "$SYS/#", "-C", "1"],
                        cwd=compose_dir,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        services_ok["mosquitto"] = True
                        logger.info("Health: mosquitto ready")
                    else:
                        all_ok = False
                except Exception:
                    all_ok = False
            # laravel health
            if not services_ok["laravel"]:
                try:
                    import httpx
                    resp = httpx.get(os.getenv("LARAVEL_URL", "http://localhost:8081") + "/api/system/health", timeout=2.0)
                    if resp.status_code == 200:
                        services_ok["laravel"] = True
                        logger.info("Health: laravel ready")
                    else:
                        all_ok = False
                except Exception:
                    all_ok = False

            if all_ok:
                return
            time.sleep(2)
        logger.warning(f"Health wait timed out after {timeout}s, statuses: {services_ok}")
    
    def _run_migrations(self):
        """
        Выполнить php artisan migrate:fresh --seed если база пуста.
        """
        compose_file = self.compose_file
        compose_dir = os.path.dirname(compose_file) if os.path.dirname(compose_file) else os.getcwd()
        try:
            # Пробуем запросить одну таблицу; если нет — запускаем миграции
            import psycopg
            dsn = self.db_path or os.getenv("DATABASE_URL")
            if not dsn:
                db_host = os.getenv("DB_HOST", "localhost")
                db_port = os.getenv("DB_PORT", "5433")
                db_name = os.getenv("DB_DATABASE", "hydro_e2e")
                db_user = os.getenv("DB_USERNAME", "hydro")
                db_pass = os.getenv("DB_PASSWORD", "hydro_e2e")
                dsn = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
            with psycopg.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("select 1 from information_schema.tables where table_name='migrations'")
                    if cur.fetchone():
                        return
        except Exception:
            # Если не удалось подключиться или таблицы нет — пробуем миграции
            pass

        logger.info("Running migrations in laravel container (migrate:fresh --seed)...")
        if self._use_docker_cli():
            container = self._resolve_container_name("laravel")
            result = subprocess.run(
                ["docker", "exec", "-T", container, "php", "artisan", "migrate:fresh", "--seed"],
                capture_output=True,
                text=True,
                timeout=180,
            )
        else:
            result = subprocess.run(
                ["docker-compose", "-f", compose_file, "exec", "-T", "laravel", "php", "artisan", "migrate:fresh", "--seed"],
                cwd=compose_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )
        if result.returncode != 0:
            logger.error(f"Migrations failed: {result.stderr}")
            raise RuntimeError(f"Migrations failed: {result.stderr}")
        logger.info("✓ Migrations completed")

    def _api_items(self, response: Any) -> List[Dict[str, Any]]:
        """
        Extract list payload from common Laravel API response envelopes.

        Supported shapes:
        - {"data": {"data": [...]}} (Laravel ResourceCollection)
        - {"data": [...]}          (plain list)
        - [...]                   (plain list)
        """
        if response is None:
            return []
        if isinstance(response, list):
            return [x for x in response if isinstance(x, dict)]
        if not isinstance(response, dict):
            return []

        data = response.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return [x for x in data.get("data") if isinstance(x, dict)]
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []
    
    def _resolve_variables(self, value: Any, required_vars: Optional[List[str]] = None) -> Any:
        """
        Resolve variables in value using the new VariableResolver.

        This method maintains backward compatibility while using the new modular approach.
        """
        if not self.variable_resolver:
            # Fallback to old logic if not initialized
            return self._resolve_variables_legacy(value, required_vars)

        # Update VariableResolver context to current context
        self.variable_resolver.context = self.context
        return self.variable_resolver.resolve_variables(value, required_vars)

    def _resolve_variables_legacy(self, value: Any, required_vars: Optional[List[str]] = None) -> Any:
        """
        Legacy variable resolution logic (kept for backward compatibility).
        """
        # This would contain the old implementation if needed
        # For now, we'll use the new resolver
        if self.variable_resolver:
            return self.variable_resolver.resolve_variables(value, required_vars)
        return value
    
    def _resolve_variable_expression(self, expr: str) -> Any:
        """
        Разрешить выражение переменной (например, "nodes.data[0].id").
        
        Args:
            expr: Выражение для разрешения
            
        Returns:
            Значение переменной
        """
        parts = re.split(r'[\.\[\]]+', expr)
        parts = [p for p in parts if p]  # Убираем пустые
        
        if not parts:
            return None
        
        var_name = parts[0]
        value = self.context.get(var_name)
        
        if value is None:
            return None
        
        # Обрабатываем доступы к полям и индексам
        for part in parts[1:]:
            if part.isdigit():
                # Индекс массива
                idx = int(part)
                if isinstance(value, (list, tuple)) and 0 <= idx < len(value):
                    value = value[idx]
                else:
                    return None
            else:
                # Поле объекта
                if isinstance(value, dict):
                    value = value.get(part)
                elif hasattr(value, part):
                    value = getattr(value, part)
                else:
                    return None
            
            if value is None:
                return None
        
        return value
    
    async def _ensure_test_zone_and_node(self):
        """
        Гарантирует наличие тестовых greenhouse/zone/node в БД для E2E.
        Использует значения по умолчанию из node-sim конфига (gh-test-1 / zn-test-1 / nd-ph-esp32una).
        """
        gh_uid = "gh-test-1"
        zone_uid = self.context.get("zone_uid") or "zn-test-1"
        node_uid = self.context.get("node_uid") or "nd-ph-esp32una"
        hardware_id = self.context.get("hardware_id") or "esp32-test-001"
        
        # Попытаться извлечь из setup.node_sim.config.node
        node_cfg = (((self.context.get("setup") or {}).get("node_sim") or {}).get("config") or {}).get("node", {})
        gh_uid = node_cfg.get("gh_uid") or gh_uid
        zone_uid = node_cfg.get("zone_uid") or zone_uid
        node_uid = node_cfg.get("node_uid") or node_uid
        hardware_id = node_cfg.get("hardware_id") or hardware_id
        
        # Greenhouse
        gh_rows = self.db.query(
            """
            INSERT INTO greenhouses (uid, name, provisioning_token, created_at, updated_at)
            VALUES (:uid, :name, :token, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            {"uid": gh_uid, "name": "Test Greenhouse", "token": f"prov-{gh_uid}"}
        )
        gh_id = gh_rows[0]["id"]
        
        # Zone
        zone_rows = self.db.query(
            """
            INSERT INTO zones (uid, name, status, greenhouse_id, created_at, updated_at)
            VALUES (:uid, :name, :status, :gh_id, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE SET greenhouse_id = EXCLUDED.greenhouse_id
            RETURNING id
            """,
            {"uid": zone_uid, "name": "Test Zone", "status": "online", "gh_id": gh_id}
        )
        zone_id = zone_rows[0]["id"]
        self.context["zone_id"] = zone_id
        self.context["zone_uid"] = zone_uid
        
        # Node
        node_rows = self.db.query(
            """
            INSERT INTO nodes (uid, name, type, status, lifecycle_state, zone_id, hardware_id, created_at, updated_at)
            VALUES (:uid, :name, :type, :status, :lifecycle_state, :zone_id, :hw_id, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE SET zone_id = EXCLUDED.zone_id
            RETURNING id, zone_id
            """,
            {
                "uid": node_uid,
                "name": "Test Node",
                "type": node_cfg.get("type") or "ph",
                "status": "online",
                "lifecycle_state": "ACTIVE",
                "zone_id": zone_id,
                "hw_id": hardware_id,
            }
        )
        node_id = node_rows[0]["id"]
        self.context["node_id"] = node_id
        self.context["node_uid"] = node_uid
    
    def _validate_critical_params(self, params: Dict[str, Any]):
        """
        Validate critical parameters using VariableResolver.
        """
        if not self.variable_resolver:
            return
        self.variable_resolver.validate_critical_params(params)
    
    def _validate_ws_channel_name(self, channel: str):
        """
        Validate WebSocket channel name using SchemaValidator.
        """
        if not self.schema_validator:
            return
        self.schema_validator.validate_ws_channel_name(channel)
    
    async def execute_step(self, step: Dict[str, Any]) -> Any:
        """
        Выполнить один шаг сценария.
        
        Args:
            step: Шаг из YAML сценария
            
        Returns:
            Результат выполнения шага
        """
        # Извлекаем имя шага и конфигурацию
        step_name = step.get("name", "unnamed")
        step_type = None
        step_config = None
        save_to = None
        
        # Ищем тип шага (api.get, ws.subscribe, etc.)
        for key in step.keys():
            if key != "name" and key != "save":
                step_type = key
                step_config = step[key]
                break
        
        # Проверяем, есть ли save на верхнем уровне
        if "save" in step:
            save_to = step["save"]
        
        # Если step_config - словарь, проверяем save внутри
        if isinstance(step_config, dict) and "save" in step_config:
            save_to = step_config.pop("save")
        
        # Разрешаем переменные в конфигурации
        step_config = self._resolve_variables(step_config) if step_config else {}
        
        logger.info(f"Executing step '{step_name}': {step_type}")
        
        # Добавляем в timeline с контекстными переменными
        timeline_data = dict(step_config)
        # Добавляем важные переменные контекста для отладки
        important_vars = {k: v for k, v in self.context.items() if k.endswith("_id") or k in ("zone_uid", "node_uid")}
        if important_vars:
            timeline_data["_context"] = important_vars
        
        self.reporter.add_timeline_event(step_type or "unknown", f"Executing {step_name}", timeline_data)
        
        start_time = time.time()
        result = None
        error = None
        
        try:
            if step_type and step_type.startswith("api."):
                result = await self._execute_api_step(step_type, step_config)
            elif step_type and step_type.startswith("ws."):
                result = await self._execute_ws_step(step_type, step_config)
            elif step_type and step_type.startswith("db."):
                result = await self._execute_db_step(step_type, step_config)
            elif step_type and step_type.startswith("mqtt."):
                result = await self._execute_mqtt_step(step_type, step_config)
            elif step_type and step_type.startswith("assert."):
                result = await self._execute_assert_step(step_type, step_config)
            elif step_type in ("wait_until", "eventually", "sleep"):
                result = await self._execute_waiting_step(step_type, step_config)
            elif step_type == "wait_for_telemetry":
                result = await self._execute_db_step(step_type, step_config)
            elif step_type == "snapshot.fetch":
                result = await self._execute_snapshot_fetch(step_config)
            elif step_type == "events.replay":
                result = await self._execute_events_replay(step_config)
            elif step_type == "wait":
                seconds = float(step_config.get("seconds", step_config) if isinstance(step_config, dict) else step_config)
                await asyncio.sleep(seconds)
                result = None
            elif step_type == "set":
                # Сохранить значение в контекст
                for key, value in step_config.items():
                    resolved_value = self._resolve_variables(value)
                    self.context[key] = resolved_value
                    logger.info(f"Set context variable '{key}' = {resolved_value} (type: {type(resolved_value).__name__})")
                result = self.context
            elif step_type == "sleep":
                await asyncio.sleep(float(step_config))
                result = None
            elif step_type == "invalidate_auth_token":
                # Инвалидирует токен в AuthClient для тестирования re-auth
                if not self.auth_client:
                    raise RuntimeError("Cannot invalidate token: AuthClient not initialized")
                # Устанавливаем невалидный токен
                self.auth_client.__class__._token = "invalid_token_for_testing"
                self.auth_client.__class__._token_expires_at = None
                logger.info("Token invalidated for testing re-auth")
                result = {"token_invalidated": True}
            elif step_type == "create_ws_client_without_token":
                # Создает WSClient без токена для тестирования ошибок авторизации
                from .ws_client import WSClient
                self.ws_no_auth = WSClient(
                    ws_url=self.ws_url,
                    api_token=None,
                    auth_client=None,
                    api_url=self.api_url
                )
                logger.info("Created WSClient without token for testing")
                result = {"ws_no_auth_created": True}
            elif step_type == "ws_subscribe_without_auth":
                # Попытка подписки на приватный канал без токена (для тестирования ошибки)
                channel = step_config.get("channel")
                expect_error = step_config.get("expect_error", False)
                expected_error_message = step_config.get("expected_error_message", "")
                
                if not hasattr(self, 'ws_no_auth'):
                    raise RuntimeError("ws_no_auth client not created. Use 'create_ws_client_without_token' step first")
                
                # Подключаемся к WebSocket сначала
                if not self.ws_no_auth.connected:
                    await self.ws_no_auth.connect()
                
                try:
                    await self.ws_no_auth.subscribe(channel)
                    # Если подписка прошла без ошибки, но мы ожидали ошибку
                    if expect_error:
                        raise AssertionError(f"Expected error when subscribing to {channel} without token, but subscription succeeded")
                    result = {"subscribed": channel}
                except RuntimeError as e:
                    error_msg = str(e)
                    logger.info(f"Expected error occurred: {error_msg}")
                    if "save" in step_config:
                        self.context[step_config.get("save", "subscription_error")] = error_msg
                    if expect_error:
                        if expected_error_message and expected_error_message.lower() not in error_msg.lower():
                            raise AssertionError(f"Expected error message to contain '{expected_error_message}', but got: {error_msg}")
                        result = {"error": error_msg, "expected": True}
                    else:
                        raise
            else:
                raise ValueError(f"Unknown step type: {step_type}")
            
            # Сохраняем результат, если указано
            if save_to:
                self.context[save_to] = result
            
            duration = time.time() - start_time
            self.reporter.add_timeline_event(
                step_type or "unknown",
                f"Completed {step_name}",
                {"duration": duration, "result": result}
            )
            
            return result
            
        except Exception as e:
            error = str(e)
            duration = time.time() - start_time
            logger.error(f"Step '{step_name}' ({step_type}) failed: {e}")
            self.reporter.add_timeline_event(
                step_type or "unknown",
                f"Failed {step_name}",
                {"duration": duration, "error": error}
            )
            raise
    
    async def _execute_api_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """Выполнить API шаг."""
        if not self.api_executor:
            raise RuntimeError("API executor not initialized")

        # Map old step types to new ones
        step_type_mapping = {
            "api.get": "api_get",
            "api.post": "api_post",
            "api.put": "api_put",
            "api.patch": "api_patch",
            "api.delete": "api_delete",
            "api.items": "api_items"
        }

        new_step_type = step_type_mapping.get(step_type, step_type)
        result = await self.api_executor.execute_api_step(new_step_type, config)

        # Auto-extract IDs from API responses
        if "endpoint" in config:
            extracted = self.schema_validator.auto_extract_ids_from_api_response(config["endpoint"], result)
            self.context.update(extracted)

        return result
    
    def _auto_extract_ids_from_api_response(self, path: str, response: Any):
        """
        Автоматически извлекает zone_id/node_id из API ответов, если они не установлены в контексте.
        
        Args:
            path: Путь API запроса
            response: Ответ от API
        """
        # Извлекаем список элементов из ответа
        items = self._api_items(response)
        
        # Также пытаемся извлечь единичный объект из ответа (для GET /api/zones/123)
        single_item = None
        if isinstance(response, dict):
            data = response.get("data", response)
            if isinstance(data, dict) and "id" in data:
                single_item = data
        
        # Автозаполнение zone_id из /api/zones (список зон) или /api/zones/{id} (одна зона)
        if ("zone_id" not in self.context or self.context.get("zone_id") in (None, "")):
            zone_to_process = None
            
            # Проверяем путь для списка зон
            if path == "/api/zones" or path.endswith("/api/zones"):
                # Пытаемся найти zone по zone_uid из setup
                zone_uid = None
                node_cfg = (((self.context.get("setup") or {}).get("node_sim") or {}).get("config") or {}).get("node", {})
                zone_uid = node_cfg.get("zone_uid")
                
                for zone in items:
                    if zone_uid and zone.get("uid") == zone_uid:
                        zone_to_process = zone
                        break
                    elif not zone_uid and zone.get("id"):
                        # Если zone_uid не указан, берем первый доступный
                        zone_to_process = zone
                        break
            
            # Проверяем путь для одной зоны (GET /api/zones/{id})
            elif single_item and "/api/zones/" in path and path != "/api/zones":
                zone_to_process = single_item
            
            # Обрабатываем найденную зону
            if zone_to_process:
                zone_id = zone_to_process.get("id")
                if zone_id:
                    self.context["zone_id"] = zone_id
                    if zone_to_process.get("uid"):
                        self.context["zone_uid"] = zone_to_process.get("uid")
                    logger.info(f"Auto-extracted zone_id={zone_id} from API response (path: {path})")
        
        # Автозаполнение node_id из /api/nodes (список узлов) или /api/nodes/{id} (один узел)
        if ("node_id" not in self.context or self.context.get("node_id") in (None, "")):
            node_to_process = None
            
            # Проверяем путь для списка узлов
            if path == "/api/nodes" or path.endswith("/api/nodes"):
                # Пытаемся найти node по node_uid из setup
                node_uid = None
                node_cfg = (((self.context.get("setup") or {}).get("node_sim") or {}).get("config") or {}).get("node", {})
                node_uid = node_cfg.get("node_uid")
                
                for node in items:
                    if node_uid and node.get("uid") == node_uid:
                        node_to_process = node
                        break
                    elif not node_uid and node.get("id"):
                        # Если node_uid не указан, берем первый доступный
                        node_to_process = node
                        break
            
            # Проверяем путь для одного узла (GET /api/nodes/{id})
            elif single_item and "/api/nodes/" in path and path != "/api/nodes":
                node_to_process = single_item
            
            # Обрабатываем найденный узел
            if node_to_process:
                node_id = node_to_process.get("id")
                if node_id:
                    self.context["node_id"] = node_id
                    if node_to_process.get("uid"):
                        self.context["node_uid"] = node_to_process.get("uid")
                    # Также извлекаем zone_id если он есть в node
                    if node_to_process.get("zone_id") and ("zone_id" not in self.context or self.context.get("zone_id") in (None, "")):
                        self.context["zone_id"] = node_to_process.get("zone_id")
                    logger.info(f"Auto-extracted node_id={node_id} from API response (path: {path})")
    
    async def _execute_ws_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """Выполнить WebSocket шаг."""
        if not self.ws_executor:
            raise RuntimeError("WebSocket executor not initialized")

        # Map old step types to new ones
        step_type_mapping = {
            "websocket.subscribe": "websocket_subscribe",
            "websocket.unsubscribe": "websocket_unsubscribe",
            "websocket.send": "websocket_send",
            "ws.wait_event": "websocket_event",
            "ws.wait_event_count": "websocket_event_count",
            "ws.subscribe_without_auth": "ws_subscribe_without_auth"
        }

        new_step_type = step_type_mapping.get(step_type, step_type)
        return await self.ws_executor.execute_ws_step(new_step_type, config)
    
    async def _execute_db_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """Выполнить DB шаг."""
        if not self.db_executor:
            raise RuntimeError("Database executor not initialized")

        # Map old step types to new ones
        step_type_mapping = {
            "database.query": "database_query",
            "database.execute": "database_execute",
            "db.wait": "db_wait",
            "wait_for_telemetry": "wait_for_telemetry"
        }

        new_step_type = step_type_mapping.get(step_type, step_type)
        return await self.db_executor.execute_db_step(new_step_type, config)
    
    async def _execute_mqtt_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """Выполнить MQTT шаг."""
        if not self.mqtt_executor:
            raise RuntimeError("MQTT executor not initialized")

        # Map old step types to new ones
        step_type_mapping = {
            "mqtt.subscribe": "mqtt_subscribe",
            "mqtt.publish": "mqtt_publish",
            "mqtt.wait_message": "mqtt_wait_message"
        }

        new_step_type = step_type_mapping.get(step_type, step_type)
        return await self.mqtt_executor.execute_mqtt_step(new_step_type, config)

    async def _execute_waiting_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """Выполнить waiting шаг."""
        if not self.waiting_executor:
            raise RuntimeError("Waiting executor not initialized")

        return await self.waiting_executor.execute_waiting_step(step_type, config)
    
    async def _execute_assert_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """Выполнить assertion шаг."""
        assert_type = step_type.split(".")[1]  # monotonic_command_status, alert_dedup_count, etc.
        
        if assert_type == "monotonic_command_status":
            commands = config["commands"]
            return self.assertions.monotonic_command_status(commands)
        elif assert_type == "alert_dedup_count":
            alerts = config["alerts"]
            max_duplicates = config.get("max_duplicates", 1)
            return self.assertions.alert_dedup_count(alerts, max_duplicates)
        elif assert_type == "unassigned_present":
            nodes = config["nodes"]
            expected_count = config.get("expected_count")
            return self.assertions.unassigned_present(nodes, expected_count)
        elif assert_type == "attached":
            nodes = config["nodes"]
            expected_count = config.get("expected_count")
            return self.assertions.attached(nodes, expected_count)
        elif assert_type == "equals":
            actual = config["actual"]
            expected = config["expected"]
            message = config.get("message")
            return self.assertions.equals(actual, expected, message)
        elif assert_type == "contains":
            container = config["container"]
            item = config["item"]
            message = config.get("message")
            return self.assertions.contains(container, item, message)
        else:
            raise ValueError(f"Unknown assertion type: {assert_type}")
    
    async def _execute_snapshot_fetch(self, config: Dict[str, Any]) -> Any:
        """Выполнить snapshot.fetch - получить снимок состояния."""
        zone_id = config.get("zone_id")
        if not zone_id:
            # Пытаемся получить zone_id из контекста
            zone_id = self.context.get("zone_id")
        if not zone_id:
            raise ValueError(
                "snapshot.fetch requires zone_id. "
                "Убедитесь, что zone_id установлен в контексте через API запрос или setup."
            )
        
        result = await self.api.get(f"/api/zones/{zone_id}/snapshot")
        # Сохраняем в контекст
        self.context["snapshot"] = result
        # Извлекаем last_event_id для удобства
        if isinstance(result, dict):
            data = result.get("data", result)
            if isinstance(data, dict) and "last_event_id" in data:
                last_event_id = data["last_event_id"]
                self.context["last_event_id"] = last_event_id
                logger.info(f"Snapshot fetched: zone_id={zone_id}, last_event_id={last_event_id}")
        return result
    
    async def _execute_events_replay(self, config: Dict[str, Any]) -> Any:
        """Выполнить events.replay - получить события после last_event_id."""
        zone_id = config.get("zone_id") or self.context.get("zone_id")
        after_id = config.get("after_id") or self.context.get("last_event_id")
        limit = config.get("limit", 50)
        
        if not zone_id:
            raise ValueError("events.replay requires zone_id")
        if after_id is None:
            raise ValueError("events.replay requires after_id (use snapshot.fetch first)")
        
        result = await self.api.get(
            f"/api/zones/{zone_id}/events",
            params={"after_id": after_id, "limit": limit}
        )
        # Сохраняем в контекст
        self.context["events_replay"] = result
        
        # Проверяем порядок event_id в событиях (gap detection)
        if isinstance(result, dict):
            events = result.get("data", result.get("events", []))
            if isinstance(events, list) and len(events) > 0:
                # Фильтруем только int event_id
                event_ids = [
                    e.get("id") for e in events 
                    if isinstance(e, dict) and isinstance(e.get("id"), int)
                ]
                if len(event_ids) > 1:
                    # Проверяем, что event_id монотонно возрастают
                    for i in range(1, len(event_ids)):
                        if event_ids[i] <= event_ids[i-1]:
                            logger.warning(
                                f"Event ID order violation in replay: event_ids={event_ids}. "
                                f"Events may be out of order or duplicate."
                            )
                            break
                    # Проверяем gap между after_id и первым событием
                    if event_ids and after_id is not None:
                        first_event_id = event_ids[0]
                        if isinstance(after_id, int) and isinstance(first_event_id, int):
                            gap = first_event_id - after_id
                            if gap > 1:
                                logger.warning(
                                    f"Event ID gap detected in replay: after_id={after_id}, "
                                    f"first_event_id={first_event_id}, gap={gap}. "
                                    f"Some events may be missing."
                                )

        # Initialize new modular components
        self.variable_resolver = VariableResolver(self.context)
        self.schema_validator = SchemaValidator(self.context)
        self.api_executor = APIStepExecutor(self.api, self.variable_resolver)
        self.ws_executor = WebSocketStepExecutor(self.ws, self.schema_validator)
        self.db_executor = DatabaseStepExecutor(self.db, self.variable_resolver)
        self.mqtt_executor = MQTTStepExecutor(self.mqtt, self.variable_resolver)
        self.waiting_executor = WaitingStepExecutor(self.variable_resolver)

        return result
    
    async def run_scenario(self, scenario_path: str) -> bool:
        """
        Запустить YAML сценарий.
        
        Args:
            scenario_path: Путь к YAML файлу сценария
            
        Returns:
            True если все тесты прошли успешно
        """
        scenario_path = Path(scenario_path)
        if not scenario_path.exists():
            raise FileNotFoundError(f"Scenario file not found: {scenario_path}")
        
        logger.info(f"Loading scenario: {scenario_path}")
        
        with open(scenario_path, "r", encoding="utf-8") as f:
            scenario = yaml.safe_load(f)
        
        scenario_name = scenario.get("name", scenario_path.stem)
        self.reporter.test_suite_name = scenario_name
        
        logger.info(f"Running scenario: {scenario_name}")
        
        # Инициализация
        await self.setup()

        # Базовые переменные времени
        now_s = int(time.time())
        self.context.setdefault("TIMESTAMP_S", now_s)
        self.context.setdefault("TIMESTAMP_MS", now_s * 1000)
        
        try:
            # Поддерживаем 2 формата сценариев:
            # 1) steps: (runner-native)
            # 2) setup/actions/assertions/cleanup: (pipeline E2E scenarios)
            if "steps" in scenario:
                return await self._run_steps_scenario(scenario, scenario_name)

            if "actions" in scenario:
                return await self._run_actions_scenario(scenario, scenario_name)

            raise ValueError("Scenario must contain either 'steps' or 'actions'")

        finally:
            await self.teardown()

    async def _run_steps_scenario(self, scenario: Dict[str, Any], scenario_name: str) -> bool:
        """Runner-native сценарий: steps: [...]"""
        steps = scenario.get("steps", [])
        test_start_time = time.time()

        for i, step in enumerate(steps):
            step_start_time = time.time()
            step_name = step.get("name", f"Step {i+1}")

            try:
                await self.execute_step(step)

                duration = time.time() - step_start_time
                self.reporter.add_test_case(
                    name=step_name,
                    status="passed",
                    duration=duration,
                    steps=[{"name": step_name, "status": "passed"}]
                )
            except Exception as e:
                duration = time.time() - step_start_time
                error_msg = str(e)
                logger.error(f"Step '{step_name}' failed: {error_msg}")

                self.reporter.add_test_case(
                    name=step_name,
                    status="failed",
                    duration=duration,
                    error_message=error_msg,
                    steps=[{"name": step_name, "status": "failed", "error": error_msg}]
                )

                if not scenario.get("continue_on_error", False):
                    break

        # Артефакты + отчеты
        ws_messages = self.ws.get_messages(50) if self.ws else []
        mqtt_messages = self.mqtt.get_messages(50) if self.mqtt else []
        self.reporter.add_artifacts(
            scenario_name,
            ws_messages=ws_messages,
            mqtt_messages=mqtt_messages
        )

        reports = self.reporter.generate_all()
        logger.info(f"Reports generated: {reports}")

        passed = sum(1 for tc in self.reporter.test_cases if tc["status"] == "passed")
        failed = sum(1 for tc in self.reporter.test_cases if tc["status"] == "failed")
        logger.info(f"Scenario '{scenario_name}' completed: {passed} passed, {failed} failed")
        return failed == 0

    async def _run_actions_scenario(self, scenario: Dict[str, Any], scenario_name: str) -> bool:
        """
        Pipeline сценарий: setup/actions/assertions/cleanup.
        """
        test_start_time = time.time()

        # setup (пока только сохраняем конфиг в контекст)
        setup = scenario.get("setup", {})
        if setup:
            self.context["setup"] = setup
            # Попробуем вывести zone_id/node_id из API по uid (если доступно)
            try:
                node_cfg = (((setup.get("node_sim") or {}).get("config") or {}).get("node") or {})
                zone_uid = node_cfg.get("zone_uid")
                node_uid = node_cfg.get("node_uid")

                if zone_uid and zone_uid != "null" and self.api:
                    zones = await self.api.get("/api/zones")
                    for z in self._api_items(zones):
                        if z.get("uid") == zone_uid:
                            self.context["zone_id"] = z.get("id")
                            break

                if node_uid and self.api:
                    nodes = await self.api.get("/api/nodes")
                    for n in self._api_items(nodes):
                        if n.get("uid") == node_uid:
                            self.context["node_id"] = n.get("id")
                            if "zone_id" not in self.context and n.get("zone_id"):
                                self.context["zone_id"] = n.get("zone_id")
                            break
            except Exception:
                # Если API не готов или не содержит данных - сценарий сам выявит проблему
                pass

        # Если после setup не найден zone_id, создаём тестовые greenhouse/zone/node в БД
        if "zone_id" not in self.context or self.context.get("zone_id") in (None, ""):
            try:
                await self._ensure_test_zone_and_node()
            except Exception as e:
                logger.warning(f"Failed to ensure test zone/node: {e}")

        # actions
        actions = scenario.get("actions") or []
        for i, action in enumerate(actions):
            step_name = action.get("step", action.get("name", f"Action {i+1}"))
            step_type = action.get("type")
            wait_seconds = float(action.get("wait_seconds", 0) or 0)
            optional = bool(action.get("optional", False))

            action_cfg = {k: v for k, v in action.items() if k not in ("step", "name", "type", "wait_seconds", "config_ref")}
            action_cfg = self._resolve_variables(action_cfg)

            step_start_time = time.time()
            try:
                await self._execute_action_step(step_type, action_cfg, action)

                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)

                # Обновляем node_id/zone_id если появились (например после node_hello)
                try:
                    node_cfg = (((setup.get("node_sim") or {}).get("config") or {}).get("node") or {})
                    node_uid = node_cfg.get("node_uid")
                    if node_uid and "node_id" not in self.context and self.api:
                        nodes = await self.api.get("/api/nodes")
                        for n in self._api_items(nodes):
                            if n.get("uid") == node_uid:
                                self.context["node_id"] = n.get("id")
                                if "zone_id" not in self.context and n.get("zone_id"):
                                    self.context["zone_id"] = n.get("zone_id")
                                break
                except Exception:
                    pass

                duration = time.time() - step_start_time
                self.reporter.add_test_case(
                    name=step_name,
                    status="passed",
                    duration=duration,
                    steps=[{"name": step_name, "status": "passed"}]
                )
            except Exception as e:
                duration = time.time() - step_start_time
                error_msg = str(e)
                if optional:
                    logger.warning(f"Optional action '{step_name}' ({step_type}) failed: {error_msg}")
                    self.reporter.add_test_case(
                        name=step_name,
                        status="skipped",
                        duration=duration,
                        error_message=error_msg,
                        steps=[{"name": step_name, "status": "skipped", "error": error_msg}]
                    )
                    continue
                logger.error(f"Action '{step_name}' ({step_type}) failed: {error_msg}")
                self.reporter.add_test_case(
                    name=step_name,
                    status="failed",
                    duration=duration,
                    error_message=error_msg,
                    steps=[{"name": step_name, "status": "failed", "error": error_msg}]
                )
                if not scenario.get("continue_on_error", False):
                    break

        # assertions
        assertions = scenario.get("assertions", [])
        for i, assertion in enumerate(assertions):
            name = assertion.get("name", f"Assertion {i+1}")
            a_type = assertion.get("type")
            optional = bool(assertion.get("optional", False))
            step_start_time = time.time()
            try:
                await self._execute_assertion(a_type, assertion)
                duration = time.time() - step_start_time
                self.reporter.add_test_case(
                    name=name,
                    status="passed",
                    duration=duration,
                    steps=[{"name": name, "status": "passed"}]
                )
            except Exception as e:
                duration = time.time() - step_start_time
                error_msg = str(e)
                if optional:
                    logger.warning(f"Optional assertion '{name}' skipped due to error: {error_msg}")
                    self.reporter.add_test_case(
                        name=name,
                        status="skipped",
                        duration=duration,
                        error_message=error_msg,
                        steps=[{"name": name, "status": "skipped", "error": error_msg}]
                    )
                    continue
                logger.error(f"Assertion '{name}' failed: {error_msg}")
                self.reporter.add_test_case(
                    name=name,
                    status="failed",
                    duration=duration,
                    error_message=error_msg,
                    steps=[{"name": name, "status": "failed", "error": error_msg}]
                )
                if not scenario.get("continue_on_error", False):
                    break

        # cleanup (best-effort)
        cleanup = scenario.get("cleanup", [])
        for c in cleanup:
            try:
                c_type = c.get("type")
                wait_seconds = float(c.get("wait_seconds", 0) or 0)
                c_cfg = {k: v for k, v in c.items() if k not in ("step", "name", "type", "wait_seconds")}
                c_cfg = self._resolve_variables(c_cfg)
                await self._execute_action_step(c_type, c_cfg, c)
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
            except Exception:
                pass

        # artifacts + reports
        ws_messages = self.ws.get_messages(50) if self.ws else []
        mqtt_messages = self.mqtt.get_messages(50) if self.mqtt else []
        
        # Собираем последние API запросы из timeline
        # Поддерживаем оба формата: api.get (steps) и api_get (actions)
        api_requests = [
            event for event in self.reporter.timeline 
            if event.get("type", "").startswith("api.") or event.get("type", "").startswith("api_")
        ][-50:]
        
        # Извлекаем важные переменные контекста
        context_vars = {
            k: v for k, v in self.context.items() 
            if k.endswith("_id") or k in ("zone_uid", "node_uid", "last_event_id", "snapshot")
        }
        
        # Добавляем last_event_id из WS если доступен
        if self.ws and hasattr(self.ws, 'get_last_event_id'):
            last_event_id = self.ws.get_last_event_id()
            if last_event_id is not None:
                context_vars["ws_last_event_id"] = last_event_id
        
        self.reporter.add_artifacts(
            scenario_name,
            ws_messages=ws_messages,
            mqtt_messages=mqtt_messages,
            api_responses=api_requests,
            context_vars=context_vars
        )
        reports = self.reporter.generate_all()
        logger.info(f"Reports generated: {reports}")

        passed = sum(1 for tc in self.reporter.test_cases if tc["status"] == "passed")
        failed = sum(1 for tc in self.reporter.test_cases if tc["status"] == "failed")
        logger.info(f"Scenario '{scenario_name}' completed: {passed} passed, {failed} failed")
        return failed == 0

    async def _execute_action_step(self, step_type: Optional[str], cfg: Dict[str, Any], raw: Dict[str, Any]):
        if not step_type:
            raise ValueError("Action step missing 'type'")

        # Set variables in context (pipeline scenarios convenience)
        if step_type == "set":
            for k, v in cfg.items():
                self.context[k] = self._resolve_variables(v)
            return
        # Simulator control (delegate to docker-compose node-sim service)
        if step_type == "start_simulator":
            # При необходимости создаем временный конфиг node-sim и монтируем через NODE_SIM_CONFIG
            cfg_ref = raw.get("config_ref")
            if cfg_ref:
                # cfg_ref формат: dotted path, например node_sim.config (или setup.node_sim.config)
                sim_cfg = self._resolve_variable_expression(cfg_ref)
                if not sim_cfg and "setup" in self.context:
                    sim_cfg = self._resolve_variable_expression(f"setup.{cfg_ref}")
                if sim_cfg:
                    import tempfile, yaml
                    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml")
                    yaml.safe_dump(sim_cfg, tmp)
                    tmp.flush()
                    self.context["_node_sim_config_path"] = tmp.name
                    os.environ["NODE_SIM_CONFIG"] = tmp.name
                    logger.info(f"Generated node-sim config at {tmp.name}")
            await self._fault_restore("node-sim")
            return
        if step_type == "stop_simulator":
            await self._fault_inject("node-sim", "stop", None)
            return
        
        # Fault injection (docker-compose services)
        if step_type in ("fault.inject", "fault_inject"):
            service = cfg.get("service")
            action = cfg.get("action", "stop")
            duration_s = cfg.get("duration_s", None)
            
            if not service:
                raise ValueError("fault.inject requires 'service' parameter")
            
            await self._fault_inject(service, action, duration_s)
            return
        
        if step_type in ("fault.restore", "fault_restore"):
            service = cfg.get("service")
            if not service:
                raise ValueError("fault.restore requires 'service' parameter")
            await self._fault_restore(service)
            return
        
        # Legacy system control (deprecated, use fault.inject instead)
        if step_type == "system_stop":
            service = cfg.get("service")
            await self._fault_inject(service, "stop", None)
            return
        if step_type == "system_start":
            service = cfg.get("service")
            await self._fault_restore(service)
            return
        
        # Sleep/wait
        if step_type in ("sleep", "wait"):
            seconds = float(cfg.get("seconds", cfg.get("wait_seconds", 1.0)))
            await asyncio.sleep(seconds)
            return

        # MQTT publish
        if step_type in ("publish_mqtt", "mqtt_publish"):
            topic = cfg["topic"]
            payload = cfg.get("payload", {})
            qos = int(cfg.get("qos", 1))
            retain = bool(cfg.get("retain", False))
            
            def _coerce_numbers(val):
                if isinstance(val, str):
                    try:
                        # Поддержка целых/float строк (включая отрицательные)
                        if re.fullmatch(r"-?\d+", val):
                            return int(val)
                        if re.fullmatch(r"-?\d+\.\d+", val):
                            return float(val)
                    except Exception:
                        return val
                    return val
                if isinstance(val, dict):
                    return {k: _coerce_numbers(v) for k, v in val.items()}
                if isinstance(val, list):
                    return [_coerce_numbers(v) for v in val]
                return val

            payload = _coerce_numbers(payload)
            self.mqtt.publish_json(topic, payload, qos=qos, retain=retain)
            return
        if step_type == "mqtt_publish_multiple":
            messages = cfg.get("messages", [])
            for msg in messages:
                topic = msg["topic"]
                payload = msg.get("payload", {})
                qos = int(msg.get("qos", 1))
                retain = bool(msg.get("retain", False))
                self.mqtt.publish_json(topic, payload, qos=qos, retain=retain)
            return

        # HTTP request (full URL)
        if step_type == "http_request":
            import httpx
            method = (cfg.get("method") or "GET").upper()
            url = cfg.get("url")
            if not url:
                raise ValueError("http_request requires url")
            headers = cfg.get("headers") or {}
            body = cfg.get("body")
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(method, url, headers=headers, json=body)
            self.context[cfg.get("capture_response", "last_http")] = {
                "status_code": resp.status_code,
                "text": resp.text,
                "json": (resp.json() if resp.headers.get("content-type","").startswith("application/json") else None),
            }
            return

        # API shortcuts
        if step_type in ("api_get", "api_post", "api_put", "api_patch", "api_delete"):
            endpoint = cfg.get("endpoint") or cfg.get("path")
            if not endpoint:
                raise ValueError(f"{step_type} requires endpoint")
            # Разрешаем переменные в endpoint
            endpoint = self._resolve_variables(endpoint)
            payload = cfg.get("payload") or cfg.get("json") or cfg.get("data")
            # Разрешаем переменные в payload
            if payload:
                payload = self._resolve_variables(payload)
            if step_type == "api_get":
                res = await self.api.get(endpoint, params=cfg.get("params"))
            elif step_type == "api_post":
                expected_status = cfg.get("expected_status")
                # Если указан expected_status, делаем запрос напрямую через httpx
                # чтобы получить ответ даже при ошибке
                if expected_status:
                    import httpx
                    headers = await self.api._get_headers()
                    url = urljoin(self.api.base_url + "/", endpoint.lstrip("/"))
                    async with httpx.AsyncClient(timeout=self.api.timeout) as client:
                        response = await client.post(url, json=payload, headers=headers)
                        self.api._last_response = response
                        if response.status_code == expected_status:
                            res = response.json()
                        else:
                            response.raise_for_status()
                            res = response.json()
                    # Для expected_status сохраняем также response данные
                    res = {
                        'data': res,
                        'status_code': response.status_code,
                        'headers': dict(response.headers),
                    }
                else:
                    res = await self.api.post(endpoint, json=payload)
                # Автозаполнение zone_id/node_id из API ответов
                self._auto_extract_ids_from_api_response(endpoint, res)
            elif step_type == "api_put":
                res = await self.api.put(endpoint, json=payload)
                # Автозаполнение zone_id/node_id из API ответов
                self._auto_extract_ids_from_api_response(endpoint, res)
            elif step_type == "api_patch":
                # APIClient doesn't have patch currently; use httpx under the hood
                res = await self.api.request("PATCH", endpoint, json=payload)
                # Автозаполнение zone_id/node_id из API ответов
                self._auto_extract_ids_from_api_response(endpoint, res)
            else:
                res = await self.api.delete(endpoint)
                # Автозаполнение zone_id/node_id из API ответов (если DELETE возвращает данные)
                self._auto_extract_ids_from_api_response(endpoint, res)
            # Проверяем expected_status, если указан (для случаев когда не было ошибки)
            expected_status = cfg.get("expected_status")
            if expected_status:
                last_response = self.api.get_last_response()
                if last_response and last_response.status_code != expected_status:
                    raise AssertionError(f"Expected status {expected_status}, got {last_response.status_code}")
            if "save" in cfg:
                self.context[cfg["save"]] = res
            return

        # WebSocket control
        if step_type == "websocket_connect":
            await self.ws.connect()
            return
        if step_type == "websocket_disconnect":
            await self.ws.disconnect()
            return
        if step_type in ("websocket_subscribe", "ws_subscribe"):
            channel = cfg["channel"]
            # Валидация канала перед подпиской
            self._validate_ws_channel_name(channel)
            await self.ws.subscribe(channel)
            return
        if step_type == "websocket_unsubscribe":
            # Просто игнорируем, т.к. в текущей реализации нет явной отписки
            logger.info("websocket_unsubscribe (noop)")
            return
        if step_type == "websocket_event":
            event_type = cfg.get("event_type") or cfg.get("event")
            timeout = float(cfg.get("timeout_seconds", cfg.get("timeout", 10.0)))
            filter_dict = cfg.get("filter")
            if filter_dict:
                filter_dict = self._resolve_variables(filter_dict)
            lookback = cfg.get("lookback_messages")
            if lookback is None and filter_dict:
                lookback = 100
            if lookback is not None:
                lookback = int(lookback)
            ev = await self.ws.wait_event(event_type, timeout=timeout, filter=filter_dict, lookback=lookback)
            if ev is None:
                raise TimeoutError(f"Timeout waiting for WebSocket event: {event_type}")
            if isinstance(ev, dict):
                raw_data = ev.get("data")
                if isinstance(raw_data, str):
                    try:
                        import json
                        ev["data"] = json.loads(raw_data)
                    except Exception:
                        pass
            if "save" in cfg:
                self.context[cfg["save"]] = ev
            return ev
        if step_type == "create_ws_client_without_token":
            # Создает WSClient без токена для тестирования ошибок авторизации
            from .ws_client import WSClient
            self.ws_no_auth = WSClient(
                ws_url=self.ws_url,
                api_token=None,
                auth_client=None,
                api_url=self.api_url
            )
            logger.info("Created WSClient without token for testing")
            return {"ws_no_auth_created": True}
        if step_type == "ws_subscribe_without_auth":
            # Попытка подписки на приватный канал без токена (для тестирования ошибки)
            channel = cfg["channel"]
            # Валидация канала даже для негативных сценариев — чтобы отлавливать пустые zone_id
            self._validate_ws_channel_name(channel)
            expect_error = cfg.get("expect_error", True)  # По умолчанию ожидаем ошибку
            expected_error_message = cfg.get("expected_error_message", "")
            
            if not hasattr(self, 'ws_no_auth'):
                raise RuntimeError("ws_no_auth client not created. Use 'create_ws_client_without_token' step first")
            
            # Подключаемся к WebSocket сначала
            if not self.ws_no_auth.connected:
                await self.ws_no_auth.connect()
            
            try:
                await self.ws_no_auth.subscribe(channel)
                # Если подписка прошла без ошибки, но мы ожидали ошибку
                if expect_error:
                    raise AssertionError(f"Expected error when subscribing to {channel} without token, but subscription succeeded")
                return {"subscribed": channel}
            except RuntimeError as e:
                error_msg = str(e)
                logger.info(f"Expected error occurred: {error_msg}")
                if "save" in cfg:
                    self.context[cfg.get("save", "subscription_error")] = error_msg
                if expect_error:
                    if expected_error_message and expected_error_message.lower() not in error_msg.lower():
                        raise AssertionError(f"Expected error message to contain '{expected_error_message}', but got: {error_msg}")
                    return {"error": error_msg, "expected": True}
                raise

        # Auth token invalidation
        if step_type == "invalidate_auth_token":
            if not self.auth_client:
                raise RuntimeError("Cannot invalidate token: AuthClient not initialized")
            # Устанавливаем невалидный токен напрямую
            cls = self.auth_client.__class__
            cls._token = "invalid_token_for_testing"
            cls._token_expires_at = None
            # Дублируем на инстансе для совместимости
            self.auth_client._token = cls._token
            self.auth_client._token_expires_at = cls._token_expires_at
            logger.info("Token invalidated for testing re-auth")
            return
        
        # Create WS client without token
        if step_type == "create_ws_client_without_token":
            from .ws_client import WSClient
            self.ws_no_auth = WSClient(
                ws_url=self.ws_url,
                api_token=None,  # Без токена
                auth_client=None,  # Без auth_client
                api_url=self.api_url
            )
            logger.info("Created WebSocket client without authentication")
            return

        # WS subscribe without auth (expects error)
        if step_type == "ws_subscribe_without_auth":
            channel = cfg.get("channel")
            expect_error = cfg.get("expect_error", True)  # По умолчанию ожидаем ошибку
            
            if not hasattr(self, 'ws_no_auth'):
                raise RuntimeError("ws_no_auth client not created. Use 'create_ws_client_without_token' step first")
            
            # Подключаемся к WebSocket сначала
            if not self.ws_no_auth.connected:
                await self.ws_no_auth.connect()
            
            try:
                await self.ws_no_auth.subscribe(channel)
                # Если подписка прошла без ошибки, но мы ожидали ошибку
                if expect_error:
                    raise AssertionError(f"Expected error when subscribing to {channel} without token, but subscription succeeded")
                return {"subscribed": channel}
            except RuntimeError as e:
                error_msg = str(e)
                logger.info(f"Expected error occurred: {error_msg}")
                if "save" in cfg:
                    self.context[cfg.get("save", "subscription_error")] = error_msg
                if expect_error:
                    # Это ожидаемая ошибка, не выбрасываем исключение
                    return {"error": error_msg, "expected": True}
                raise

        # DB query in actions (rare)
        if step_type == "database_query":
            query = cfg["query"]
            params = cfg.get("params", {})
            params = self._resolve_variables(params) if params else {}
            self._validate_critical_params(params)
            result = self.db.query(query, params=params)
            # Валидируем expected_rows если указан (DoD требует валидацию результата)
            expected_rows = cfg.get("expected_rows")
            if expected_rows is not None:
                actual_rows = len(result)
                if actual_rows != expected_rows:
                    raise AssertionError(f"Expected {expected_rows} rows from database_query, got {actual_rows}")
            if "save" in cfg:
                self.context[cfg["save"]] = result
            return result

        # DB wait in actions (used in command scenarios)
        if step_type in ("db.wait", "db_wait"):
            query = cfg["query"]
            params = cfg.get("params", {})
            params = self._resolve_variables(params) if params else {}
            timeout = float(cfg.get("timeout", 10.0))
            expected_rows = cfg.get("expected_rows")
            self._validate_critical_params(params)
            rows = await self.db.wait(query, params=params, timeout=timeout, expected_rows=expected_rows)
            if "save" in cfg:
                self.context[cfg["save"]] = rows
            return rows

        # DB execute (DELETE, UPDATE, INSERT)
        if step_type in ("db.execute", "database_execute"):
            query = cfg["query"]
            params = cfg.get("params", {})
            params = self._resolve_variables(params) if params else {}
            result = self.db.execute(query, params=params)
            if "save" in cfg:
                self.context[cfg["save"]] = result
            return result

        # Snapshot fetch
        if step_type == "snapshot.fetch":
            zone_id = cfg.get("zone_id") or self.context.get("zone_id")
            if not zone_id:
                raise ValueError("snapshot.fetch requires zone_id")
            result = await self.api.get(f"/api/zones/{zone_id}/snapshot")
            if "save" in cfg:
                self.context[cfg["save"]] = result
            # Извлекаем last_event_id для удобства
            if isinstance(result, dict):
                data = result.get("data", result)
                if isinstance(data, dict) and "last_event_id" in data:
                    self.context["last_event_id"] = data["last_event_id"]
            return

        # Events replay
        if step_type == "events.replay":
            zone_id = cfg.get("zone_id") or self.context.get("zone_id")
            after_id = cfg.get("after_id") or self.context.get("last_event_id")
            limit = cfg.get("limit", 50)
            if not zone_id:
                raise ValueError("events.replay requires zone_id")
            if after_id is None:
                raise ValueError("events.replay requires after_id (use snapshot.fetch first)")
            result = await self.api.get(
                f"/api/zones/{zone_id}/events",
                params={"after_id": after_id, "limit": limit}
            )
            if "save" in cfg:
                self.context[cfg["save"]] = result
            return

        # Scrape metrics from automation-engine
        if step_type == "scrape_metrics":
            import httpx
            automation_engine_url = cfg.get("url", "http://localhost:9401")
            metric_name = cfg.get("metric")
            timeout = float(cfg.get("timeout", 10.0))
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(f"{automation_engine_url}/metrics")
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to scrape metrics: {resp.status_code}")
                
                # Парсим Prometheus формат
                metrics_text = resp.text
                result = {}
                
                if metric_name:
                    # Ищем конкретную метрику
                    import re
                    pattern = rf"^{re.escape(metric_name)}\s+([0-9.]+)"
                    for line in metrics_text.split("\n"):
                        match = re.match(pattern, line)
                        if match:
                            result[metric_name] = float(match.group(1))
                            break
                else:
                    # Парсим все метрики (упрощенный вариант)
                    import re
                    for line in metrics_text.split("\n"):
                        if line and not line.startswith("#"):
                            parts = line.split()
                            if len(parts) >= 2:
                                metric_key = parts[0].split("{")[0]  # Убираем labels
                                try:
                                    result[metric_key] = float(parts[-1])
                                except ValueError:
                                    pass
                
                if "save" in cfg:
                    self.context[cfg["save"]] = result
                return result

        # Wait for zone event
        if step_type == "wait_zone_event":
            zone_id = cfg.get("zone_id") or self.context.get("zone_id")
            event_type = cfg.get("event_type")
            filter_dict = cfg.get("filter", {})
            timeout = float(cfg.get("timeout", 30.0))
            optional = cfg.get("optional", False)
            
            if not zone_id:
                raise ValueError("wait_zone_event requires zone_id")
            
            # Используем db.wait для ожидания события в zone_events
            # Согласно миграции, таблица zone_events использует поле 'details' (JSONB), а не 'payload_json'
            query = """
                SELECT id, type, details, created_at
                FROM zone_events
                WHERE zone_id = :zone_id
            """
            params = {"zone_id": zone_id}
            
            if event_type:
                query += " AND type = :event_type"
                params["event_type"] = event_type
            
            # Добавляем фильтры по details (JSONB)
            if filter_dict:
                for key, value in filter_dict.items():
                    query += f" AND details->>'{key}' = :filter_{key}"
                    params[f"filter_{key}"] = str(value)
            
            query += " ORDER BY created_at DESC LIMIT 1"
            
            try:
                rows = await self.db.wait(query, params=params, timeout=timeout, expected_rows=1)
                if rows and len(rows) > 0:
                    event = rows[0]
                    if "save" in cfg:
                        self.context[cfg["save"]] = event
                    return event
                elif not optional:
                    raise TimeoutError(f"Timeout waiting for zone event: {event_type or 'any'}")
                return None
            except Exception as e:
                if optional:
                    return None
                raise

        # Wait for command
        if step_type == "wait_command":
            zone_id = cfg.get("zone_id") or self.context.get("zone_id")
            command_filter = cfg.get("filter", {})
            timeout = float(cfg.get("timeout", 30.0))
            optional = cfg.get("optional", False)
            
            if not zone_id:
                raise ValueError("wait_command requires zone_id")
            
            query = """
                SELECT id, cmd, status, source, created_at, updated_at
                FROM commands
                WHERE zone_id = :zone_id
            """
            params = {"zone_id": zone_id}
            
            # Фильтры
            if "cmd" in command_filter:
                query += " AND cmd = :cmd"
                params["cmd"] = command_filter["cmd"]
            if "source" in command_filter:
                query += " AND source = :source"
                params["source"] = command_filter["source"]
            if "status" in command_filter:
                query += " AND status = :status"
                params["status"] = command_filter["status"]
            
            query += " ORDER BY created_at DESC LIMIT 1"
            
            try:
                rows = await self.db.wait(query, params=params, timeout=timeout, expected_rows=1)
                if rows and len(rows) > 0:
                    command = rows[0]
                    if "save" in cfg:
                        self.context[cfg["save"]] = command
                    return command
                elif not optional:
                    raise TimeoutError("Timeout waiting for command")
                return None
            except Exception as e:
                if optional:
                    return None
                raise

        # Automation Engine test hook
        if step_type == "ae_test_hook":
            import httpx
            automation_engine_url = cfg.get("url")
            if not automation_engine_url:
                host = os.getenv("AUTOMATION_ENGINE_HOST")
                if not host:
                    host = "automation-engine" if os.getenv("E2E_CONTAINER") == "1" else "localhost"
                port = os.getenv("AUTOMATION_ENGINE_API_PORT", "9505")
                automation_engine_url = f"http://{host}:{port}"
            zone_id = cfg.get("zone_id") or self.context.get("zone_id")
            controller = cfg.get("controller")
            action = cfg.get("action")  # inject_error, clear_error, reset_backoff, set_state
            error_type = cfg.get("error_type")
            state = cfg.get("state")
            
            if not zone_id:
                raise ValueError("ae_test_hook requires zone_id")
            if not action:
                raise ValueError("ae_test_hook requires action")
            
            payload = {
                "zone_id": zone_id,
                "action": action,
            }
            if controller:
                payload["controller"] = controller
            if error_type:
                payload["error_type"] = error_type
            if state:
                payload["state"] = state
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{automation_engine_url}/test/hook", json=payload)
                if resp.status_code != 200:
                    raise RuntimeError(f"Test hook failed: {resp.status_code} - {resp.text}")
                
                result = resp.json()
                if "save" in cfg:
                    self.context[cfg["save"]] = result
                return result

        # Node-sim fault modes
        if step_type == "node_sim_fault_mode":
            # Устанавливает fault mode для node-sim через API или конфиг
            mode = cfg.get("mode")  # drop, delay, duplicate
            enabled = cfg.get("enabled", True)
            delay_ms = cfg.get("delay_ms", 0)
            
            # Для node-sim можно использовать HTTP API если он есть, или обновить конфиг
            # Пока используем упрощенный подход через переменные окружения или конфиг
            logger.info(f"Setting node-sim fault mode: {mode}, enabled={enabled}, delay_ms={delay_ms}")
            
            # Сохраняем в контекст для использования в других шагах
            self.context["_node_sim_fault_mode"] = {
                "mode": mode,
                "enabled": enabled,
                "delay_ms": delay_ms
            }
            
            return {"mode": mode, "enabled": enabled}

        raise ValueError(f"Unknown action type: {step_type}")

    async def _execute_assertion(self, a_type: Optional[str], assertion: Dict[str, Any]):
        if not a_type:
            raise ValueError("Assertion missing 'type'")

        if a_type == "sleep":
            # Простой assertion-таймаут, чтобы дать системе стабилизироваться
            seconds = float(assertion.get("seconds", assertion.get("timeout", 0)))
            if seconds > 0:
                await asyncio.sleep(seconds)
            return

        if a_type == "http_request":
            import httpx
            method = (assertion.get("method") or "GET").upper()
            url = self._resolve_variables(assertion.get("url"))
            timeout = float(assertion.get("timeout", 10.0))
            expected_status = int(assertion.get("expected_status", 200))
            save_key = assertion.get("save", "http_assertion_response")

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(method, url)
            if resp.status_code != expected_status:
                raise AssertionError(f"http_request assertion: expected {expected_status}, got {resp.status_code}")
            try:
                data = resp.json()
            except Exception:
                data = {"text": resp.text}
            # Сохраняем в контекст по ключу save (как в шагах)
            self.context[save_key] = {"status_code": resp.status_code, "data": data}
            return

        if a_type in ("assert", "custom_assert"):
            # Простейшая поддержка кастомных boolean-условий из YAML
            condition_expr = assertion.get("condition")
            if not condition_expr:
                return
            # Подставляем значения из контекста через _resolve_variables (Jinja-подобные плейсхолдеры уже раскрыты)
            resolved = self._resolve_variables(condition_expr)
            # Ограниченный eval: ожидаем, что resolved уже строка вида "1 >= 0" или булево
            if isinstance(resolved, bool):
                ok = resolved
            else:
                try:
                    # Безопасный eval с ограниченным набором функций и контекстом
                    safe_builtins = {
                        'len': len,
                        'str': str,
                        'int': int,
                        'float': float,
                        'bool': bool,
                        'all': all,
                        'any': any,
                        'sum': sum,
                        'max': max,
                        'min': min,
                        'abs': abs,
                        'True': True,
                        'False': False,
                        'None': None,
                    }
                    eval_globals = {'context': self.context}
                    ok = bool(eval(str(resolved), {"__builtins__": safe_builtins}, eval_globals))
                except Exception as e:
                    raise AssertionError(f"Failed to evaluate assert condition '{resolved}': {e}")
            if not ok:
                raise AssertionError(f"Assertion condition is false: {resolved}")
            return

        if a_type == "database_query":
            query = self._resolve_variables(assertion.get("query"))
            params = self._resolve_variables(assertion.get("params", {}))
            logger.info(f"Database assertion '{assertion.get('name', 'unknown')}' params: {params}")
            self._validate_critical_params(params)
            rows = await self.db.wait(query, params=params, timeout=float(assertion.get("timeout", 10.0)), expected_rows=assertion.get("expected_rows"))
            logger.info(f"Database assertion '{assertion.get('name', 'unknown')}' found {len(rows)} rows")
            expected = assertion.get("expected", [])
            if not rows:
                raise AssertionError(f"No rows returned for database_query assertion '{assertion.get('name', 'unknown')}'")
            row0 = rows[0]
            logger.info(f"Database assertion '{assertion.get('name', 'unknown')}' row0: {row0}")
            self._assert_row_expected(row0, expected)
            return

        if a_type in ("db.wait", "db_wait"):
            query = self._resolve_variables(assertion.get("query"))
            params = self._resolve_variables(assertion.get("params", {}))
            timeout = float(assertion.get("timeout", 10.0))
            expected_rows = assertion.get("expected_rows")
            self._validate_critical_params(params)
            rows = await self.db.wait(query, params=params, timeout=timeout, expected_rows=expected_rows)
            return rows

        if a_type == "websocket_event":
            event_type = assertion.get("event_type") or assertion.get("event")
            timeout = float(assertion.get("timeout_seconds", assertion.get("timeout", 10.0)))
            filter_dict = assertion.get("filter")
            if filter_dict:
                filter_dict = self._resolve_variables(filter_dict)
            lookback = assertion.get("lookback_messages")
            if lookback is None and filter_dict:
                lookback = 100
            if lookback is not None:
                lookback = int(lookback)
            ev = await self.ws.wait_event(event_type, timeout=timeout, filter=filter_dict, lookback=lookback)
            if ev is None:
                raise TimeoutError(f"Timeout waiting for WebSocket event: {event_type}")
            return

        if a_type == "websocket_event_count":
            event_type = assertion.get("event_type") or assertion.get("event")
            channel = assertion.get("channel")
            timeout = float(assertion.get("timeout_seconds", assertion.get("timeout", 10.0)))
            filter_dict = assertion.get("filter", {})
            expected = assertion.get("expected", [])
            
            # Подписываемся на канал, если еще не подписаны
            if channel and channel not in self.ws._subscribed_channels:
                await self.ws.subscribe(channel)
            
            # Собираем все события за период
            events = []
            start_time = time.time()
            while time.time() - start_time < timeout:
                messages = self.ws.get_messages(100)
                for msg in messages:
                    data = msg.get("data", {})
                    msg_event = data.get("event", data.get("type"))
                    if msg_event == event_type:
                        # Проверяем фильтр
                        match = True
                        for key, value in filter_dict.items():
                            # Простой путь через точку (например, command.cmd_id)
                            parts = key.split(".")
                            target = data
                            for part in parts:
                                if isinstance(target, dict):
                                    target = target.get(part)
                                else:
                                    match = False
                                    break
                            if target != value:
                                match = False
                                break
                        if match:
                            events.append(data)
                await asyncio.sleep(0.1)
            
            # Проверяем ожидаемое количество
            for rule in expected:
                field = rule.get("field")
                operator = rule.get("operator")
                value = rule.get("value")
                if field == "count":
                    actual = len(events)
                    if operator == "equals" and actual != value:
                        raise AssertionError(f"Expected {value} events, got {actual}")
                    elif operator == "greater_than" and not (actual > value):
                        raise AssertionError(f"Expected > {value} events, got {actual}")
            return

        if a_type == "compare_json":
            # minimal: compare two captured responses
            source1 = assertion.get("source1")
            source2 = assertion.get("source2")
            path1 = assertion.get("path1")
            path2 = assertion.get("path2")
            op = assertion.get("operator")
            v1 = self._extract_json_path(self.context.get(source1), path1)
            v2 = self._extract_json_path(self.context.get(source2), path2)
            if op == "less_than" and not (v1 < v2):
                raise AssertionError(f"Expected {v1} < {v2}, but {v1} >= {v2}")
            elif op == "greater_than" and not (v1 > v2):
                raise AssertionError(f"Expected {v1} > {v2}, but {v1} <= {v2}")
            return

        if a_type == "json_assertion":
            # Поддерживаем как source/path, так и прямые data:
            target = assertion.get("data")
            if target is None:
                source = assertion.get("source")
                path = assertion.get("path")
                target = self._extract_json_path(self.context.get(source), path)
            else:
                target = self._resolve_variables(target)
            expected = assertion.get("expected", [])
            # basic length checks and field checks
            for rule in expected:
                field = rule.get("field")
                operator = rule.get("operator")
                value = self._resolve_variables(rule.get("value"))
                rule_optional = bool(rule.get("optional", False))

                # Выбираем значение поля
                field_value = None
                if field == "length":
                    field_value = len(target) if target is not None else 0
                elif field:
                    field_value = self._extract_json_path(target, field) if isinstance(target, (dict, list)) else None

                try:
                    if field == "length":
                        actual = field_value
                        if operator == "greater_than" and not (actual > value):
                            raise AssertionError(f"Expected length > {value}, got {actual}")
                        if operator == "equals" and not (actual == value):
                            raise AssertionError(f"Expected length = {value}, got {actual}")
                    elif field and operator:
                        if operator == "is_not_null":
                            if field_value is None:
                                raise AssertionError(f"Expected field {field} to be not null")
                        elif operator == "equals":
                            if str(field_value) != str(value):
                                raise AssertionError(f"Expected {field} = {value}, got {field_value}")
                        elif operator == "greater_than":
                            if not (float(field_value) > float(value)):
                                raise AssertionError(f"Expected {field} > {value}, got {field_value}")
                        elif operator == "greater_than_or_equal":
                            if not (float(field_value) >= float(value)):
                                raise AssertionError(f"Expected {field} >= {value}, got {field_value}")
                        elif operator == "less_than":
                            if not (float(field_value) < float(value)):
                                raise AssertionError(f"Expected {field} < {value}, got {field_value}")
                        elif operator == "in":
                            if field_value not in value:
                                raise AssertionError(f"Expected {field} in {value}, got {field_value}")
                        elif operator == "is_type":
                            type_map = {
                                "list": list,
                                "dict": dict,
                                "str": str,
                                "int": int,
                                "float": float,
                                "bool": bool,
                            }
                            expected_type = type_map.get(str(value).lower(), None)
                            if expected_type and not isinstance(field_value if field else target, expected_type):
                                raise AssertionError(f"Expected {field or 'value'} to be of type {value}")
                        else:
                            raise AssertionError(f"Unsupported operator in json_assertion: {operator}")
                    else:
                        # нет правила — ничего не делаем
                        continue
                except AssertionError:
                    if rule_optional:
                        continue
                    raise
            return

        if a_type == "table_absent":
            table_name = assertion.get("table_name")
            if not table_name:
                raise ValueError("table_absent assertion requires 'table_name'")
            self.assertions.table_absent(self.db, table_name)
            return

        if a_type == "column_absent":
            table_name = assertion.get("table_name")
            column_name = assertion.get("column_name")
            if not table_name or not column_name:
                raise ValueError("column_absent assertion requires 'table_name' and 'column_name'")
            self.assertions.column_absent(self.db, table_name, column_name)
            return

        raise ValueError(f"Unknown assertion type: {a_type}")

    def _assert_row_expected(self, row: Dict[str, Any], expected_rules: List[Dict[str, Any]]):
        """
        Assert row expected using SchemaValidator.
        """
        if not self.schema_validator:
            return
        resolved_rules = []
        for rule in expected_rules or []:
            if not isinstance(rule, dict):
                resolved_rules.append(rule)
                continue
            resolved_rule = dict(rule)
            if "value" in resolved_rule:
                resolved_rule["value"] = self._resolve_variables(resolved_rule["value"])
            if "or" in resolved_rule and isinstance(resolved_rule["or"], list):
                resolved_or = []
                for alt in resolved_rule["or"]:
                    if isinstance(alt, dict):
                        alt_rule = dict(alt)
                        if "value" in alt_rule:
                            alt_rule["value"] = self._resolve_variables(alt_rule["value"])
                        resolved_or.append(alt_rule)
                    else:
                        resolved_or.append(alt)
                resolved_rule["or"] = resolved_or
            resolved_rules.append(resolved_rule)
        self.schema_validator.assert_row_expected(row, resolved_rules)

    def _extract_json_path(self, obj: Any, path: Optional[str]) -> Any:
        """
        Extract JSON path using SchemaValidator.
        """
        if not self.schema_validator:
            return None
        return self.schema_validator.extract_json_path(obj, path)

    async def cleanup(self):
        """Очистка ресурсов после выполнения сценария."""
        logger.info("Cleaning up E2E runner...")

        # Закрываем соединения
        if self.ws:
            try:
                await self.ws.disconnect()
            except Exception as e:
                logger.warning(f"Failed to disconnect WebSocket: {e}")

        if self.db:
            try:
                self.db.disconnect()
            except Exception as e:
                logger.warning(f"Failed to disconnect database: {e}")

        if self.mqtt:
            try:
                await self.mqtt.disconnect()
            except Exception as e:
                logger.warning(f"Failed to disconnect MQTT: {e}")

        # Останавливаем инфраструктуру если мы её запускали
        if hasattr(self, '_infra_started_by_runner') and self._infra_started_by_runner:
            try:
                await self._stop_infrastructure()
            except Exception as e:
                logger.warning(f"Failed to stop infrastructure: {e}")

        logger.info("E2E runner cleanup completed")

    async def _stop_infrastructure(self):
        """Остановить инфраструктуру."""
        logger.info("Stopping E2E infrastructure...")

        # Останавливаем сервисы в обратном порядке
        services_to_stop = ["node-sim", "automation-engine", "history-logger", "laravel", "mosquitto", "redis", "postgres"]

        for service in services_to_stop:
            try:
                result = await asyncio.create_subprocess_exec(
                    "docker-compose", "-f", self.compose_file, "stop", service,
                    cwd=os.path.dirname(self.compose_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.wait()
                if result.returncode == 0:
                    logger.info(f"Stopped service: {service}")
                else:
                    logger.warning(f"Failed to stop service: {service}")
            except Exception as e:
                logger.warning(f"Error stopping service {service}: {e}")

        # Останавливаем всю инфраструктуру
        try:
            result = await asyncio.create_subprocess_exec(
                "docker-compose", "-f", self.compose_file, "down",
                cwd=os.path.dirname(self.compose_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.wait()
            logger.info("E2E infrastructure stopped")
        except Exception as e:
            logger.warning(f"Failed to stop E2E infrastructure: {e}")


async def main():
    """Главная функция."""
    if len(sys.argv) < 2:
        print("Usage: python e2e_runner.py <scenario.yaml>")
        sys.exit(1)
    
    scenario_path = sys.argv[1]
    
    runner = E2ERunner()
    success = await runner.run_scenario(scenario_path)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
