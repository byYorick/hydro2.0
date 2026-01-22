"""
State Machine для обработки команд с поддержкой негативных режимов.
"""

import asyncio
from enum import Enum
import random
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from collections import deque

from .utils_time import current_timestamp_ms, sleep_ms


class CommandStatus(Enum):
    """Статусы команды в state machine."""
    ACK = "ACK"
    DONE = "DONE"
    ERROR = "ERROR"
    INVALID = "INVALID"
    BUSY = "BUSY"
    NO_EFFECT = "NO_EFFECT"


@dataclass
class FailureMode:
    """Режим отказов для тестирования."""
    delay_response: bool = False
    delay_ms: int = 0
    drop_response: bool = False
    duplicate_response: bool = False
    delay_done_ms: int = 0  # Задержка перед отправкой DONE
    drop_next_response: bool = False  # Пропустить следующий ответ
    duplicate_next_response: bool = False  # Дублировать следующий ответ
    random_drop_rate: float = 0.0
    random_duplicate_rate: float = 0.0
    random_delay_ms_min: int = 0
    random_delay_ms_max: int = 0


@dataclass
class CommandState:
    """Состояние команды в state machine."""
    cmd_id: str
    cmd: str
    params: Dict[str, Any]
    status: CommandStatus = CommandStatus.ACK
    exec_time_ms: int = 0  # Время выполнения команды
    response_payload: Optional[Dict[str, Any]] = None
    accepted_at_ms: int = field(default_factory=current_timestamp_ms)
    done_at_ms: Optional[int] = None
    channel: Optional[str] = None


class CommandStateMachine:
    """
    State Machine для обработки команд.
    
    Поддерживает:
    - Переходы ACK -> DONE/ERROR/INVALID/BUSY/NO_EFFECT
    - Негативные режимы (drop, duplicate, delay)
    - Идемпотентность через кеш
    """
    
    def __init__(self):
        self.active_commands: Dict[str, CommandState] = {}
        self.failure_mode: Optional[FailureMode] = None
        self._pending_drops: set = set()  # cmd_id, которые нужно пропустить
        self._pending_duplicates: set = set()  # cmd_id, которые нужно дублировать
    
    def set_failure_mode(self, failure_mode: FailureMode):
        """Установить режим отказов."""
        self.failure_mode = failure_mode
    
    def accept_command(
        self,
        cmd_id: str,
        cmd: str,
        params: Dict[str, Any],
        exec_time_ms: int = 100,
        channel: Optional[str] = None
    ) -> CommandState:
        """
        Принять команду и создать состояние ACK.
        
        Args:
            cmd_id: ID команды
            cmd: Имя команды
            params: Параметры команды
            exec_time_ms: Время выполнения в миллисекундах
            channel: Канал команды
        
        Returns:
            CommandState в статусе ACK
        """
        state = CommandState(
            cmd_id=cmd_id,
            cmd=cmd,
            params=params,
            status=CommandStatus.ACK,
            exec_time_ms=exec_time_ms,
            channel=channel
        )
        self.active_commands[cmd_id] = state
        return state
    
    async def execute_command(
        self,
        state: CommandState,
        executor: Callable[[str, Dict[str, Any]], tuple[CommandStatus, Optional[Dict[str, Any]]]]
    ) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """
        Выполнить команду и перевести в DONE/ERROR/INVALID/BUSY/NO_EFFECT.
        
        Args:
            state: Состояние команды
            executor: Функция выполнения команды (cmd, params) -> (status, payload)
        
        Returns:
            (final_status, response_payload)
        """
        # Применяем задержку выполнения, если указана
        if state.exec_time_ms > 0:
            await asyncio.sleep(state.exec_time_ms / 1000.0)
        
        # Выполняем команду
        try:
            final_status, response_payload = executor(state.cmd, state.params)
        except Exception as e:
            final_status = CommandStatus.ERROR
            response_payload = {"error": str(e)}
        
        # Применяем задержку перед отправкой DONE (негативный режим)
        if self.failure_mode and self.failure_mode.delay_done_ms > 0:
            await asyncio.sleep(self.failure_mode.delay_done_ms / 1000.0)
        
        # Обновляем состояние
        state.status = final_status
        state.response_payload = response_payload
        state.done_at_ms = current_timestamp_ms()
        
        return final_status, response_payload
    
    def should_drop_response(self, cmd_id: str) -> bool:
        """Проверить, нужно ли пропустить ответ."""
        if not self.failure_mode:
            return False
        
        # Проверяем глобальный флаг
        if self.failure_mode.drop_response:
            return True

        if self.failure_mode.random_drop_rate > 0 and random.random() < self.failure_mode.random_drop_rate:
            return True
        
        # Проверяем флаг для следующего ответа
        if cmd_id in self._pending_drops:
            self._pending_drops.discard(cmd_id)
            return True
        
        return False
    
    def should_duplicate_response(self, cmd_id: str) -> bool:
        """Проверить, нужно ли дублировать ответ."""
        if not self.failure_mode:
            return False
        
        # Проверяем глобальный флаг
        if self.failure_mode.duplicate_response:
            return True

        if self.failure_mode.random_duplicate_rate > 0 and random.random() < self.failure_mode.random_duplicate_rate:
            return True
        
        # Проверяем флаг для следующего ответа
        if cmd_id in self._pending_duplicates:
            self._pending_duplicates.discard(cmd_id)
            return True
        
        return False
    
    def mark_drop_next_response(self, cmd_id: str):
        """Пометить, что следующий ответ для cmd_id нужно пропустить."""
        self._pending_drops.add(cmd_id)
    
    def mark_duplicate_next_response(self, cmd_id: str):
        """Пометить, что следующий ответ для cmd_id нужно дублировать."""
        self._pending_duplicates.add(cmd_id)

    def get_response_delay_ms(self) -> int:
        """Получить задержку перед отправкой ответа."""
        if not self.failure_mode:
            return 0
        if self.failure_mode.delay_response and self.failure_mode.delay_ms > 0:
            return self.failure_mode.delay_ms
        if self.failure_mode.random_delay_ms_max > 0:
            low = max(0, self.failure_mode.random_delay_ms_min)
            high = max(low, self.failure_mode.random_delay_ms_max)
            return random.randint(low, high)
        return 0
    
    def get_state(self, cmd_id: str) -> Optional[CommandState]:
        """Получить состояние команды."""
        return self.active_commands.get(cmd_id)
    
    def remove_state(self, cmd_id: str):
        """Удалить состояние команды (после отправки ответа)."""
        self.active_commands.pop(cmd_id, None)
    
    def clear(self):
        """Очистить все состояния."""
        self.active_commands.clear()
        self._pending_drops.clear()
        self._pending_duplicates.clear()
