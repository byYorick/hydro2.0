"""
Cache для часто используемых данных.
Снижает нагрузку на БД за счет кеширования.
"""
import asyncio
import logging
from typing import Dict, Any, Optional, Callable, Awaitable
from datetime import datetime, timedelta
from common.utils.time import utcnow
from functools import wraps

logger = logging.getLogger(__name__)

T = Any


class ZoneDataCache:
    """Кеш данных зон с TTL."""
    
    def __init__(self, ttl_seconds: int = 30):
        """
        Инициализация кеша.
        
        Args:
            ttl_seconds: Время жизни кеша в секундах
        """
        self.cache: Dict[int, Dict[str, Any]] = {}
        self.cache_timestamps: Dict[int, datetime] = {}
        self.ttl = timedelta(seconds=ttl_seconds)
    
    async def get_zone_data(
        self,
        zone_id: int,
        fetch_func: Callable[[int], Awaitable[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """
        Получить данные зоны из кеша или БД.
        
        Args:
            zone_id: ID зоны
            fetch_func: Функция для загрузки данных из БД
        
        Returns:
            Данные зоны
        """
        now = utcnow()
        
        # Проверяем кеш
        if zone_id in self.cache:
            cache_time = self.cache_timestamps[zone_id]
            if now - cache_time < self.ttl:
                logger.debug(f"Zone {zone_id}: Cache hit")
                return self.cache[zone_id]
            else:
                # Кеш устарел
                logger.debug(f"Zone {zone_id}: Cache expired")
        
        # Загружаем из БД
        try:
            data = await fetch_func(zone_id)
            
            # Сохраняем в кеш
            self.cache[zone_id] = data
            self.cache_timestamps[zone_id] = now
            
            logger.debug(f"Zone {zone_id}: Data cached")
            return data
        except Exception as e:
            logger.warning(f"Zone {zone_id}: Failed to fetch data: {e}", exc_info=True)
            # Возвращаем устаревшие данные из кеша, если есть
            if zone_id in self.cache:
                logger.warning(f"Zone {zone_id}: Using stale cache data")
                return self.cache[zone_id]
            raise
    
    def invalidate(self, zone_id: int):
        """Инвалидировать кеш зоны."""
        self.cache.pop(zone_id, None)
        self.cache_timestamps.pop(zone_id, None)
        logger.debug(f"Zone {zone_id}: Cache invalidated")
    
    def clear(self):
        """Очистить весь кеш."""
        self.cache.clear()
        self.cache_timestamps.clear()
        logger.debug("Cache cleared")


# Глобальные кеши
_capabilities_cache = ZoneDataCache(ttl_seconds=300)  # 5 минут
_nodes_cache = ZoneDataCache(ttl_seconds=120)  # 2 минуты
_recipe_config_cache = ZoneDataCache(ttl_seconds=600)  # 10 минут


def get_capabilities_cache() -> ZoneDataCache:
    """Получить кеш capabilities."""
    return _capabilities_cache


def get_nodes_cache() -> ZoneDataCache:
    """Получить кеш узлов."""
    return _nodes_cache


def get_recipe_config_cache() -> ZoneDataCache:
    """Получить кеш конфигурации рецептов."""
    return _recipe_config_cache


