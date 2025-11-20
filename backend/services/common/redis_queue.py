"""
Redis queue для буферизации телеметрии перед записью в БД.
"""
import json
import logging
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, asdict
from pydantic import BaseModel

try:
    import redis.asyncio as redis_async
    HAS_ASYNC = True
except ImportError:
    import redis as redis_sync
    redis_async = None
    HAS_ASYNC = False

from .env import get_settings

logger = logging.getLogger(__name__)

# Глобальный Redis клиент
_redis_client = None


@dataclass
class TelemetryQueueItem:
    """Элемент очереди телеметрии."""
    node_uid: str
    zone_uid: Optional[str] = None
    metric_type: str = ""
    value: float = 0.0
    ts: Optional[datetime] = None
    raw: Optional[dict] = None
    channel: Optional[str] = None
    
    def dict(self) -> dict:
        """Преобразовать в словарь для сериализации."""
        data = asdict(self)
        # Преобразуем datetime в ISO строку
        if data.get("ts") and isinstance(data["ts"], datetime):
            data["ts"] = data["ts"].isoformat()
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
            return cls(**obj)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to deserialize TelemetryQueueItem: {e}")
            return None


class TelemetryQueue:
    """Очередь телеметрии в Redis для буферизации перед записью в БД."""
    
    QUEUE_KEY = "hydro:telemetry:queue"
    MAX_QUEUE_SIZE = 10000  # Максимальный размер очереди
    
    def __init__(self):
        self._client: Optional[redis.Redis] = None
    
    async def _ensure_client(self):
        """Убедиться, что Redis клиент инициализирован."""
        if self._client is None:
            self._client = await get_redis_client()
    
    async def push(self, item: TelemetryQueueItem) -> bool:
        """
        Добавить элемент в очередь.
        
        Returns:
            True если успешно, False если очередь переполнена или ошибка
        """
        try:
            await self._ensure_client()
            
            # Проверяем размер очереди
            size = await self._client.llen(self.QUEUE_KEY)
            if size >= self.MAX_QUEUE_SIZE:
                logger.warning(f"Telemetry queue is full ({size} items), dropping message")
                return False
            
            # Добавляем в очередь
            await self._client.rpush(self.QUEUE_KEY, item.to_json())
            return True
            
        except Exception as e:
            logger.error(f"Failed to push to telemetry queue: {e}", exc_info=True)
            return False
    
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
        Redis клиент
    """
    global _redis_client
    
    if _redis_client is None:
        s = get_settings()
        
        # Используем redis.asyncio если доступен, иначе обычный redis
        if HAS_ASYNC:
            _redis_client = redis_async.Redis(
                host=s.redis_host if hasattr(s, 'redis_host') else 'redis',
                port=s.redis_port if hasattr(s, 'redis_port') else 6379,
                db=0,
                decode_responses=False,  # Работаем с bytes для JSON
            )
        else:
            # Fallback на синхронный redis (не рекомендуется для production)
            logger.warning("Using synchronous redis client (redis.asyncio not available)")
            _redis_client = redis_sync.Redis(
                host=s.redis_host if hasattr(s, 'redis_host') else 'redis',
                port=s.redis_port if hasattr(s, 'redis_port') else 6379,
                db=0,
                decode_responses=False,
            )
        
        # Проверяем подключение
        try:
            if HAS_ASYNC:
                await _redis_client.ping()
            else:
                _redis_client.ping()
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
            if hasattr(_redis_client, 'close'):
                await _redis_client.close()
            else:
                _redis_client.close()
        except Exception as e:
            logger.error(f"Error closing Redis client: {e}")
        finally:
            _redis_client = None

