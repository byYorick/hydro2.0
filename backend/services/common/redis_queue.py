"""
Redis queue для буферизации телеметрии перед записью в БД.
"""
import json
import logging
import random
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, asdict
from pydantic import BaseModel

try:
    from prometheus_client import Counter, Gauge
    QUEUE_SIZE = Gauge("telemetry_queue_size", "Current size of telemetry queue")
    QUEUE_DROPPED = Counter("telemetry_queue_dropped_total", "Dropped messages due to queue overflow")
    QUEUE_OVERFLOW_ALERTS = Counter("telemetry_queue_overflow_alerts_total", "Number of overflow alerts sent")
except ImportError:
    # Prometheus не установлен - создаем заглушки
    class _Counter:
        def inc(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
    class _Gauge:
        def set(self, *args, **kwargs): pass
    QUEUE_SIZE = _Gauge()
    QUEUE_DROPPED = _Counter()
    QUEUE_OVERFLOW_ALERTS = _Counter()

try:
    import redis.asyncio as redis_async
except ImportError:
    # redis[asyncio] обязателен для работы сервиса
    raise ImportError(
        "redis.asyncio is required. Please install redis with asyncio support: "
        "pip install 'redis[asyncio]' or add 'redis[asyncio]' to requirements.txt"
    )

from .env import get_settings

logger = logging.getLogger(__name__)

# Глобальный Redis клиент
_redis_client = None


@dataclass
class TelemetryQueueItem:
    """Элемент очереди телеметрии."""
    node_uid: str
    zone_uid: Optional[str] = None
    gh_uid: Optional[str] = None  # Greenhouse UID для корректного резолва зоны в многотепличной конфигурации
    metric_type: str = ""
    value: float = 0.0
    ts: Optional[datetime] = None
    raw: Optional[dict] = None
    channel: Optional[str] = None
    enqueued_at: Optional[datetime] = None  # Время добавления в очередь для трекинга возраста
    
    def dict(self) -> dict:
        """Преобразовать в словарь для сериализации."""
        data = asdict(self)
        # Преобразуем datetime в ISO строку
        if data.get("ts") and isinstance(data["ts"], datetime):
            data["ts"] = data["ts"].isoformat()
        if data.get("enqueued_at") and isinstance(data["enqueued_at"], datetime):
            data["enqueued_at"] = data["enqueued_at"].isoformat()
        return data
    
    def to_json(self) -> bytes:
        """Сериализовать в JSON bytes."""
        return json.dumps(self.dict(), default=str).encode('utf-8')
    
    @classmethod
    def from_json(cls, data: bytes) -> Optional['TelemetryQueueItem']:
        """Десериализовать из JSON bytes."""
        try:
            obj = json.loads(data.decode('utf-8'))
            # Преобразуем ISO строку обратно в datetime
            if obj.get("ts"):
                try:
                    obj["ts"] = datetime.fromisoformat(obj["ts"].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    obj["ts"] = None
            if obj.get("enqueued_at"):
                try:
                    obj["enqueued_at"] = datetime.fromisoformat(obj["enqueued_at"].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    obj["enqueued_at"] = None
            return cls(**obj)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to deserialize TelemetryQueueItem: {e}")
            return None


class TelemetryQueue:
    """Очередь телеметрии в Redis для буферизации перед записью в БД."""
    
    QUEUE_KEY = "hydro:telemetry:queue"
    MAX_QUEUE_SIZE = 10000  # Максимальный размер очереди
    
    def __init__(self):
        self._client: Optional[redis_async.Redis] = None
    
    async def _ensure_client(self):
        """Убедиться, что Redis клиент инициализирован."""
        if self._client is None:
            self._client = await get_redis_client()
    
    async def push(self, item: TelemetryQueueItem) -> bool:
        """
        Добавить элемент в очередь с мониторингом и backpressure.
        
        Returns:
            True если успешно, False если очередь переполнена или ошибка
        """
        try:
            await self._ensure_client()
            
            # Проверяем размер очереди
            size = await self._client.llen(self.QUEUE_KEY)
            QUEUE_SIZE.set(size)
            
            # Backpressure: применяем sampling при >90% заполнения
            utilization = size / self.MAX_QUEUE_SIZE if self.MAX_QUEUE_SIZE > 0 else 0.0
            if utilization > 0.9:
                # Пропускаем 50% сообщений при 90-95% заполнении
                # Пропускаем 80% сообщений при >95% заполнении
                sample_rate = 0.5 if utilization < 0.95 else 0.2
                if random.random() > sample_rate:
                    QUEUE_DROPPED.labels(reason="backpressure").inc()
                    logger.warning(
                        f"Dropping telemetry due to backpressure (queue {utilization:.1%} full)",
                        extra={'queue_utilization': utilization, 'queue_size': size}
                    )
                    return False
            
            # Защита от переполнения
            if size >= self.MAX_QUEUE_SIZE:
                QUEUE_DROPPED.labels(reason="overflow").inc()
                
                # Отправляем алерт при критическом переполнении (>95%)
                if size >= self.MAX_QUEUE_SIZE * 0.95:
                    await self._send_overflow_alert(size)
                
                logger.warning(
                    f"Telemetry queue is full ({size} items), dropping message",
                    extra={
                        'queue_size': size,
                        'max_size': self.MAX_QUEUE_SIZE,
                        'utilization': f"{utilization:.1%}"
                    }
                )
                return False
            
            # Добавляем в очередь
            item.enqueued_at = datetime.utcnow()  # Устанавливаем время добавления
            await self._client.rpush(self.QUEUE_KEY, item.to_json())
            return True
            
        except Exception as e:
            logger.error(f"Failed to push to telemetry queue: {e}", exc_info=True)
            return False
    
    async def _send_overflow_alert(self, current_size: int):
        """Отправить алерт о переполнении очереди."""
        try:
            await self._ensure_client()
            
            # Throttling: не отправляем чаще 1 раза в минуту
            throttle_key = "alert_throttle:queue_overflow"
            if await self._client.exists(throttle_key):
                return
            
            await self._client.setex(throttle_key, 60, "1")  # 60 секунд
            
            QUEUE_OVERFLOW_ALERTS.inc()
            
            logger.error(
                f"CRITICAL: Telemetry queue overflow! Size: {current_size}/{self.MAX_QUEUE_SIZE}",
                extra={
                    'queue_size': current_size,
                    'max_size': self.MAX_QUEUE_SIZE,
                    'utilization': f"{current_size/self.MAX_QUEUE_SIZE:.1%}"
                }
            )
            
            # Отправляем в систему алертов (если доступна)
            try:
                from common.db import create_zone_event
                await create_zone_event(
                    zone_id=None,  # Системный алерт
                    event_type='system_queue_overflow',
                    details={
                        'queue_size': current_size,
                        'max_size': self.MAX_QUEUE_SIZE,
                        'severity': 'critical'
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to create zone event for queue overflow: {e}")
        except Exception as e:
            logger.error(f"Failed to send overflow alert: {e}", exc_info=True)
    
    async def pop_batch(self, batch_size: int) -> List[TelemetryQueueItem]:
        """
        Извлечь батч элементов из очереди.
        
        Args:
            batch_size: Максимальное количество элементов для извлечения
            
        Returns:
            Список TelemetryQueueItem
        """
        try:
            await self._ensure_client()
            
            # Проверяем размер очереди
            queue_size = await self._client.llen(self.QUEUE_KEY)
            if queue_size == 0:
                return []
            
            # Извлекаем батч через pipeline для атомарности
            actual_batch_size = min(batch_size, queue_size)
            pipeline = self._client.pipeline()
            
            for _ in range(actual_batch_size):
                pipeline.lpop(self.QUEUE_KEY)
            
            results = await pipeline.execute()
            
            # Десериализуем результаты
            items = []
            for result in results:
                if result is None:
                    continue
                item = TelemetryQueueItem.from_json(result)
                if item:
                    items.append(item)
            
            return items
            
        except Exception as e:
            logger.error(f"Failed to pop batch from telemetry queue: {e}", exc_info=True)
            return []
    
    async def size(self) -> int:
        """Получить текущий размер очереди."""
        try:
            await self._ensure_client()
            return await self._client.llen(self.QUEUE_KEY)
        except Exception as e:
            logger.error(f"Failed to get queue size: {e}", exc_info=True)
            return 0
    
    async def get_oldest_age_seconds(self) -> Optional[float]:
        """
        Получить возраст самого старого элемента в очереди в секундах.
        
        Returns:
            Возраст в секундах или None если очередь пуста или элемент не имеет enqueued_at
        """
        try:
            await self._ensure_client()
            
            # Читаем первый элемент очереди без удаления (LINDEX 0)
            oldest_item_data = await self._client.lindex(self.QUEUE_KEY, 0)
            if not oldest_item_data:
                return None
            
            # Десериализуем элемент
            oldest_item = TelemetryQueueItem.from_json(oldest_item_data)
            if not oldest_item or not oldest_item.enqueued_at:
                return None
            
            # Вычисляем возраст
            age = (datetime.utcnow() - oldest_item.enqueued_at).total_seconds()
            return max(0.0, age)  # Не возвращаем отрицательные значения
            
        except Exception as e:
            logger.error(f"Failed to get queue oldest age: {e}", exc_info=True)
            return None
    
    async def clear(self):
        """Очистить очередь."""
        try:
            await self._ensure_client()
            await self._client.delete(self.QUEUE_KEY)
            logger.info("Telemetry queue cleared")
        except Exception as e:
            logger.error(f"Failed to clear telemetry queue: {e}", exc_info=True)


async def get_redis_client():
    """
    Получить глобальный Redis клиент (singleton).
    
    Returns:
        Redis async клиент (redis.asyncio.Redis)
    """
    global _redis_client
    
    if _redis_client is None:
        s = get_settings()
        
        # Используем redis.asyncio (обязательно для async сервиса)
        _redis_client = redis_async.Redis(
            host=s.redis_host if hasattr(s, 'redis_host') else 'redis',
            port=s.redis_port if hasattr(s, 'redis_port') else 6379,
            db=0,
            decode_responses=False,  # Работаем с bytes для JSON
        )
        
        # Проверяем подключение
        try:
            await _redis_client.ping()
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            _redis_client = None
            raise
    
    return _redis_client


async def close_redis_client():
    """Закрыть глобальный Redis клиент."""
    global _redis_client
    
    if _redis_client is not None:
        try:
            await _redis_client.aclose()  # redis.asyncio использует aclose()
        except Exception as e:
            logger.error(f"Error closing Redis client: {e}")
        finally:
            _redis_client = None

