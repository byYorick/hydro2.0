"""
Command Bus - централизованная публикация команд через history-logger REST API.
Интегрирован с валидацией команд и отслеживанием выполнения.
Все общение с нодами происходит через history-logger.
"""
from typing import Optional, Dict, Any
import logging
import httpx
import os
from common.mqtt import MqttClient
from common.db import create_zone_event
from common.simulation_events import record_simulation_event
from prometheus_client import Counter, Histogram
from .command_validator import CommandValidator
from .command_tracker import CommandTracker
from .command_audit import CommandAudit
from utils.logging_context import get_trace_id
from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from decision_context import ContextLike, normalize_context

logger = logging.getLogger(__name__)

# Метрики для отслеживания ошибок публикации
REST_PUBLISH_ERRORS = Counter("rest_command_errors_total", "REST command publish errors", ["error_type"])
COMMANDS_SENT = Counter("automation_commands_sent_total", "Commands sent by automation", ["zone_id", "metric"])
COMMAND_VALIDATION_FAILED = Counter("command_validation_failed_total", "Failed command validations", ["zone_id", "reason"])
COMMAND_REST_LATENCY = Histogram("command_rest_latency_seconds", "REST command publish latency", buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0])


class CommandBus:
    """Централизованная публикация команд через history-logger REST API с валидацией и отслеживанием."""
    
    def __init__(
        self,
        mqtt: Optional[MqttClient] = None,  # Оставлено для обратной совместимости, но не используется
        gh_uid: str = "",
        history_logger_url: Optional[str] = None,
        history_logger_token: Optional[str] = None,
        command_source: Optional[str] = None,
        command_validator: Optional[CommandValidator] = None,
        command_tracker: Optional[CommandTracker] = None,
        command_audit: Optional[CommandAudit] = None,
        http_timeout: float = 5.0,
        api_circuit_breaker: Optional[CircuitBreaker] = None
    ):
        """
        Инициализация Command Bus.
        
        Args:
            mqtt: MQTT клиент (deprecated, не используется)
            gh_uid: UID теплицы
            history_logger_url: URL history-logger сервиса (по умолчанию из env)
            history_logger_token: Токен для аутентификации (по умолчанию из env)
            command_validator: Валидатор команд (опционально)
            command_tracker: Трекер команд (опционально)
            command_audit: Аудит команд (опционально)
            http_timeout: Таймаут для HTTP запросов в секундах
            api_circuit_breaker: Circuit breaker для API (опционально)
        """
        self.mqtt = mqtt  # Deprecated
        self.gh_uid = gh_uid
        self.history_logger_url = history_logger_url or os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
        self.history_logger_token = history_logger_token or os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
        self.command_source = command_source or os.getenv("COMMAND_SOURCE", "automation")
        self.validator = command_validator or CommandValidator()
        self.tracker = command_tracker
        self.audit = command_audit or CommandAudit()
        self.http_timeout = http_timeout
        self.api_circuit_breaker = api_circuit_breaker
        
        # Долгоживущий HTTP клиент для переиспользования соединений
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def start(self):
        """Инициализировать долгоживущий HTTP клиент."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.http_timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
            logger.debug("CommandBus HTTP client initialized")
    
    async def stop(self):
        """Закрыть HTTP клиент и освободить ресурсы."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
            logger.debug("CommandBus HTTP client closed")
    
    def _get_client(self):
        """
        Получить HTTP клиент.
        
        Returns:
            httpx.AsyncClient если долгоживущий клиент инициализирован
            None если нужно использовать временный клиент в контекстном менеджере
        """
        if self._http_client is None:
            logger.warning("CommandBus HTTP client not initialized, using temporary client")
            return None
        return self._http_client
    
    async def publish_command(
        self,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Optional[Dict[str, Any]] = None,
        cmd_id: Optional[str] = None
    ) -> bool:
        """
        Публикация команды через history-logger REST API.
        
        Args:
            zone_id: ID зоны
            node_uid: UID узла
            channel: Канал узла
            cmd: Команда
            params: Параметры команды
            cmd_id: Идентификатор команды (если уже сгенерирован)
        
        Returns:
            True если команда успешно отправлена, False в противном случае
        """
        import time
        start_time = time.time()
        
        try:
            # Получаем trace_id из контекста логирования
            trace_id = get_trace_id()
            
            # Формируем запрос к history-logger
            payload = {
                "cmd": cmd,
                "greenhouse_uid": self.gh_uid,
                "zone_id": zone_id,
                "node_uid": node_uid,
                "channel": channel,
                "source": self.command_source,
                "params": params or {},
            }
            if cmd_id:
                payload["cmd_id"] = cmd_id
            if trace_id:
                payload["trace_id"] = trace_id
            
            # Заголовки для аутентификации
            headers = {"Content-Type": "application/json"}
            if self.history_logger_token:
                headers["Authorization"] = f"Bearer {self.history_logger_token}"
            
            # Обертка для HTTP запроса через circuit breaker
            async def _send_request():
                client = self._get_client()
                if client is None:
                    # Используем временный клиент в контекстном менеджере
                    async with httpx.AsyncClient(timeout=self.http_timeout) as temp_client:
                        return await temp_client.post(
                            f"{self.history_logger_url}/commands",
                            json=payload,
                            headers=headers
                        )
                else:
                    # Используем долгоживущий клиент
                    return await client.post(
                        f"{self.history_logger_url}/commands",
                        json=payload,
                        headers=headers
                    )
            
            # Отправляем запрос через circuit breaker если он настроен
            if self.api_circuit_breaker:
                response = await self.api_circuit_breaker.call(_send_request)
            else:
                response = await _send_request()
            
            latency = time.time() - start_time
            COMMAND_REST_LATENCY.observe(latency)
                
            if response.status_code == 200:
                try:
                    result = response.json()
                    cmd_id = result.get("data", {}).get("command_id")
                    logger.debug(
                        f"Zone {zone_id}: Command {cmd} sent successfully via REST, cmd_id: {cmd_id}",
                        extra={"zone_id": zone_id, "cmd_id": cmd_id, "trace_id": trace_id}
                    )
                    COMMANDS_SENT.labels(zone_id=str(zone_id), metric=cmd).inc()
                    await record_simulation_event(
                        zone_id,
                        service="automation-engine",
                        stage="command_publish",
                        status="sent",
                        message="Команда отправлена через history-logger",
                        payload={
                            "cmd": cmd,
                            "cmd_id": cmd_id,
                            "channel": channel,
                            "node_uid": node_uid,
                            "source": self.command_source,
                        },
                    )
                    return True
                except Exception as e:
                    error_type = "json_decode_error"
                    REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
                    logger.error(
                        f"Zone {zone_id}: Failed to parse response JSON: {e}",
                        extra={"zone_id": zone_id, "trace_id": trace_id}
                    )
                    await record_simulation_event(
                        zone_id,
                        service="automation-engine",
                        stage="command_publish",
                        status="failed",
                        level="error",
                        message="Ошибка разбора ответа history-logger",
                        payload={
                            "cmd": cmd,
                            "channel": channel,
                            "node_uid": node_uid,
                            "error": str(e),
                        },
                    )
                    return False
            else:
                try:
                    error_msg = response.text
                except Exception:
                    error_msg = f"HTTP {response.status_code}"
                error_type = f"http_{response.status_code}"
                REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
                logger.error(
                    f"Zone {zone_id}: Failed to publish command {cmd} via REST: {response.status_code} - {error_msg}",
                    extra={"zone_id": zone_id, "trace_id": trace_id}
                )
                await record_simulation_event(
                    zone_id,
                    service="automation-engine",
                    stage="command_publish",
                    status="failed",
                    level="error",
                    message="Ошибка отправки команды через history-logger",
                    payload={
                        "cmd": cmd,
                        "channel": channel,
                        "node_uid": node_uid,
                        "http_status": response.status_code,
                        "error": error_msg,
                    },
                )
                return False
                    
        except httpx.TimeoutException as e:
            error_type = "timeout"
            REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
            logger.error(f"Zone {zone_id}: Timeout publishing command {cmd} via REST: {e}", exc_info=True)
            await record_simulation_event(
                zone_id,
                service="automation-engine",
                stage="command_publish",
                status="failed",
                level="error",
                message="Таймаут отправки команды через history-logger",
                payload={
                    "cmd": cmd,
                    "channel": channel,
                    "node_uid": node_uid,
                    "error": str(e),
                },
            )
            return False
        except httpx.RequestError as e:
            error_type = "request_error"
            REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
            logger.error(f"Zone {zone_id}: Request error publishing command {cmd} via REST: {e}", exc_info=True)
            await record_simulation_event(
                zone_id,
                service="automation-engine",
                stage="command_publish",
                status="failed",
                level="error",
                message="Ошибка запроса при отправке команды через history-logger",
                payload={
                    "cmd": cmd,
                    "channel": channel,
                    "node_uid": node_uid,
                    "error": str(e),
                },
            )
            return False
        except Exception as e:
            error_type = type(e).__name__
            REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
            logger.error(f"Zone {zone_id}: Failed to publish command {cmd} via REST: {e}", exc_info=True)
            await record_simulation_event(
                zone_id,
                service="automation-engine",
                stage="command_publish",
                status="failed",
                level="error",
                message="Не удалось отправить команду через history-logger",
                payload={
                    "cmd": cmd,
                    "channel": channel,
                    "node_uid": node_uid,
                    "error": str(e),
                },
            )
            return False
    
    async def publish_controller_command(
        self,
        zone_id: int,
        command: Dict[str, Any],
        context: ContextLike = None
    ) -> bool:
        """
        Публикация команды от контроллера с валидацией и отслеживанием.
        
        Args:
            zone_id: ID зоны
            command: Команда от контроллера с полями:
                - node_uid: UID узла
                - channel: Канал узла
                - cmd: Команда
                - params: Параметры команды (опционально)
            context: Дополнительный контекст для трекинга
        
        Returns:
            True если команда успешно отправлена, False в противном случае
        """
        node_uid = command.get('node_uid')
        channel = command.get('channel', 'default')
        cmd = command.get('cmd')
        params = command.get('params')
        cmd_id = command.get('cmd_id')
        normalized_context = normalize_context(context)
        
        if not node_uid or not cmd:
            logger.warning(f"Zone {zone_id}: Invalid command structure - missing node_uid or cmd")
            return False
        
        # Валидация команды
        is_valid, error = self.validator.validate_command(command)
        if not is_valid:
            COMMAND_VALIDATION_FAILED.labels(zone_id=str(zone_id), reason=error or 'unknown').inc()
            logger.error(
                f"Zone {zone_id}: Command validation failed: {error}",
                extra={
                    'zone_id': zone_id,
                    'command': command,
                    'validation_error': error
                }
            )
            await create_zone_event(zone_id, 'COMMAND_VALIDATION_FAILED', {
                'command': command,
                'error': error
            })
            await record_simulation_event(
                zone_id,
                service="automation-engine",
                stage="command_validate",
                status="validation_failed",
                level="warning",
                message="Команда не прошла валидацию",
                payload={
                    "command": command,
                    "error": error,
                },
            )
            return False
        
        # Отслеживание команды
        cmd_id = None
        if self.tracker:
            try:
                cmd_id = await self.tracker.track_command(zone_id, command, normalized_context)
                # Добавляем cmd_id в команду (top-level)
                command['cmd_id'] = cmd_id
                cmd_id = command['cmd_id']
            except Exception as e:
                logger.warning(f"Zone {zone_id}: Failed to track command: {e}", exc_info=True)
                # Если tracker не сработал, используем исходные params (могут быть None)
                params = command.get('params')
        else:
            # Если tracker не настроен, используем исходные params
            params = command.get('params')
        
        # Публикация команды (cmd_id передается top-level)
        success = await self.publish_command(zone_id, node_uid, channel, cmd, params, cmd_id=cmd_id)
        
        # Аудит команды (даже если не удалось отправить)
        try:
            await self.audit.audit_command(zone_id, command, normalized_context)
        except Exception as e:
            logger.warning(f"Zone {zone_id}: Failed to audit command: {e}", exc_info=True)
        
        if not success and cmd_id and self.tracker:
            # Если публикация не удалась, подтверждаем команду как failed
            await self.tracker.confirm_command(cmd_id, False, error='publish_failed')
        
        return success
