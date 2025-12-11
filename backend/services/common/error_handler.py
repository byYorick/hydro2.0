"""
Общий компонент для обработки ошибок от ESP32 нод.

Обрабатывает:
- Diagnostics сообщения (периодические метрики ошибок)
- Error сообщения (немедленные ошибки)
- Интеграция с Laravel API для создания Alerts
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
import httpx
import json
from .db import execute, fetch
from .env import get_settings

logger = logging.getLogger(__name__)


class NodeErrorHandler:
    """Обработчик ошибок от ESP32 нод."""
    
    def __init__(self):
        self.settings = get_settings()
        self.laravel_url = self.settings.laravel_api_url if hasattr(self.settings, 'laravel_api_url') else None
        self.ingest_token = (
            self.settings.history_logger_api_token 
            if hasattr(self.settings, 'history_logger_api_token') and self.settings.history_logger_api_token
            else (self.settings.ingest_token if hasattr(self.settings, 'ingest_token') else None)
        )
    
    async def handle_diagnostics(self, node_uid: str, diagnostics_data: Dict[str, Any]) -> None:
        """
        Обработка diagnostics сообщения от узла.
        
        Args:
            node_uid: UID узла
            diagnostics_data: Данные диагностики (JSON payload)
        """
        try:
            errors = diagnostics_data.get("errors", {})
            if not errors:
                return
            
            # Обновляем метрики ошибок в БД
            await execute(
                """
                UPDATE nodes 
                SET 
                    error_count = COALESCE($2, error_count),
                    warning_count = COALESCE($3, warning_count),
                    critical_count = COALESCE($4, critical_count),
                    updated_at = NOW()
                WHERE uid = $1
                """,
                node_uid,
                errors.get("error_count"),
                errors.get("warning_count"),
                errors.get("critical_count")
            )
            
            logger.debug(
                f"[DIAGNOSTICS] Updated error metrics for node {node_uid}: "
                f"errors={errors.get('error_count')}, "
                f"warnings={errors.get('warning_count')}, "
                f"critical={errors.get('critical_count')}"
            )
            
            # Если есть критические ошибки, создаем Alert
            if errors.get("critical_count", 0) > 0:
                await self._create_alert(
                    node_uid=node_uid,
                    level="critical",
                    component="system",
                    error_code="critical_errors_detected",
                    message=f"Node has {errors.get('critical_count')} critical errors",
                    details=errors
                )
        
        except Exception as e:
            logger.error(
                f"[DIAGNOSTICS] Failed to process diagnostics for node {node_uid}: {e}",
                exc_info=True
            )
    
    async def handle_error(self, node_uid: str, error_data: Dict[str, Any]) -> None:
        """
        Обработка error сообщения от узла.
        
        Args:
            node_uid: UID узла
            error_data: Данные ошибки (JSON payload)
        """
        try:
            level = error_data.get("level", "ERROR").upper()
            component = error_data.get("component", "unknown")
            error_code = error_data.get("error_code", "unknown")
            message = error_data.get("message", "Unknown error")
            
            # Обновляем счетчик ошибок в БД
            if level == "CRITICAL":
                await execute(
                    "UPDATE nodes SET critical_count = COALESCE(critical_count, 0) + 1, updated_at = NOW() WHERE uid = $1",
                    node_uid
                )
            elif level == "ERROR":
                await execute(
                    "UPDATE nodes SET error_count = COALESCE(error_count, 0) + 1, updated_at = NOW() WHERE uid = $1",
                    node_uid
                )
            elif level == "WARNING":
                await execute(
                    "UPDATE nodes SET warning_count = COALESCE(warning_count, 0) + 1, updated_at = NOW() WHERE uid = $1",
                    node_uid
                )
            
            logger.info(
                f"[ERROR] Node {node_uid} error: level={level}, component={component}, "
                f"error_code={error_code}, message={message}"
            )
            
            # Создаем Alert через Laravel API
            await self._create_alert(
                node_uid=node_uid,
                level=level.lower(),
                component=component,
                error_code=error_code,
                message=message,
                details=error_data
            )
        
        except Exception as e:
            logger.error(
                f"[ERROR] Failed to process error for node {node_uid}: {e}",
                exc_info=True
            )
    
    async def _create_alert(
        self,
        node_uid: str,
        level: str,
        component: str,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Создание Alert напрямую в БД (Laravel API не поддерживает POST для alerts).
        
        Args:
            node_uid: UID узла
            level: Уровень ошибки (warning, error, critical)
            component: Компонент, где произошла ошибка
            error_code: Код ошибки
            message: Сообщение об ошибке
            details: Дополнительные детали
        """
        try:
            # Получаем node_id и zone_id из БД
            node_rows = await fetch(
                """
                SELECT n.id, n.zone_id, z.id as zone_id_check
                FROM nodes n
                LEFT JOIN zones z ON z.id = n.zone_id
                WHERE n.uid = $1
                """,
                node_uid
            )
            
            if not node_rows:
                logger.warning(f"[ERROR_HANDLER] Node {node_uid} not found in database, cannot create alert")
                return
            
            node_row = node_rows[0]
            zone_id = node_row.get('zone_id')
            
            if not zone_id:
                logger.warning(f"[ERROR_HANDLER] Node {node_uid} has no zone_id, cannot create alert")
                return
            
            # Структура alerts: zone_id, source, code, type, details, status
            # source: 'biz' или 'infra' (для ошибок нод используем 'infra')
            # code: код ошибки (например, 'node_error_ph_sensor')
            # type: тип алерта (например, 'node_error')
            # details: JSON с деталями
            
            alert_code = f"node_error_{component}_{error_code}"
            alert_type = "node_error"
            
            # Создаем Alert напрямую в БД
            await execute(
                """
                INSERT INTO alerts (
                    zone_id, source, code, type, status, details, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                """,
                zone_id,
                "infra",  # Ошибки нод - это инфраструктурные ошибки
                alert_code,
                alert_type,
                "ACTIVE",
                json.dumps({
                    "node_uid": node_uid,
                    "component": component,
                    "error_code": error_code,
                    "level": level,
                    "message": message,
                    "details": details or {}
                })
            )
            
            logger.info(f"[ERROR_HANDLER] Alert created for node {node_uid}: {error_code}")
        
        except Exception as e:
            logger.error(
                f"[ERROR_HANDLER] Exception while creating alert for node {node_uid}: {e}",
                exc_info=True
            )


# Глобальный экземпляр обработчика
_error_handler: Optional[NodeErrorHandler] = None


def get_error_handler() -> NodeErrorHandler:
    """Получить глобальный экземпляр обработчика ошибок."""
    global _error_handler
    if _error_handler is None:
        _error_handler = NodeErrorHandler()
    return _error_handler

