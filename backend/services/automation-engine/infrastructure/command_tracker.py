"""Command tracker для ожидания terminal-статусов команд через DB polling + LISTEN/NOTIFY."""
import asyncio
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timezone
from common.utils.time import utcnow
from common.db import fetch
from common.commands import new_command_id
from infrastructure.command_tracker_confirm import (
    check_timeout_impl,
    confirm_command_internal_impl,
    emit_failure_alert_impl,
    persist_terminal_status_impl,
    wait_for_command_done_impl,
)
from infrastructure.command_tracker_runtime import (
    close_notify_connection_impl,
    handle_notify_payload_impl,
    listen_command_statuses_impl,
    on_command_status_notify_impl,
    poll_command_statuses_impl,
    restore_pending_commands_impl,
    start_polling_impl,
    stop_polling_impl,
)
from prometheus_client import Histogram, Counter, Gauge
from decision_context import ContextLike, normalize_context

logger = logging.getLogger(__name__)

# Метрики
COMMAND_LATENCY = Histogram(
    "command_latency_seconds",
    "Time from command send to confirmation",
    ["zone_id", "command_type"]
)

COMMAND_SUCCESS = Counter(
    "command_success_total",
    "Successful commands",
    ["zone_id", "command_type"]
)

COMMAND_FAILURE = Counter(
    "command_failure_total",
    "Failed commands",
    ["zone_id", "command_type", "reason"]
)

COMMAND_TIMEOUT = Counter(
    "command_timeout_total",
    "Command timeouts",
    ["zone_id", "command_type"]
)

PENDING_COMMANDS = Gauge(
    "pending_commands_count",
    "Number of pending commands",
    ["zone_id"]
)

_NO_EFFECT_ALERT_SUPPRESSED_COMMANDS = {"activate_sensor_mode", "deactivate_sensor_mode"}


