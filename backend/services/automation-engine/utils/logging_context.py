"""
Context для структурированного логирования с Trace ID.
Обеспечивает отслеживание запросов через весь стек вызовов.
"""
import contextvars
import uuid
import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime
from common.utils.time import utcnow

# Context variable для trace ID
trace_id_var = contextvars.ContextVar('trace_id', default=None)
zone_id_var = contextvars.ContextVar('zone_id', default=None)


def get_trace_id() -> str:
    """Получить или создать trace ID."""
    trace_id = trace_id_var.get()
    if trace_id is None:
        trace_id = str(uuid.uuid4())[:8]
        trace_id_var.set(trace_id)
    return trace_id


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """Установить trace ID (или создать новый)."""
    if trace_id is None:
        trace_id = str(uuid.uuid4())[:8]
    trace_id_var.set(trace_id)
    return trace_id


def get_zone_id() -> Optional[int]:
    """Получить zone_id из контекста."""
    return zone_id_var.get()


def set_zone_id(zone_id: Optional[int]) -> None:
    """Установить zone_id в контекст."""
    if zone_id is None:
        zone_id_var.set(None)
    else:
        zone_id_var.set(zone_id)


class StructuredFormatter(logging.Formatter):
    """Форматтер для структурированного логирования в JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Форматировать запись лога как JSON."""
        # Базовые поля
        log_data: Dict[str, Any] = {
            'timestamp': utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'trace_id': get_trace_id(),
        }
        
        # Zone ID из контекста или extra
        zone_id = get_zone_id() or getattr(record, 'zone_id', None)
        if zone_id:
            log_data['zone_id'] = zone_id
        
        # Добавляем все поля из extra
        if hasattr(record, 'extra'):
            log_data.update(record.extra)
        
        # Добавляем поля из record, которые не являются стандартными
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'msecs', 'message',
                          'pathname', 'process', 'processName', 'relativeCreated', 'thread',
                          'threadName', 'exc_info', 'exc_text', 'stack_info', 'extra']:
                if not key.startswith('_'):
                    log_data[key] = value
        
        # Добавляем exception если есть
        if record.exc_info:
            import traceback
            log_data['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Настроить структурированное логирование."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Удаляем существующие обработчики
    root_logger.handlers.clear()
    
    # Создаем новый обработчик с структурированным форматтером
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(handler)


class ZoneContextManager:
    """Context manager для установки zone_id в контекст."""
    
    def __init__(self, zone_id: int):
        self.zone_id = zone_id
        self.prev_zone_id = None
    
    def __enter__(self):
        self.prev_zone_id = get_zone_id()
        set_zone_id(self.zone_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        set_zone_id(self.prev_zone_id)


