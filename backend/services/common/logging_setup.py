"""
Единая настройка логирования и обработчиков необработанных ошибок для Python-сервисов.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from common.service_logs import send_service_log
from common.trace_context import get_trace_id


class ServiceContextFilter(logging.Filter):
    """Добавляет имя сервиса в запись лога, если его нет."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "service"):
            record.service = self._service_name
        return True


def get_log_level(env_var: str = "LOG_LEVEL", default_level: str = "INFO") -> int:
    """Получить уровень логирования из переменных окружения."""
    log_level = os.getenv(env_var, default_level).upper()
    return getattr(logging, log_level, logging.INFO)


def get_log_format(env_var: str = "LOG_FORMAT", default_format: str = "text") -> str:
    """
    Получить формат логов из переменных окружения.
    Поддерживаемые значения: text | json (structured).
    """
    raw_value = os.getenv(env_var, default_format).strip().lower()
    if raw_value in ("json", "structured"):
        return "json"
    return "text"


class JsonFormatter(logging.Formatter):
    """Форматтер для логов в JSON."""

    _standard_fields = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if hasattr(record, "service"):
            data["service"] = record.service
        trace_id = get_trace_id()
        if trace_id:
            data["trace_id"] = trace_id

        # Доп. поля (extra)
        for key, value in record.__dict__.items():
            if key in self._standard_fields or key.startswith("_"):
                continue
            if key in data:
                continue
            data[key] = value

        if record.exc_info:
            import traceback
            data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(data, ensure_ascii=False, default=str)


def setup_standard_logging(
    service_name: str,
    *,
    env_var: str = "LOG_LEVEL",
    default_level: str = "INFO",
) -> int:
    """
    Настроить базовое логирование (stdout) и добавить контекст сервиса.
    Возвращает числовое значение уровня логирования.
    """
    level_value = get_log_level(env_var=env_var, default_level=default_level)
    log_format = get_log_format()
    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logging.basicConfig(level=level_value, handlers=[handler], force=True)
    attach_service_context(service_name)
    return level_value


def attach_service_context(service_name: str) -> None:
    """Добавить фильтр с именем сервиса в корневой логгер."""
    logging.getLogger().addFilter(ServiceContextFilter(service_name))


def _build_asyncio_exception_handler(
    service_name: str,
    logger: logging.Logger,
    forward_to_service_logs: bool,
) -> Any:
    def _handler(loop: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
        message = context.get("message") or "Необработанное исключение в asyncio"
        exception = context.get("exception")
        context_payload = {k: v for k, v in context.items() if k != "exception"}
        extra = {"source": "asyncio", "asyncio_context": context_payload}

        if exception:
            logger.error(
                message,
                exc_info=(type(exception), exception, exception.__traceback__),
                extra=extra,
            )
        else:
            logger.error(message, extra=extra)

        if forward_to_service_logs:
            try:
                send_service_log(
                    service=service_name,
                    level="error",
                    message=message,
                    context={
                        "source": "asyncio",
                        "exception_type": type(exception).__name__ if exception else None,
                        "exception_message": str(exception) if exception else None,
                        "asyncio_context": context_payload,
                    },
                )
            except Exception:
                logger.debug("Не удалось отправить asyncio-ошибку в service logs", exc_info=True)

    return _handler


class _LoggingEventLoopPolicy(asyncio.AbstractEventLoopPolicy):
    """Прокси-политика, которая настраивает обработчик ошибок для новых loop."""

    def __init__(self, base_policy: asyncio.AbstractEventLoopPolicy, handler: Any) -> None:
        self._base_policy = base_policy
        self._handler = handler
        self._hydro_logging_wrapped = True

    def get_event_loop(self) -> asyncio.AbstractEventLoop:
        return self._base_policy.get_event_loop()

    def set_event_loop(self, loop: Optional[asyncio.AbstractEventLoop]) -> None:
        self._base_policy.set_event_loop(loop)

    def new_event_loop(self) -> asyncio.AbstractEventLoop:
        loop = self._base_policy.new_event_loop()
        loop.set_exception_handler(self._handler)
        return loop

    def get_child_watcher(self) -> Optional[Any]:
        if hasattr(self._base_policy, "get_child_watcher"):
            return self._base_policy.get_child_watcher()
        return None

    def set_child_watcher(self, watcher: Any) -> None:
        if hasattr(self._base_policy, "set_child_watcher"):
            self._base_policy.set_child_watcher(watcher)


def install_asyncio_exception_handler(
    service_name: str,
    logger: Optional[logging.Logger] = None,
    *,
    forward_to_service_logs: bool = True,
) -> None:
    """Установить обработчик необработанных исключений asyncio."""
    logger = logger or logging.getLogger("system")
    handler = _build_asyncio_exception_handler(service_name, logger, forward_to_service_logs)

    try:
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(handler)
    except RuntimeError:
        # Нет запущенного цикла — пробуем получить текущий loop
        try:
            loop = asyncio.get_event_loop()
            loop.set_exception_handler(handler)
        except RuntimeError:
            pass

    policy = asyncio.get_event_loop_policy()
    if not getattr(policy, "_hydro_logging_wrapped", False):
        asyncio.set_event_loop_policy(_LoggingEventLoopPolicy(policy, handler))


def _format_exception_for_context(exc: BaseException) -> Dict[str, Any]:
    return {
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
    }


def _build_exc_info(
    exc_type: Optional[type], exc: Optional[BaseException], tb: Optional[Any]
) -> Tuple[Optional[type], Optional[BaseException], Optional[Any]]:
    return exc_type, exc, tb


def install_exception_handlers(
    service_name: str,
    logger: Optional[logging.Logger] = None,
    *,
    forward_to_service_logs: bool = True,
) -> None:
    """
    Установить верхнеуровневые обработчики необработанных исключений
    (main thread, threading, asyncio).
    """
    logger = logger or logging.getLogger("system")

    def _report_unhandled(
        message: str,
        exc_info: Tuple[Optional[type], Optional[BaseException], Optional[Any]],
        source: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        logger.critical(message, exc_info=exc_info, extra={**(extra or {}), "source": source})
        if forward_to_service_logs:
            exc = exc_info[1]
            context = {"source": source}
            if exc:
                context.update(_format_exception_for_context(exc))
            if extra:
                context.update(extra)
            try:
                send_service_log(
                    service=service_name,
                    level="critical",
                    message=message,
                    context=context,
                )
            except Exception:
                logger.debug("Не удалось отправить критическую ошибку в service logs", exc_info=True)

    def _sys_excepthook(exc_type, exc, tb) -> None:
        if exc_type is KeyboardInterrupt:
            sys.__excepthook__(exc_type, exc, tb)
            return
        _report_unhandled(
            "Необработанное исключение в главном потоке",
            _build_exc_info(exc_type, exc, tb),
            "sys.excepthook",
        )

    sys.excepthook = _sys_excepthook

    if hasattr(threading, "excepthook"):
        def _threading_excepthook(args) -> None:
            _report_unhandled(
                "Необработанное исключение в потоке",
                _build_exc_info(args.exc_type, args.exc_value, args.exc_traceback),
                "threading.excepthook",
                extra={"thread": getattr(args.thread, "name", "unknown")},
            )

        threading.excepthook = _threading_excepthook

    install_asyncio_exception_handler(
        service_name,
        logger=logger,
        forward_to_service_logs=forward_to_service_logs,
    )
