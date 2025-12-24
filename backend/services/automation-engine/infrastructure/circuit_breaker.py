"""
Circuit Breaker Pattern для защиты от каскадных сбоев.
Предотвращает перегрузку системы при недоступности внешних зависимостей.
"""
import time
import logging
from enum import Enum
from typing import Callable, Awaitable, TypeVar, Optional, Any
from prometheus_client import Gauge, Counter

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Состояния Circuit Breaker."""
    CLOSED = "closed"  # Нормальная работа
    OPEN = "open"  # Сбой, запросы блокируются
    HALF_OPEN = "half_open"  # Тестирование восстановления


class CircuitBreakerOpenError(Exception):
    """Исключение при открытом Circuit Breaker."""
    pass


class CircuitBreaker:
    """
    Circuit Breaker для защиты от каскадных сбоев.
    
    Состояния:
    - CLOSED: Нормальная работа, все запросы проходят
    - OPEN: Сбой, все запросы блокируются
    - HALF_OPEN: Тестирование восстановления, ограниченное количество запросов
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        half_open_max_calls: int = 3
    ):
        """
        Инициализация Circuit Breaker.
        
        Args:
            name: Имя компонента (для логирования и метрик)
            failure_threshold: Количество сбоев для перехода в OPEN
            timeout: Время в секундах до попытки восстановления
            half_open_max_calls: Максимальное количество запросов в HALF_OPEN
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0
        
        # Метрики Prometheus
        self.state_gauge = Gauge(
            f"circuit_breaker_state_{name}",
            f"Circuit breaker state for {name} (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
            ["component"]
        )
        self.failures_counter = Counter(
            f"circuit_breaker_failures_total_{name}",
            f"Circuit breaker failures for {name}",
            ["component"]
        )
        self.requests_blocked_counter = Counter(
            f"circuit_breaker_requests_blocked_total_{name}",
            f"Blocked requests for {name}",
            ["component"]
        )
    
    async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        """
        Выполнить функцию через Circuit Breaker.
        
        Args:
            func: Асинхронная функция для выполнения
            *args, **kwargs: Аргументы функции
        
        Returns:
            Результат выполнения функции
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        # Проверяем состояние
        if self.state == CircuitState.OPEN:
            # Проверяем, не прошло ли достаточно времени для попытки восстановления
            if self.last_failure_time and (time.time() - self.last_failure_time) >= self.timeout:
                logger.info(f"Circuit breaker {self.name}: Attempting recovery, transitioning to HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.success_count = 0
            else:
                # Блокируем запрос
                self.requests_blocked_counter.labels(component=self.name).inc()
                raise CircuitBreakerOpenError(
                    f"Circuit breaker {self.name} is OPEN. "
                    f"Last failure: {self.last_failure_time}, "
                    f"Timeout: {self.timeout}s"
                )
        
        # HALF_OPEN: ограничиваем количество запросов
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                logger.warning(
                    f"Circuit breaker {self.name}: HALF_OPEN max calls reached, "
                    f"staying in HALF_OPEN"
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker {self.name} is HALF_OPEN, max calls reached"
                )
            self.half_open_calls += 1
        
        # Выполняем функцию
        try:
            result = await func(*args, **kwargs)
            
            # Успешное выполнение
            self._on_success()
            return result
            
        except Exception as e:
            # Ошибка выполнения
            self._on_failure()
            raise
    
    def _on_success(self):
        """Обработка успешного выполнения."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            # Если все запросы успешны, переходим в CLOSED
            if self.success_count >= self.half_open_max_calls:
                logger.info(f"Circuit breaker {self.name}: Recovery successful, transitioning to CLOSED")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_calls = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            # Сбрасываем счетчик сбоев при успехе
            if self.failure_count > 0:
                self.failure_count = max(0, self.failure_count - 1)
        
        self._update_metrics()
    
    def _on_failure(self):
        """Обработка сбоя."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.failures_counter.labels(component=self.name).inc()
        
        if self.state == CircuitState.HALF_OPEN:
            # В HALF_OPEN любой сбой возвращает в OPEN
            logger.warning(f"Circuit breaker {self.name}: Failure in HALF_OPEN, transitioning to OPEN")
            self.state = CircuitState.OPEN
            self.half_open_calls = 0
            self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            # Проверяем порог сбоев
            if self.failure_count >= self.failure_threshold:
                logger.error(
                    f"Circuit breaker {self.name}: Failure threshold reached ({self.failure_count}), "
                    f"transitioning to OPEN"
                )
                self.state = CircuitState.OPEN
        
        self._update_metrics()
    
    def _update_metrics(self):
        """Обновить метрики Prometheus."""
        state_value = {
            CircuitState.CLOSED: 0,
            CircuitState.OPEN: 1,
            CircuitState.HALF_OPEN: 2
        }[self.state]
        self.state_gauge.labels(component=self.name).set(state_value)
    
    def reset(self):
        """Принудительный сброс Circuit Breaker."""
        logger.info(f"Circuit breaker {self.name}: Manual reset")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0
        self._update_metrics()
    
    def get_state(self) -> CircuitState:
        """Получить текущее состояние."""
        return self.state
    
    def is_open(self) -> bool:
        """Проверить, открыт ли Circuit Breaker."""
        return self.state == CircuitState.OPEN