class CommandTracker:
    """
    Отслеживание выполнения команд.
    
    Отслеживает отправленные команды и их подтверждения от узлов.
    Статусы читаются из таблицы commands в БД (единый источник истины).
    """
    
    def __init__(self, command_timeout: int = 300, poll_interval: int = 5):
        """
        Инициализация трекера команд.
        
        Args:
            command_timeout: Таймаут команды в секундах (по умолчанию 5 минут)
            poll_interval: Интервал проверки статусов из БД в секундах (по умолчанию 5 секунд)
        """
        self.pending_commands: Dict[str, Dict[str, Any]] = {}
        self.command_timeout = command_timeout
        self.poll_interval = poll_interval
        self._timeout_tasks: Dict[str, asyncio.Task] = {}
        self._poll_task: Optional[asyncio.Task] = None
        self._notify_task: Optional[asyncio.Task] = None
        self._notify_conn: Optional[Any] = None
        self._notify_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=10000)
        self._shutdown_event = asyncio.Event()
        self._logger = logger
        self._utcnow = utcnow
        self._metrics = {
            "COMMAND_LATENCY": COMMAND_LATENCY,
            "COMMAND_SUCCESS": COMMAND_SUCCESS,
            "COMMAND_FAILURE": COMMAND_FAILURE,
            "COMMAND_TIMEOUT": COMMAND_TIMEOUT,
            "PENDING_COMMANDS": PENDING_COMMANDS,
        }
        # Tri-state semantics by zone:
        # - active=True: timeout alert was emitted in this runtime and should be resolved on success.
        # - probe_done=False/absent: cold-start probe not executed yet.
        self._timeout_alert_active_by_zone: Dict[int, bool] = {}
        self._timeout_alert_probe_done_by_zone: Dict[int, bool] = {}

    @staticmethod
    def _normalize_utc_datetime(value: Any) -> datetime:
        if not isinstance(value, datetime):
            return utcnow()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _resolve_command_name(command_info: Dict[str, Any]) -> str:
        command_payload = command_info.get("command") if isinstance(command_info, dict) else None
        if isinstance(command_payload, dict):
            cmd_value = command_payload.get("cmd")
            if isinstance(cmd_value, str):
                normalized = cmd_value.strip().lower()
                if normalized:
                    return normalized
        command_type = command_info.get("command_type") if isinstance(command_info, dict) else None
        if isinstance(command_type, str):
            normalized = command_type.strip().lower()
            if normalized:
                return normalized
        return ""

    @classmethod
    def _should_suppress_no_effect_alert(cls, status: str, command_info: Dict[str, Any]) -> bool:
        if str(status or "").strip().upper() != "NO_EFFECT":
            return False
        command_name = cls._resolve_command_name(command_info)
        return command_name in _NO_EFFECT_ALERT_SUPPRESSED_COMMANDS
    
    async def track_command(
        self,
        zone_id: int,
        command: Dict[str, Any],
        context: ContextLike = None,
        cmd_id: Optional[str] = None,
    ) -> str:
        """
        Начать отслеживание команды.
        
        Args:
            zone_id: ID зоны
            command: Команда для отслеживания
            context: Дополнительный контекст
        
        Returns:
            cmd_id: Уникальный ID команды (UUID формат, совместимый с history-logger)
        """
        resolved_cmd_id = str(cmd_id or "").strip() if cmd_id is not None else ""
        if not resolved_cmd_id:
            resolved_cmd_id = new_command_id()
        
        command_info = {
            'cmd_id': resolved_cmd_id,
            'zone_id': zone_id,
            'command': command,
            'command_type': command.get('cmd', 'unknown'),
            'sent_at': utcnow(),
            'status': 'QUEUED',
            'context': normalize_context(context)
        }
        
        self.pending_commands[resolved_cmd_id] = command_info
        
        # Обновляем метрики
        PENDING_COMMANDS.labels(zone_id=str(zone_id)).inc()
        
        # Команда будет сохранена в таблицу commands через history-logger/Laravel
        # Мы только отслеживаем её локально и проверяем статус из БД
        
        # Устанавливаем таймаут
        timeout_task = asyncio.create_task(self._check_timeout(resolved_cmd_id))
        self._timeout_tasks[resolved_cmd_id] = timeout_task
        
        logger.debug(
            f"Zone {zone_id}: Command {cmd_id} tracked",
            extra={
                'zone_id': zone_id,
                'cmd_id': resolved_cmd_id,
                'command_type': command.get('cmd')
            }
        )
        
        return resolved_cmd_id
    
    async def _confirm_command_internal(
        self,
        cmd_id: str,
        status: str,  # 'DONE', 'ERROR', 'INVALID', 'BUSY', 'NO_EFFECT', 'TIMEOUT', 'SEND_FAILED'
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        await confirm_command_internal_impl(self, cmd_id=cmd_id, status=status, response=response, error=error)

    async def _emit_failure_alert(
        self,
        *,
        zone_id: int,
        cmd_id: str,
        status: str,
        command_info: Dict[str, Any],
        error: Optional[str],
    ) -> None:
        await emit_failure_alert_impl(
            self,
            zone_id=zone_id,
            cmd_id=cmd_id,
            status=status,
            command_info=command_info,
            error=error,
        )

    async def confirm_command(
        self,
        cmd_id: str,
        success: bool,
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        """
        DEPRECATED: Используйте _confirm_command_internal или проверку через БД.
        Оставлено для обратной совместимости.
        """
        status = 'DONE' if success else 'ERROR'
        await self._confirm_command_internal(cmd_id, status, response, error)

    async def confirm_command_status(
        self,
        cmd_id: str,
        status: str,
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Явно подтвердить команду заданным статусом.
        Используется для сценариев, когда публикация команды не удалась до получения ACK.
        """
        normalized_status = str(status or "").strip().upper()
        if normalized_status in {"TIMEOUT", "SEND_FAILED"}:
            await self._persist_terminal_status(cmd_id=cmd_id, status=normalized_status, error=error)
        await self._confirm_command_internal(cmd_id, normalized_status or status, response, error)

    async def _persist_terminal_status(
        self,
        *,
        cmd_id: str,
        status: str,
        error: Optional[str],
    ) -> None:
        await persist_terminal_status_impl(self, cmd_id=cmd_id, status=status, error=error)

    async def _check_timeout(self, cmd_id: str):
        await check_timeout_impl(self, cmd_id)
    
    async def _get_command_status_from_db(self, cmd_id: str) -> Optional[str]:
        """
        Получить статус команды из таблицы commands.
        
        Args:
            cmd_id: ID команды
        
        Returns:
            Статус команды ('QUEUED', 'SENT', 'ACK', 'DONE', 'ERROR', 'INVALID', 'BUSY', 'NO_EFFECT', 'TIMEOUT', 'SEND_FAILED') или None
        """
        try:
            rows = await fetch(
                """
                SELECT status FROM commands WHERE cmd_id = $1
                """,
                cmd_id
            )
            if rows and len(rows) > 0:
                return rows[0].get('status')
        except Exception as e:
            logger.debug(f"Failed to get command status from DB for {cmd_id}: {e}")
        return None

    async def _fetch_rows(self, query: str, *args: Any) -> Any:
        return await fetch(query, *args)

    def _on_command_status_notify(self, _connection, _pid: int, _channel: str, payload: str) -> None:
        on_command_status_notify_impl(self, payload)

    async def _handle_notify_payload(self, payload: str) -> None:
        await handle_notify_payload_impl(self, payload)

    async def _listen_command_statuses(self) -> None:
        await listen_command_statuses_impl(self)

    async def _close_notify_connection(self) -> None:
        await close_notify_connection_impl(self)

    async def get_command_outcome(self, cmd_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить детализированный terminal outcome команды из таблицы commands.

        Returns:
            Dict со статусом и ошибкой либо None, если команда не найдена.
        """
        try:
            rows = await fetch(
                """
                SELECT status, error_code, error_message, ack_at, failed_at, updated_at
                FROM commands
                WHERE cmd_id = $1
                LIMIT 1
                """,
                cmd_id,
            )
            if not rows:
                return None

            row = rows[0]
            return {
                "status": str(row.get("status") or "").strip().upper() or None,
                "error_code": row.get("error_code"),
                "error_message": row.get("error_message"),
                "ack_at": row.get("ack_at"),
                "failed_at": row.get("failed_at"),
                "updated_at": row.get("updated_at"),
            }
        except Exception as exc:
            logger.debug("Failed to get command outcome from DB for %s: %s", cmd_id, exc)
            return None
    
    async def _poll_command_statuses(self):
        await poll_command_statuses_impl(self)
    
    async def start_polling(self):
        """Запустить периодическую проверку статусов команд из БД."""
        await start_polling_impl(self)
    
    async def stop_polling(self):
        """Остановить периодическую проверку статусов команд и LISTEN-подписку."""
        await stop_polling_impl(self)
    
    async def restore_pending_commands(self):
        """
        Восстановить pending команды из БД после рестарта.
        Загружает команды со статусами 'QUEUED', 'SENT' или 'ACK', которые были отправлены недавно.
        """
        await restore_pending_commands_impl(self)
    
    async def wait_for_command_done(
        self,
        cmd_id: str,
        timeout_sec: Optional[float] = None,
        poll_interval_sec: float = 1.0
    ) -> Optional[bool]:
        """
        Явно ждать завершения команды (DONE).
        
        ВАЖНО: Успехом считается только DONE.
        NO_EFFECT трактуется как неуспех команды.
        ACK - промежуточный статус, команда еще выполняется.
        
        Args:
            cmd_id: ID команды
            timeout_sec: Таймаут ожидания в секундах (None = использовать command_timeout)
            poll_interval_sec: Интервал проверки статуса в секундах
        
        Returns:
            True если команда завершилась со статусом DONE
            False если команда завершилась со статусом NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED
            None если истек таймаут
        """
        return await wait_for_command_done_impl(
            self,
            cmd_id=cmd_id,
            timeout_sec=timeout_sec,
            poll_interval_sec=poll_interval_sec,
        )
    
    async def get_pending_commands(self, zone_id: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
        """
        Получить список ожидающих команд.
        
        Args:
            zone_id: Фильтр по зоне (опционально)
        
        Returns:
            Словарь cmd_id -> command_info
        """
        if zone_id is None:
            return self.pending_commands.copy()
        
        return {
            cmd_id: cmd_info
            for cmd_id, cmd_info in self.pending_commands.items()
            if cmd_info['zone_id'] == zone_id
        }
    
    async def cleanup_old_commands(self, max_age_hours: int = 24):
        """
        DEPRECATED: Очистка команд теперь выполняется через Laravel (архивирование в commands_archive).
        Оставлено для обратной совместимости.
        """
        # Очистка команд выполняется через Laravel, не нужно делать это здесь
        logger.debug("Command cleanup is handled by Laravel (archiving to commands_archive)")
