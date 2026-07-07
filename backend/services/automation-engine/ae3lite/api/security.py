"""Базовые security-проверки для ingress AE3-Lite."""

from __future__ import annotations

import logging
import secrets
from typing import Any, Callable, Optional

from ae3lite.api.http_errors import api_error_detail

_logger = logging.getLogger(__name__)


def validate_scheduler_security_baseline(
    *,
    headers: Any,
    enforce: bool,
    scheduler_api_token: str,
    require_trace_id: bool,
    extract_trace_id_from_headers_fn: Callable[[Any], Optional[str]],
) -> None:
    if not enforce:
        return

    expected_token = str(scheduler_api_token or "").strip()
    if not expected_token:
        _logger.error("AE3 security: scheduler_api_token не настроен, запрос отклонён с 500")
        raise api_error_detail("scheduler_security_token_not_configured", status_code=500)

    auth_header = str(headers.get("authorization") or "").strip()
    bearer_prefix = "Bearer "
    if not auth_header.startswith(bearer_prefix):
        _logger.warning("AE3 security: неавторизованный запрос отклонён (токен отсутствует или неверный)")
        raise api_error_detail("unauthorized", status_code=401)

    provided_token = auth_header[len(bearer_prefix) :]
    if len(provided_token) != len(expected_token) or not secrets.compare_digest(
        provided_token, expected_token
    ):
        _logger.warning("AE3 security: неавторизованный запрос отклонён (токен отсутствует или неверный)")
        raise api_error_detail("unauthorized", status_code=401)

    if require_trace_id:
        trace_id = extract_trace_id_from_headers_fn(headers)
        if not trace_id:
            _logger.warning("AE3 security: запрос отклонён, отсутствует заголовок X-Trace-Id")
            raise api_error_detail("missing_trace_id", status_code=422)


__all__ = ["validate_scheduler_security_baseline"]
