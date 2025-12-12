"""
Отслеживание выполнения команд.
Позволяет проверять успешность выполнения команд и обрабатывать таймауты.

Статусы команд отслеживаются через таблицу commands в БД, которая обновляется history-logger.
Это обеспечивает единый источник истины и работу после рестарта.

Статусы команд:
- QUEUED: команда в очереди
- SENT: команда отправлена
- ACCEPTED: команда принята узлом (промежуточный статус)
- DONE: команда выполнена успешно (терминальный)
- FAILED: команда провалилась (терминальный)
- TIMEOUT: таймаут выполнения команды (терминальный)
- SEND_FAILED: ошибка отправки команды (терминальный)

Терминальные статусы: DONE, FAILED, TIMEOUT, SEND_FAILED
"""
import asyncio
import json
import logging
import time
from typing import Dict, Optional, Any
from datetime import datetime
from common.db import execute, fetch, create_zone_event
from common.commands import new_command_id
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
        self._shutdown_event = asyncio.Event()
    
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
            cmd_id: Уникальный ID команды (UUID формат, совместимый с history-logger)
        """
        cmd_id = new_command_id()
        
        command_info = {
            'cmd_id': cmd_id,
            'zone_id': zone_id,
            'command': command,
            'command_type': command.get('cmd', 'unknown'),
            'sent_at': datetime.utcnow(),
            'status': 'QUEUED',
            'context': context or {}
        }
        
        self.pending_commands[cmd_id] = command_info
        
        # Обновляем метрики
        PENDING_COMMANDS.labels(zone_id=str(zone_id)).inc()
        
        # Команда будет сохранена в таблицу commands через history-logger/Laravel
        # Мы только отслеживаем её локально и проверяем статус из БД
        
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
    
    async def _confirm_command_internal(
        self,
        cmd_id: str,
        status: str,  # 'DONE', 'FAILED', 'TIMEOUT', 'SEND_FAILED'
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        """
        Внутренний метод для подтверждения команды на основе статуса из БД.
        
        Args:
            cmd_id: ID команды
            status: Статус из БД ('DONE', 'FAILED', 'TIMEOUT', 'SEND_FAILED')
            response: Ответ от узла (опционально)
            error: Сообщение об ошибке (опционально)
        """
        if cmd_id not in self.pending_commands:
            # Команда может быть не в pending, если она была восстановлена из БД
            logger.debug(f"Command {cmd_id} not found in pending commands (may be already processed)")
            return
        
        command_info = self.pending_commands[cmd_id]
        zone_id = command_info['zone_id']
        command_type = command_info['command_type']
        
        # Отменяем таймаут
        if cmd_id in self._timeout_tasks:
            self._timeout_tasks[cmd_id].cancel()
            del self._timeout_tasks[cmd_id]
        
        # Определяем успешность на основе статуса
        # ВАЖНО: Успехом считается только DONE, не ACCEPTED!
        # ACCEPTED - это промежуточный статус (команда принята, но еще выполняется)
        success = (status == 'DONE')
        
        # Обновляем статус
        command_info['status'] = status
        command_info['completed_at'] = datetime.utcnow()
        if response:
            command_info['response'] = response
        if error:
            command_info['error'] = error
        
        # Вычисляем задержку
        latency = (command_info['completed_at'] - command_info['sent_at']).total_seconds()
        COMMAND_LATENCY.labels(zone_id=str(zone_id), command_type=command_type).observe(latency)
        
        # Обновляем метрики
        PENDING_COMMANDS.labels(zone_id=str(zone_id)).dec()
        
        if success:
            COMMAND_SUCCESS.labels(zone_id=str(zone_id), command_type=command_type).inc()
        else:
            reason = error or status
            COMMAND_FAILURE.labels(zone_id=str(zone_id), command_type=command_type, reason=reason).inc()
        
        # Логируем результат
        if success:
            logger.info(
                f"Zone {zone_id}: Command {cmd_id} completed successfully (status: {status})",
                extra={
                    'zone_id': zone_id,
                    'cmd_id': cmd_id,
                    'command_type': command_type,
                    'status': status,
                    'latency': latency
                }
            )
        else:
            logger.warning(
                f"Zone {zone_id}: Command {cmd_id} failed (status: {status}): {error}",
                extra={
                    'zone_id': zone_id,
                    'cmd_id': cmd_id,
                    'command_type': command_type,
                    'status': status,
                    'error': error,
                    'latency': latency
                }
            )
        
        # Удаляем из pending
        del self.pending_commands[cmd_id]
    
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
        status = 'DONE' if success else 'FAILED'
        await self._confirm_command_internal(cmd_id, status, response, error)
    
    async def _check_timeout(self, cmd_id: str):
        """Проверить таймаут команды."""
        try:
            await asyncio.sleep(self.command_timeout)
            
            if cmd_id in self.pending_commands:
                command_info = self.pending_commands[cmd_id]
                # Проверяем статус в БД перед обработкой таймаута
                db_status = await self._get_command_status_from_db(cmd_id)
                
                if db_status and db_status in ('DONE', 'FAILED', 'TIMEOUT', 'SEND_FAILED'):
                    # Команда уже обработана, просто удаляем из pending
                    logger.debug(f"Command {cmd_id} already processed in DB (status: {db_status}), removing from pending")
                    del self.pending_commands[cmd_id]
                    if cmd_id in self._timeout_tasks:
                        self._timeout_tasks[cmd_id].cancel()
                        del self._timeout_tasks[cmd_id]
                    return
                
                if command_info['status'] in ('QUEUED', 'SENT', 'ACCEPTED'):
                    # Команда не завершена (в очереди, отправлена или принята, но еще не выполнена)
                    zone_id = command_info['zone_id']
                    command_type = command_info['command_type']
                    
                    logger.warning(
                        f"Zone {zone_id}: Command {cmd_id} timed out after {self.command_timeout}s (status: {command_info['status']})",
                        extra={
                            'zone_id': zone_id,
                            'cmd_id': cmd_id,
                            'command_type': command_type,
                            'timeout': self.command_timeout,
                            'status': command_info['status']
                        }
                    )
                    
                    COMMAND_TIMEOUT.labels(zone_id=str(zone_id), command_type=command_type).inc()
                    PENDING_COMMANDS.labels(zone_id=str(zone_id)).dec()
                    
                    # Подтверждаем как timeout
                    await self._confirm_command_internal(cmd_id, 'TIMEOUT', error='timeout')
                    
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
    
    async def _get_command_status_from_db(self, cmd_id: str) -> Optional[str]:
        """
        Получить статус команды из таблицы commands.
        
        Args:
            cmd_id: ID команды
        
        Returns:
            Статус команды ('QUEUED', 'SENT', 'ACCEPTED', 'DONE', 'FAILED', 'TIMEOUT', 'SEND_FAILED') или None
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
    
    async def _poll_command_statuses(self):
        """
        Периодически проверяет статусы команд из БД и обновляет внутреннее состояние.
        
        ВАЖНО: Обрабатываются только терминальные статусы (DONE, FAILED, TIMEOUT, SEND_FAILED).
        ACCEPTED не обрабатывается, так как это промежуточный статус.
        """
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(self.poll_interval)
                
                if not self.pending_commands:
                    continue
                
                # Получаем список cmd_id для проверки
                cmd_ids = list(self.pending_commands.keys())
                
                if not cmd_ids:
                    continue
                
                # Проверяем статусы в БД батчами
                try:
                    rows = await fetch(
                        """
                        SELECT cmd_id, status, ack_at, failed_at, error_message
                        FROM commands
                        WHERE cmd_id = ANY($1::text[])
                        AND status IN ('DONE', 'FAILED', 'TIMEOUT', 'SEND_FAILED')
                        """,
                        cmd_ids
                    )
                    
                    # Обрабатываем обновленные команды
                    for row in rows:
                        cmd_id = row['cmd_id']
                        status = row['status']
                        
                        if cmd_id in self.pending_commands:
                            # Команда завершена, обновляем состояние
                            error = None
                            if status in ('FAILED', 'TIMEOUT', 'SEND_FAILED'):
                                error = row.get('error_message') or f'Command {status}'
                            
                            await self._confirm_command_internal(cmd_id, status, error=error)
                            
                except Exception as e:
                    logger.warning(f"Error polling command statuses from DB: {e}", exc_info=True)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in command status polling loop: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)
    
    async def start_polling(self):
        """Запустить периодическую проверку статусов команд из БД."""
        if self._poll_task is None or self._poll_task.done():
            self._shutdown_event.clear()
            self._poll_task = asyncio.create_task(self._poll_command_statuses())
            logger.info(f"Started command status polling (interval: {self.poll_interval}s)")
    
    async def stop_polling(self):
        """Остановить периодическую проверку статусов команд."""
        self._shutdown_event.set()
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped command status polling")
    
    async def restore_pending_commands(self):
        """
        Восстановить pending команды из БД после рестарта.
        Загружает команды со статусами 'QUEUED', 'SENT' или 'ACCEPTED', которые были отправлены недавно.
        """
        try:
            # Загружаем команды, которые были отправлены в последние command_timeout секунд
            rows = await fetch(
                """
                SELECT cmd_id, zone_id, cmd, params, status, sent_at, created_at
                FROM commands
                WHERE status IN ('QUEUED', 'SENT', 'ACCEPTED')
                AND (sent_at IS NOT NULL AND sent_at > NOW() - INTERVAL '%s seconds')
                OR (sent_at IS NULL AND created_at > NOW() - INTERVAL '%s seconds')
                ORDER BY created_at DESC
                LIMIT 1000
                """,
                self.command_timeout,
                self.command_timeout
            )
            
            restored_count = 0
            for row in rows:
                cmd_id = row['cmd_id']
                zone_id = row['zone_id']
                cmd = row['cmd']
                params = row.get('params') or {}
                status = row['status']
                sent_at = row.get('sent_at') or row.get('created_at')
                
                # Восстанавливаем команду в pending_commands
                command_info = {
                    'cmd_id': cmd_id,
                    'zone_id': zone_id,
                    'command': {'cmd': cmd, 'params': params},
                    'command_type': cmd,
                    'sent_at': sent_at if isinstance(sent_at, datetime) else datetime.utcnow(),
                    'status': status,
                    'context': {}
                }
                
                self.pending_commands[cmd_id] = command_info
                PENDING_COMMANDS.labels(zone_id=str(zone_id)).inc()
                
                # Устанавливаем таймаут
                timeout_task = asyncio.create_task(self._check_timeout(cmd_id))
                self._timeout_tasks[cmd_id] = timeout_task
                
                restored_count += 1
            
            if restored_count > 0:
                logger.info(f"Restored {restored_count} pending commands from DB after restart")
            else:
                logger.debug("No pending commands to restore from DB")
                
        except Exception as e:
            logger.warning(f"Failed to restore pending commands from DB: {e}", exc_info=True)
    
    async def wait_for_command_done(
        self,
        cmd_id: str,
        timeout_sec: Optional[float] = None,
        poll_interval_sec: float = 1.0
    ) -> Optional[bool]:
        """
        Явно ждать завершения команды (статус DONE).
        
        ВАЖНО: Успехом считается только статус DONE, не ACCEPTED!
        ACCEPTED - это промежуточный статус, команда еще выполняется.
        
        Args:
            cmd_id: ID команды
            timeout_sec: Таймаут ожидания в секундах (None = использовать command_timeout)
            poll_interval_sec: Интервал проверки статуса в секундах
        
        Returns:
            True если команда завершилась со статусом DONE
            False если команда завершилась со статусом FAILED/TIMEOUT/SEND_FAILED
            None если истек таймаут
        """
        if timeout_sec is None:
            timeout_sec = self.command_timeout
        
        start_time = time.time()
        
        while (time.time() - start_time) < timeout_sec:
            db_status = await self._get_command_status_from_db(cmd_id)
            
            if db_status == 'DONE':
                # Команда успешно завершена
                if cmd_id in self.pending_commands:
                    await self._confirm_command_internal(cmd_id, 'DONE')
                return True
            
            if db_status in ('FAILED', 'TIMEOUT', 'SEND_FAILED'):
                # Команда завершилась с ошибкой
                if cmd_id in self.pending_commands:
                    error = f'Command {db_status}'
                    await self._confirm_command_internal(cmd_id, db_status, error=error)
                return False
            
            # Промежуточные статусы (QUEUED, SENT, ACCEPTED) - продолжаем ждать
            await asyncio.sleep(poll_interval_sec)
        
        # Таймаут
        logger.warning(f"Timeout waiting for command {cmd_id} to complete (waited {timeout_sec}s)")
        return None
    
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


