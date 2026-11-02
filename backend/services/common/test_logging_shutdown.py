"""Late asyncio finalizers must not restart logging threads during shutdown."""
import logging
from unittest.mock import Mock

from common import logging_setup, service_logs


def test_asyncio_finalizer_uses_default_stderr_handler(monkeypatch):
    monkeypatch.setattr(logging_setup.sys, 'is_finalizing', lambda: True)
    forward = Mock()
    monkeypatch.setattr(logging_setup, 'send_service_log', forward)
    logger = Mock(spec=logging.Logger)
    loop = Mock()
    context = {'message': 'Task was destroyed but it is pending!'}
    logging_setup._build_asyncio_exception_handler('test', logger, True)(loop, context)
    loop.default_exception_handler.assert_called_once_with(context)
    logger.error.assert_not_called()
    forward.assert_not_called()


def test_forwarding_does_not_start_threads_at_interpreter_shutdown(monkeypatch):
    monkeypatch.setattr(service_logs.sys, 'is_finalizing', lambda: True)
    thread = Mock()
    monkeypatch.setattr(service_logs.threading, 'Thread', thread)
    service_logs.send_service_log('test', 'error', 'late finalizer')
    thread.assert_not_called()
