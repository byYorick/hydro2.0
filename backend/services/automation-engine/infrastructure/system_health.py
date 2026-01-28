"""
System Health Monitor - мониторинг здоровья всех компонентов системы.
"""
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime
from common.utils.time import utcnow
from common.db import fetch
from common.mqtt import MqttClient
from prometheus_client import Gauge
from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

# Метрики здоровья системы
SYSTEM_HEALTH_STATUS = Gauge(
    "system_health_status",
    "Overall system health status (0=healthy, 1=degraded, 2=critical)",
    ["component"]
)

COMPONENT_HEALTH_LATENCY = Gauge(
    "component_health_latency_ms",
    "Component health check latency in milliseconds",
    ["component"]
)


class SystemHealthMonitor:
    """Мониторинг здоровья системы."""
    
    def __init__(
        self,
        mqtt: MqttClient,
        db_circuit_breaker: Optional[CircuitBreaker] = None,
        api_circuit_breaker: Optional[CircuitBreaker] = None,
        mqtt_circuit_breaker: Optional[CircuitBreaker] = None
    ):
        """
        Инициализация монитора здоровья.
        
        Args:
            mqtt: MQTT клиент
            db_circuit_breaker: Circuit Breaker для БД
            api_circuit_breaker: Circuit Breaker для API
            mqtt_circuit_breaker: Circuit Breaker для MQTT
        """
        self.mqtt = mqtt
        self.db_circuit_breaker = db_circuit_breaker
        self.api_circuit_breaker = api_circuit_breaker
        self.mqtt_circuit_breaker = mqtt_circuit_breaker
    
    async def check_health(self) -> Dict[str, Any]:
        """
        Проверка здоровья всех компонентов.
        
        Returns:
            Dict с информацией о здоровье системы
        """
        health = {
            'status': 'healthy',
            'timestamp': utcnow().isoformat(),
            'components': {}
        }
        
        # Проверка БД
        db_health = await self._check_database()
        health['components']['database'] = db_health
        
        # Проверка MQTT
        mqtt_health = await self._check_mqtt()
        health['components']['mqtt'] = mqtt_health
        
        # Проверка Circuit Breakers
        if self.db_circuit_breaker:
            health['components']['database_circuit_breaker'] = {
                'status': 'healthy' if self.db_circuit_breaker.state.value == 'closed' else 'degraded',
                'state': self.db_circuit_breaker.state.value,
                'failure_count': self.db_circuit_breaker.failure_count
            }
        
        if self.api_circuit_breaker:
            health['components']['api_circuit_breaker'] = {
                'status': 'healthy' if self.api_circuit_breaker.state.value == 'closed' else 'degraded',
                'state': self.api_circuit_breaker.state.value,
                'failure_count': self.api_circuit_breaker.failure_count
            }
        
        if self.mqtt_circuit_breaker:
            health['components']['mqtt_circuit_breaker'] = {
                'status': 'healthy' if self.mqtt_circuit_breaker.state.value == 'closed' else 'degraded',
                'state': self.mqtt_circuit_breaker.state.value,
                'failure_count': self.mqtt_circuit_breaker.failure_count
            }
        
        # Определяем общий статус
        component_statuses = [c.get('status', 'unknown') for c in health['components'].values()]
        
        if 'critical' in component_statuses:
            health['status'] = 'critical'
        elif 'degraded' in component_statuses or 'unhealthy' in component_statuses:
            health['status'] = 'degraded'
        else:
            health['status'] = 'healthy'
        
        # Обновляем метрики
        status_value = {'healthy': 0, 'degraded': 1, 'critical': 2}.get(health['status'], 1)
        SYSTEM_HEALTH_STATUS.labels(component='overall').set(status_value)
        
        return health
    
    async def _check_database(self) -> Dict[str, Any]:
        """Проверка доступности БД."""
        try:
            start = time.time()
            rows = await fetch("SELECT 1 as test")
            latency_ms = (time.time() - start) * 1000
            
            if rows and len(rows) > 0:
                status = 'healthy'
            else:
                status = 'degraded'
            
            COMPONENT_HEALTH_LATENCY.labels(component='database').set(latency_ms)
            
            return {
                'status': status,
                'latency_ms': round(latency_ms, 2),
                'last_check': utcnow().isoformat()
            }
        except Exception as e:
            logger.warning(f"Database health check failed: {e}", exc_info=True)
            COMPONENT_HEALTH_LATENCY.labels(component='database').set(-1)
            
            return {
                'status': 'critical',
                'error': str(e),
                'last_check': utcnow().isoformat()
            }
    
    async def _check_mqtt(self) -> Dict[str, Any]:
        """Проверка MQTT соединения."""
        try:
            is_connected = self.mqtt.is_connected()
            
            status = 'healthy' if is_connected else 'critical'
            
            return {
                'status': status,
                'connected': is_connected,
                'last_check': utcnow().isoformat()
            }
        except Exception as e:
            logger.warning(f"MQTT health check failed: {e}", exc_info=True)
            return {
                'status': 'critical',
                'error': str(e),
                'last_check': utcnow().isoformat()
            }
    
    async def check_laravel_api(self, base_url: str, token: str) -> Dict[str, Any]:
        """
        Проверка доступности Laravel API.
        
        Args:
            base_url: URL API
            token: Токен авторизации
        
        Returns:
            Dict с информацией о здоровье API
        """
        try:
            import httpx
            start = time.time()
            
            async with httpx.AsyncClient() as client:
                from common.trace_context import inject_trace_id_header
                headers = {"Authorization": f"Bearer {token}"} if token else {}
                headers = inject_trace_id_header(headers)
                response = await client.get(
                    f"{base_url}/api/system/health",
                    headers=headers,
                    timeout=5.0
                )
                latency_ms = (time.time() - start) * 1000
            
            if response.status_code == 200:
                status = 'healthy'
            elif response.status_code == 401:
                status = 'degraded'  # Проблема с авторизацией
            else:
                status = 'degraded'
            
            COMPONENT_HEALTH_LATENCY.labels(component='laravel_api').set(latency_ms)
            
            return {
                'status': status,
                'latency_ms': round(latency_ms, 2),
                'http_status': response.status_code,
                'last_check': utcnow().isoformat()
            }
        except Exception as e:
            logger.warning(f"Laravel API health check failed: {e}", exc_info=True)
            COMPONENT_HEALTH_LATENCY.labels(component='laravel_api').set(-1)
            
            return {
                'status': 'critical',
                'error': str(e),
                'last_check': utcnow().isoformat()
            }
