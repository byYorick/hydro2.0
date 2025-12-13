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
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from urllib.parse import urlparse, urljoin

from .api_client import APIClient, AuthenticationError
from .auth_client import AuthClient
from .ws_client import WSClient
from .db_probe import DBProbe
from .mqtt_probe import MQTTProbe
from .assertions import Assertions, AssertionError
from .reporting import TestReporter

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
        auth_role = config.get("auth_role", "admin")
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
    
    async def setup(self):
        """Инициализация клиентов."""
        logger.info("Setting up E2E runner...")
        
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
        service_map = {
            "laravel": "laravel",
            "mosquitto": "mosquitto",
            "postgres": "postgres",
            "history-logger": "history-logger",
            "automation-engine": "automation-engine",
            "redis": "redis",
            "reverb": "reverb",
            "node-sim": "node-sim",
        }
        compose_service = service_map.get(service, service)
        
        try:
            if action == "stop":
                logger.info(f"[FAULT_INJECT] Stopping service: {compose_service}")
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
            "reverb": "reverb",
            "node-sim": "node-sim",
        }
        compose_service = service_map.get(service, service)
        
        try:
            logger.info(f"[FAULT_INJECT] Restoring service: {compose_service}")
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
            "laravel",
            "reverb",
            "history-logger",
            "mqtt-bridge",
            "automation-engine",
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
    
    def _resolve_variables(self, value: Any) -> Any:
        """
        Разрешить переменные в значении (поддержка ${var} и {{var}}).
        
        Поддерживает:
        - ${var} - простая переменная
        - ${var.field} - доступ к полю
        - ${var[0]} - доступ по индексу
        - ${var.field[0].subfield} - вложенные доступы
        
        Args:
            value: Значение для разрешения
            
        Returns:
            Разрешенное значение
        """
        if isinstance(value, str):
            # Поддержка ${var.field[0]} и {{var.field[0]}}
            import re
            pattern = r'\$\{([^}]+)\}|\{\{([^}]+)\}\}'
            
            def replace(match):
                var_expr = match.group(1) or match.group(2)
                # Поддержка ${ENV_VAR:-default}
                if ":-" in var_expr:
                    env_name, default = var_expr.split(":-", 1)
                    env_name = env_name.strip()
                    if env_name in os.environ and os.environ[env_name] != "":
                        return str(os.environ[env_name])
                    return str(default)

                # Если есть в context - используем context
                resolved = self._resolve_variable_expression(var_expr)
                if resolved is not None:
                    return str(resolved)

                # Иначе пробуем env (простое ${ENV_VAR})
                if var_expr in os.environ:
                    return str(os.environ[var_expr])

                return ""
            
            out = re.sub(pattern, replace, value)

            # Поддержка {var} (format-style) для сценариев actions/assertions
            def repl_brace(m: re.Match) -> str:
                name = m.group(1)
                if name in self.context and self.context[name] is not None:
                    return str(self.context[name])
                if name in os.environ and os.environ[name] != "":
                    return str(os.environ[name])
                return m.group(0)
            out = re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", repl_brace, out)
            return out
        elif isinstance(value, dict):
            return {k: self._resolve_variables(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._resolve_variables(item) for item in value]
        else:
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
        self.reporter.add_timeline_event(step_type or "unknown", f"Executing {step_name}", step_config)
        
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
                from runner.ws_client import WSClient
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
        method = step_type.split(".")[1]  # get, post, put, delete
        path = config.pop("path", None)
        if not path:
            raise ValueError("API step requires 'path' parameter")
        
        # Разрешаем переменные в path
        path = self._resolve_variables(path)
        
        if method == "get":
            return await self.api.get(path, params=config.get("params"))
        elif method == "post":
            return await self.api.post(path, json=config.get("json", config.get("data")))
        elif method == "put":
            return await self.api.put(path, json=config.get("json", config.get("data")))
        elif method == "delete":
            return await self.api.delete(path)
        else:
            raise ValueError(f"Unknown API method: {method}")
    
    async def _execute_ws_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """Выполнить WebSocket шаг."""
        action = step_type.split(".")[1]  # subscribe, wait_event
        
        if action == "subscribe":
            channel = config["channel"]
            await self.ws.subscribe(channel)
            return {"subscribed": channel}
        elif action == "wait_event":
            event_type = config["event"]
            timeout = config.get("timeout", 10.0)
            filter_dict = config.get("filter", {})
            optional = config.get("optional", False)
            logger.info(f"ws.wait_event: Waiting for event '{event_type}' with filter {filter_dict}, timeout={timeout}s, optional={optional}")
            result = await self.ws.wait_event(event_type, timeout=timeout, filter=filter_dict)
            if result is None and not optional:
                logger.error(f"ws.wait_event: Timeout waiting for event '{event_type}' after {timeout}s")
                raise TimeoutError(f"Timeout waiting for WebSocket event: {event_type}")
            if result:
                logger.info(f"ws.wait_event: Received event '{event_type}': {result.get('event')} on channel {result.get('channel')}")
            return result
        else:
            raise ValueError(f"Unknown WS action: {action}")
    
    async def _execute_db_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """Выполнить DB шаг."""
        action = step_type.split(".")[1]  # wait, query
        
        if action == "wait":
            query = config["query"]
            params = config.get("params", {})
            timeout = config.get("timeout", 10.0)
            expected_rows = config.get("expected_rows")
            
            # Разрешаем переменные в params
            resolved_params = {}
            for k, v in params.items():
                resolved_value = self._resolve_variables(v)
                resolved_params[k] = resolved_value
                logger.debug(f"db.wait: Resolved param '{k}': {v} -> {resolved_value}")
            
            logger.info(f"db.wait: Executing wait with query: {query}, params: {resolved_params}, expected_rows: {expected_rows}, timeout: {timeout}s")
            
            return await self.db.wait(
                query,
                params=resolved_params,
                timeout=timeout,
                expected_rows=expected_rows
            )
        elif action == "query":
            query = config["query"]
            params = config.get("params", {})
            return self.db.query(query, params=params)
        else:
            raise ValueError(f"Unknown DB action: {action}")
    
    async def _execute_mqtt_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """Выполнить MQTT шаг."""
        action = step_type.split(".")[1]  # subscribe, wait_message
        
        if action == "subscribe":
            topic = config["topic"]
            qos = config.get("qos", 1)
            self.mqtt.subscribe(topic, qos=qos)
            return {"subscribed": topic}
        elif action == "wait_message":
            topic = config.get("topic")
            timeout = config.get("timeout", 10.0)
            result = await self.mqtt.wait_message(topic=topic, timeout=timeout)
            if result is None:
                raise TimeoutError(f"Timeout waiting for MQTT message on topic: {topic}")
            return result
        else:
            raise ValueError(f"Unknown MQTT action: {action}")
    
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
        if zone_id:
            result = await self.api.get(f"/api/zones/{zone_id}/snapshot")
            # Сохраняем в контекст
            self.context["snapshot"] = result
            # Извлекаем last_event_id для удобства
            if isinstance(result, dict):
                data = result.get("data", result)
                if isinstance(data, dict) and "last_event_id" in data:
                    self.context["last_event_id"] = data["last_event_id"]
            return result
        else:
            raise ValueError("snapshot.fetch requires zone_id")
    
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

        # actions
        actions = scenario.get("actions", [])
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
                else:
                    res = await self.api.post(endpoint, json=payload)
            elif step_type == "api_put":
                res = await self.api.put(endpoint, json=payload)
            elif step_type == "api_patch":
                # APIClient doesn't have patch currently; use httpx under the hood
                res = await self.api.request("PATCH", endpoint, json=payload)
            else:
                res = await self.api.delete(endpoint)
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
            await self.ws.subscribe(channel)
            return
        if step_type == "websocket_unsubscribe":
            # Просто игнорируем, т.к. в текущей реализации нет явной отписки
            logger.info("websocket_unsubscribe (noop)")
            return
        if step_type == "create_ws_client_without_token":
            # Создает WSClient без токена для тестирования ошибок авторизации
            from runner.ws_client import WSClient
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
            result = self.db.query(query, params=params)
            if "save" in cfg:
                self.context[cfg["save"]] = result
            return result

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

        raise ValueError(f"Unknown action type: {step_type}")

    async def _execute_assertion(self, a_type: Optional[str], assertion: Dict[str, Any]):
        if not a_type:
            raise ValueError("Assertion missing 'type'")

        if a_type == "database_query":
            query = self._resolve_variables(assertion.get("query"))
            params = self._resolve_variables(assertion.get("params", {}))
            rows = await self.db.wait(query, params=params, timeout=float(assertion.get("timeout", 10.0)), expected_rows=assertion.get("expected_rows"))
            expected = assertion.get("expected", [])
            if not rows:
                raise AssertionError("No rows returned for database_query assertion")
            row0 = rows[0]
            self._assert_row_expected(row0, expected)
            return

        if a_type in ("db.wait", "db_wait"):
            query = self._resolve_variables(assertion.get("query"))
            params = self._resolve_variables(assertion.get("params", {}))
            timeout = float(assertion.get("timeout", 10.0))
            expected_rows = assertion.get("expected_rows")
            rows = await self.db.wait(query, params=params, timeout=timeout, expected_rows=expected_rows)
            return rows

        if a_type == "websocket_event":
            event_type = assertion.get("event_type") or assertion.get("event")
            timeout = float(assertion.get("timeout_seconds", assertion.get("timeout", 10.0)))
            ev = await self.ws.wait_event(event_type, timeout=timeout)
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

        raise ValueError(f"Unknown assertion type: {a_type}")

    def _assert_row_expected(self, row: Dict[str, Any], expected_rules: List[Dict[str, Any]]):
        for rule in expected_rules:
            field = rule.get("field")
            op = rule.get("operator")
            expected_value = self._resolve_variables(rule.get("value"))
            actual_value = row.get(field) if isinstance(row, dict) else None

            if op == "equals":
                if str(actual_value) != str(expected_value):
                    raise AssertionError(f"Field {field}: expected {expected_value}, got {actual_value}")
            elif op == "is_not_null":
                if actual_value is None:
                    raise AssertionError(f"Field {field}: expected not null")
            elif op == "in":
                if actual_value not in expected_value:
                    raise AssertionError(f"Field {field}: expected in {expected_value}, got {actual_value}")
            elif op == "greater_than":
                if not (float(actual_value) > float(expected_value)):
                    raise AssertionError(f"Field {field}: expected > {expected_value}, got {actual_value}")
            elif op == "less_than_or_equal":
                if not (float(actual_value) <= float(expected_value)):
                    raise AssertionError(f"Field {field}: expected <= {expected_value}, got {actual_value}")
            elif op == "greater_than_or_equal":
                if not (float(actual_value) >= float(expected_value)):
                    raise AssertionError(f"Field {field}: expected >= {expected_value}, got {actual_value}")
            else:
                raise AssertionError(f"Unsupported operator in db assertion: {op}")

    def _extract_json_path(self, obj: Any, path: Optional[str]) -> Any:
        if obj is None or not path:
            return None
        # obj может быть dict с ключами json/text
        if isinstance(obj, dict) and "json" in obj and isinstance(obj["json"], dict):
            obj = obj["json"]
        parts = path.split(".")
        cur = obj
        for p in parts:
            if cur is None:
                return None
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return None
        return cur


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
