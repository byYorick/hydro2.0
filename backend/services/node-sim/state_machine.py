"""
Машина состояний для обработки команд.
Управляет жизненным циклом команды: ACCEPTED -> DONE/FAILED
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class CommandStatus(str, Enum):
    """Статусы команды в машине состояний."""
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    EXECUTING = "EXECUTING"
    DONE = "DONE"
    FAILED = "FAILED"


class CommandState:
    """Состояние команды в машине состояний."""
    
    def __init__(self, cmd_id: str, cmd: str, params: Dict[str, Any], deadline_ms: Optional[int] = None):
        self.cmd_id = cmd_id
        self.cmd = cmd
        self.params = params
        self.deadline_ms = deadline_ms
        self.status = CommandStatus.PENDING
        self.created_at = time.time() * 1000  # миллисекунды
        self.accepted_at: Optional[float] = None
        self.done_at: Optional[float] = None
        self.error_code: Optional[str] = None
        self.error_message: Optional[str] = None
        self.execution_task: Optional[asyncio.Task] = None
    
    def accept(self):
        """Принять команду."""
        if self.status != CommandStatus.PENDING:
            raise ValueError(f"Cannot accept command in status {self.status}")
        self.status = CommandStatus.ACCEPTED
        self.accepted_at = time.time() * 1000
    
    def start_execution(self, task: asyncio.Task):
        """Начать выполнение команды."""
        if self.status != CommandStatus.ACCEPTED:
            raise ValueError(f"Cannot start execution in status {self.status}")
        self.status = CommandStatus.EXECUTING
        self.execution_task = task
    
    def complete(self):
        """Завершить команду успешно."""
        if self.status != CommandStatus.EXECUTING:
            raise ValueError(f"Cannot complete command in status {self.status}")
        self.status = CommandStatus.DONE
        self.done_at = time.time() * 1000
    
    def fail(self, error_code: Optional[str] = None, error_message: Optional[str] = None):
        """Завершить команду с ошибкой."""
        if self.status not in (CommandStatus.ACCEPTED, CommandStatus.EXECUTING):
            raise ValueError(f"Cannot fail command in status {self.status}")
        self.status = CommandStatus.FAILED
        self.done_at = time.time() * 1000
        self.error_code = error_code
        self.error_message = error_message
    
    def get_duration_ms(self) -> Optional[int]:
        """Получить длительность выполнения команды в миллисекундах."""
        if self.accepted_at and self.done_at:
            return int(self.done_at - self.accepted_at)
        return None
    
    def is_expired(self) -> bool:
        """Проверить, истек ли дедлайн команды."""
        if not self.deadline_ms:
            return False
        elapsed = (time.time() * 1000) - self.created_at
        return elapsed > self.deadline_ms


class FailureMode:
    """Режимы отказов для тестирования."""
    
    def __init__(
        self,
        delay_response: bool = False,
        delay_ms: int = 0,
        drop_response: bool = False,
        duplicate_response: bool = False
    ):
        self.delay_response = delay_response
        self.delay_ms = delay_ms
        self.drop_response = drop_response
        self.duplicate_response = duplicate_response


class CommandStateMachine:
    """
    Машина состояний для управления командами.
    
    Обрабатывает:
    - Дедупликацию по cmd_id (LRU 128)
    - Переходы состояний: PENDING -> ACCEPTED -> EXECUTING -> DONE/FAILED
    - Режимы отказов: delay, drop, duplicate
    """
    
    def __init__(self, max_commands: int = 128):
        """
        Инициализация машины состояний.
        
        Args:
            max_commands: Максимальное количество команд в LRU кэше
        """
        self._commands: Dict[str, CommandState] = {}
        self._max_commands = max_commands
        self._failure_mode: Optional[FailureMode] = None
        self._lock = asyncio.Lock()
    
    def set_failure_mode(self, mode: Optional[FailureMode]):
        """Установить режим отказов."""
        self._failure_mode = mode
    
    async def process_command(
        self,
        cmd_id: str,
        cmd: str,
        params: Dict[str, Any],
        deadline_ms: Optional[int] = None,
        executor: callable = None
    ) -> CommandState:
        """
        Обработать команду.
        
        Args:
            cmd_id: ID команды
            cmd: Тип команды
            params: Параметры команды
            deadline_ms: Дедлайн выполнения
            executor: Функция-исполнитель команды (async)
        
        Returns:
            CommandState
        """
        async with self._lock:
            # Дедупликация по cmd_id
            if cmd_id in self._commands:
                existing = self._commands[cmd_id]
                logger.warning(f"Duplicate command {cmd_id}, status={existing.status}")
                return existing
            
            # Проверка лимита LRU
            if len(self._commands) >= self._max_commands:
                # Удаляем самую старую команду
                oldest_id = min(
                    self._commands.keys(),
                    key=lambda k: self._commands[k].created_at
                )
                del self._commands[oldest_id]
                logger.debug(f"Removed oldest command {oldest_id} from LRU cache")
            
            # Создаем новое состояние команды
            state = CommandState(cmd_id, cmd, params, deadline_ms)
            self._commands[cmd_id] = state
            
            # Принимаем команду
            state.accept()
            
            # Запускаем выполнение
            if executor:
                task = asyncio.create_task(
                    self._execute_command(state, executor)
                )
                state.start_execution(task)
            else:
                # Без исполнителя просто помечаем как DONE
                state.status = CommandStatus.DONE
                state.done_at = time.time() * 1000
        
        return state
    
    async def _execute_command(self, state: CommandState, executor: callable):
        """Выполнить команду."""
        try:
            # Проверка дедлайна
            if state.is_expired():
                state.fail("deadline_expired", "Command deadline expired")
                return
            
            # Симулируем время выполнения команды
            execution_time_ms = self._get_execution_time(state.cmd, state.params)
            
            # Применяем режим отказов
            if self._failure_mode and self._failure_mode.delay_response:
                execution_time_ms += self._failure_mode.delay_ms
            
            await asyncio.sleep(execution_time_ms / 1000.0)
            
            # Проверка режима drop
            if self._failure_mode and self._failure_mode.drop_response:
                logger.warning(f"Dropping response for command {state.cmd_id} (failure mode)")
                return
            
            # Выполняем команду
            try:
                result = await executor(state.cmd, state.params)
                if result is False:
                    state.fail("execution_failed", "Command execution returned False")
                else:
                    state.complete()
            except Exception as e:
                logger.error(f"Command execution error: {e}", exc_info=True)
                state.fail("execution_error", str(e))
        
        except asyncio.CancelledError:
            state.fail("cancelled", "Command execution cancelled")
        except Exception as e:
            logger.error(f"Unexpected error in command execution: {e}", exc_info=True)
            state.fail("unexpected_error", str(e))
    
    def _get_execution_time(self, cmd: str, params: Dict[str, Any]) -> int:
        """
        Получить симулированное время выполнения команды в миллисекундах.
        
        Args:
            cmd: Тип команды
            params: Параметры команды
        
        Returns:
            Время выполнения в миллисекундах
        """
        # Базовые времена для разных команд
        base_times = {
            "run_pump": 100,  # 100ms
            "set_relay": 50,  # 50ms
            "set_pwm": 30,  # 30ms
            "calibrate": 2000,  # 2 секунды
        }
        
        base_time = base_times.get(cmd, 100)
        
        # Для run_pump учитываем duration_ms из params
        if cmd == "run_pump" and "duration_ms" in params:
            return int(params["duration_ms"])
        
        return base_time
    
    def get_command_state(self, cmd_id: str) -> Optional[CommandState]:
        """Получить состояние команды."""
        return self._commands.get(cmd_id)
    
    def should_duplicate_response(self, cmd_id: str) -> bool:
        """Проверить, нужно ли дублировать ответ (режим отказов)."""
        if self._failure_mode and self._failure_mode.duplicate_response:
            return True
        return False

