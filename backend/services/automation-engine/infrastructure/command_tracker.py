"""
Отслеживание выполнения команд.
Позволяет проверять успешность выполнения команд и обрабатывать таймауты.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Optional, Any
from datetime import datetime
from common.db import execute, fetch, create_zone_event
from prometheus_client import Histogram, Counter, Gauge

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


class CommandTracker:
    """
    Отслеживание выполнения команд.
    
    Отслеживает отправленные команды и их подтверждения от узлов.
    """
    
    def __init__(self, command_timeout: int = 300):
        """
        Инициализация трекера команд.
        
        Args:
            command_timeout: Таймаут команды в секундах (по умолчанию 5 минут)
        """
        self.pending_commands: Dict[str, Dict[str, Any]] = {}
        self.command_timeout = command_timeout
        self._timeout_tasks: Dict[str, asyncio.Task] = {}
    
    async def track_command(
        self,
        zone_id: int,
        command: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Начать отслеживание команды.
        
        Args:
            zone_id: ID зоны
            command: Команда для отслеживания
            context: Дополнительный контекст
        
        Returns:
            cmd_id: Уникальный ID команды
        """
        cmd_id = f"{zone_id}_{int(time.time() * 1000)}"
        
        command_info = {
            'cmd_id': cmd_id,
            'zone_id': zone_id,
            'command': command,
            'command_type': command.get('cmd', 'unknown'),
            'sent_at': datetime.utcnow(),
            'status': 'pending',
            'context': context or {}
        }
        
        self.pending_commands[cmd_id] = command_info
        
        # Обновляем метрики
        PENDING_COMMANDS.labels(zone_id=str(zone_id)).inc()
        
        # Сохраняем в БД
        try:
            await execute(
                """
                INSERT INTO command_tracking (cmd_id, zone_id, command, status, sent_at, context)
                VALUES ($1, $2, $3, 'pending', NOW(), $4)
                """,
                cmd_id,
                zone_id,
                json.dumps(command),
                json.dumps(context) if context else None
            )
        except Exception as e:
            logger.warning(f"Failed to save command tracking to DB: {e}", exc_info=True)
        
        # Устанавливаем таймаут
        timeout_task = asyncio.create_task(self._check_timeout(cmd_id))
        self._timeout_tasks[cmd_id] = timeout_task
        
        logger.debug(
            f"Zone {zone_id}: Command {cmd_id} tracked",
            extra={
                'zone_id': zone_id,
                'cmd_id': cmd_id,
                'command_type': command.get('cmd')
            }
        )
        
        return cmd_id
    
    async def confirm_command(
        self,
        cmd_id: str,
        success: bool,
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        """
        Подтвердить выполнение команды.
        
        Args:
            cmd_id: ID команды
            success: Успешность выполнения
            response: Ответ от узла
            error: Сообщение об ошибке
        """
        if cmd_id not in self.pending_commands:
            logger.warning(f"Command {cmd_id} not found in pending commands")
            return
        
        command_info = self.pending_commands[cmd_id]
        zone_id = command_info['zone_id']
        command_type = command_info['command_type']
        
        # Отменяем таймаут
        if cmd_id in self._timeout_tasks:
            self._timeout_tasks[cmd_id].cancel()
            del self._timeout_tasks[cmd_id]
        
        # Обновляем статус
        command_info['status'] = 'completed' if success else 'failed'
        command_info['completed_at'] = datetime.utcnow()
        command_info['response'] = response
        command_info['error'] = error
        
        # Вычисляем задержку
        latency = (command_info['completed_at'] - command_info['sent_at']).total_seconds()
        COMMAND_LATENCY.labels(zone_id=str(zone_id), command_type=command_type).observe(latency)
        
        # Обновляем метрики
        PENDING_COMMANDS.labels(zone_id=str(zone_id)).dec()
        
        if success:
            COMMAND_SUCCESS.labels(zone_id=str(zone_id), command_type=command_type).inc()
        else:
            reason = error or 'unknown'
            COMMAND_FAILURE.labels(zone_id=str(zone_id), command_type=command_type, reason=reason).inc()
        
        # Обновляем в БД
        try:
            await execute(
                """
                UPDATE command_tracking
                SET status = $1, completed_at = NOW(), response = $2, error = $3, latency_seconds = $4
                WHERE cmd_id = $5
                """,
                'completed' if success else 'failed',
                json.dumps(response) if response else None,
                error,
                latency,
                cmd_id
            )
        except Exception as e:
            logger.warning(f"Failed to update command tracking in DB: {e}", exc_info=True)
        
        # Логируем результат
        if success:
            logger.info(
                f"Zone {zone_id}: Command {cmd_id} completed successfully",
                extra={
                    'zone_id': zone_id,
                    'cmd_id': cmd_id,
                    'command_type': command_type,
                    'latency': latency
                }
            )
        else:
            logger.warning(
                f"Zone {zone_id}: Command {cmd_id} failed: {error}",
                extra={
                    'zone_id': zone_id,
                    'cmd_id': cmd_id,
                    'command_type': command_type,
                    'error': error,
                    'latency': latency
                }
            )
        
        # Удаляем из pending (оставляем в БД для истории)
        del self.pending_commands[cmd_id]
    
    async def _check_timeout(self, cmd_id: str):
        """Проверить таймаут команды."""
        try:
            await asyncio.sleep(self.command_timeout)
            
            if cmd_id in self.pending_commands:
                command_info = self.pending_commands[cmd_id]
                if command_info['status'] == 'pending':
                    # Команда не подтверждена
                    zone_id = command_info['zone_id']
                    command_type = command_info['command_type']
                    
                    logger.warning(
                        f"Zone {zone_id}: Command {cmd_id} timed out after {self.command_timeout}s",
                        extra={
                            'zone_id': zone_id,
                            'cmd_id': cmd_id,
                            'command_type': command_type,
                            'timeout': self.command_timeout
                        }
                    )
                    
                    COMMAND_TIMEOUT.labels(zone_id=str(zone_id), command_type=command_type).inc()
                    PENDING_COMMANDS.labels(zone_id=str(zone_id)).dec()
                    
                    # Подтверждаем как failed
                    await self.confirm_command(cmd_id, False, error='timeout')
                    
                    # Создаем событие
                    await create_zone_event(
                        zone_id,
                        'COMMAND_TIMEOUT',
                        {
                            'cmd_id': cmd_id,
                            'command': command_info['command'],
                            'timeout_seconds': self.command_timeout
                        }
                    )
        except asyncio.CancelledError:
            # Таймаут отменен (команда подтверждена)
            pass
        except Exception as e:
            logger.error(f"Error in timeout check for command {cmd_id}: {e}", exc_info=True)
    
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
        Очистить старые команды из БД.
        
        Args:
            max_age_hours: Максимальный возраст команд в часах
        """
        try:
            await execute(
                """
                DELETE FROM command_tracking
                WHERE completed_at < NOW() - INTERVAL '%s hours'
                OR (status = 'pending' AND sent_at < NOW() - INTERVAL '%s hours')
                """,
                max_age_hours,
                max_age_hours
            )
            logger.info(f"Cleaned up old commands (older than {max_age_hours} hours)")
        except Exception as e:
            logger.warning(f"Failed to cleanup old commands: {e}", exc_info=True)


