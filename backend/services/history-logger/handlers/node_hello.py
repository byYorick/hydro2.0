"""``handle_node_hello``: регистрация ESP32-узла через Laravel ``/api/nodes/register``."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict

import httpx

from common.env import get_settings
from common.node_types import normalize_node_type
from common.trace_context import clear_trace_id, inject_trace_id_header
from metrics import NODE_HELLO_ERRORS, NODE_HELLO_RECEIVED, NODE_HELLO_REGISTERED
from utils import _parse_json

from ._shared import apply_trace_context, pop_pending_config_report

logger = logging.getLogger(__name__)


async def _process_pending_config_report_after_registration(hardware_id: str) -> None:
    """Если от ноды уже пришёл config_report до регистрации, реплеим его сейчас.

    Late import ``handle_config_report`` разрывает circular dependency между
    ``handlers.node_hello`` и ``handlers.config_report``.
    """
    pending = await pop_pending_config_report(hardware_id)
    if not pending:
        return

    logger.info(
        "[NODE_HELLO] Processing buffered config_report after registration: hardware_id=%s",
        hardware_id,
    )

    try:
        from .config_report import handle_config_report  # late import

        await handle_config_report(pending["topic"], pending["payload"])
    except Exception as e:
        logger.error(
            "[NODE_HELLO] Failed to process buffered config_report: hardware_id=%s, error=%s",
            hardware_id,
            e,
            exc_info=True,
        )


async def handle_node_hello(topic: str, payload: bytes) -> None:
    """Обработчик node_hello сообщений от узлов ESP32.
    Регистрирует новые узлы через Laravel API.
    """
    try:
        logger.info("[NODE_HELLO] ===== START processing node_hello =====")
        logger.info(f"[NODE_HELLO] Topic: {topic}, payload length: {len(payload)}")

        try:
            data = _parse_json(payload)
            if not data or not isinstance(data, dict):
                logger.warning(f"[NODE_HELLO] Invalid JSON in node_hello from topic {topic}")
                NODE_HELLO_ERRORS.labels(error_type="invalid_json").inc()
                return

            apply_trace_context(data)

            if data.get("message_type") != "node_hello":
                logger.debug(
                    "[NODE_HELLO] Not a node_hello message, skipping: %s",
                    data.get("message_type"),
                )
                return

            hardware_id = data.get("hardware_id")
            if not hardware_id:
                logger.warning("[NODE_HELLO] Missing hardware_id in node_hello message")
                NODE_HELLO_ERRORS.labels(error_type="missing_hardware_id").inc()
                return

            logger.info(f"[NODE_HELLO] Processing node_hello from hardware_id: {hardware_id}")
            logger.info(f"[NODE_HELLO] Full payload data: {data}")
            NODE_HELLO_RECEIVED.inc()
        except Exception as e:
            logger.error(f"[NODE_HELLO] Error parsing node_hello: {e}", exc_info=True)
            NODE_HELLO_ERRORS.labels(error_type="parse_error").inc()
            return

        s = get_settings()
        laravel_url = s.laravel_api_url if hasattr(s, "laravel_api_url") else None
        ingest_token = (
            s.history_logger_api_token
            if hasattr(s, "history_logger_api_token") and s.history_logger_api_token
            else (s.ingest_token if hasattr(s, "ingest_token") and s.ingest_token else None)
        )

        if not laravel_url:
            logger.error("[NODE_HELLO] Laravel API URL not configured, cannot register node")
            NODE_HELLO_ERRORS.labels(error_type="config_missing").inc()
            return

        app_env = os.getenv("APP_ENV", "").lower().strip()
        is_prod = app_env in ("production", "prod") and app_env != ""

        if is_prod and not ingest_token:
            logger.error(
                "[NODE_HELLO] Ingest token (PY_INGEST_TOKEN or HISTORY_LOGGER_API_TOKEN) must be set in production for node registration"
            )
            NODE_HELLO_ERRORS.labels(error_type="token_missing").inc()
            return

        try:
            await _register_via_api(
                hardware_id=hardware_id,
                data=data,
                laravel_url=laravel_url,
                ingest_token=ingest_token,
                is_prod=is_prod,
                api_timeout=s.laravel_api_timeout_sec,
            )
        except Exception as e:
            logger.error(
                "[NODE_HELLO] Unexpected error registering node: hardware_id=%s, error=%s",
                hardware_id,
                str(e),
                exc_info=True,
            )
            NODE_HELLO_ERRORS.labels(error_type="exception").inc()
    except Exception as e:
        logger.error(
            "[NODE_HELLO] Unexpected error processing node_hello: error=%s",
            str(e),
            exc_info=True,
        )
        NODE_HELLO_ERRORS.labels(error_type="exception").inc()
    finally:
        clear_trace_id()


async def _register_via_api(
    *,
    hardware_id: str,
    data: Dict[str, Any],
    laravel_url: str,
    ingest_token: str | None,
    is_prod: bool,
    api_timeout: float,
) -> None:
    raw_node_type = data.get("node_type")
    normalized_node_type = normalize_node_type(
        str(raw_node_type) if raw_node_type is not None else None
    )
    if (
        raw_node_type is not None
        and str(raw_node_type).strip()
        and normalized_node_type == "unknown"
        and str(raw_node_type).strip().lower() != "unknown"
    ):
        logger.warning(
            "[NODE_HELLO] Non-canonical node_type received, normalized to unknown: hardware_id=%s node_type=%s",
            hardware_id,
            raw_node_type,
        )

    api_data = {
        "message_type": "node_hello",
        "hardware_id": data.get("hardware_id"),
        "node_type": normalized_node_type,
        "fw_version": data.get("fw_version"),
        "hardware_revision": data.get("hardware_revision"),
        "capabilities": data.get("capabilities"),
        "provisioning_meta": data.get("provisioning_meta"),
    }

    headers = inject_trace_id_header(
        {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )

    if ingest_token:
        headers["Authorization"] = f"Bearer {ingest_token}"
    elif is_prod:
        logger.error("[NODE_HELLO] Cannot register node without ingest token in production")
        NODE_HELLO_ERRORS.labels(error_type="token_missing").inc()
        return
    else:
        logger.warning(
            "[NODE_HELLO] No ingest token configured, registering without auth (dev mode only)"
        )

    MAX_API_RETRIES = 3
    API_RETRY_BACKOFF_BASE = 2

    last_error = None
    for attempt in range(MAX_API_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=api_timeout) as client:
                response = await client.post(
                    f"{laravel_url}/api/nodes/register",
                    json=api_data,
                    headers=headers,
                )

            if response.status_code in (200, 201):
                response_data = response.json()
                node_uid = response_data.get("data", {}).get("uid", "unknown")
                action = "registered" if response.status_code == 201 else "updated"
                logger.info(
                    "[NODE_HELLO] Node %s successfully: hardware_id=%s, node_uid=%s, attempts=%s",
                    action,
                    hardware_id,
                    node_uid,
                    attempt + 1,
                )
                NODE_HELLO_REGISTERED.inc()
                await _process_pending_config_report_after_registration(hardware_id)
                return
            if response.status_code == 401:
                logger.error(
                    "[NODE_HELLO] Unauthorized: token required or invalid. hardware_id=%s, response=%s",
                    hardware_id,
                    response.text[:200],
                )
                NODE_HELLO_ERRORS.labels(error_type="unauthorized").inc()
                return
            if response.status_code >= 500:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                if attempt < MAX_API_RETRIES - 1:
                    backoff_seconds = API_RETRY_BACKOFF_BASE**attempt
                    logger.warning(
                        "[NODE_HELLO] Server error %s (attempt %s/%s), retrying in %ss: hardware_id=%s",
                        response.status_code,
                        attempt + 1,
                        MAX_API_RETRIES,
                        backoff_seconds,
                        hardware_id,
                    )
                    await asyncio.sleep(backoff_seconds)
                    continue
                logger.error(
                    "[NODE_HELLO] Failed to register node after %s attempts: status=%s, hardware_id=%s, response=%s",
                    MAX_API_RETRIES,
                    response.status_code,
                    hardware_id,
                    response.text[:500],
                )
                NODE_HELLO_ERRORS.labels(error_type=f"http_{response.status_code}").inc()
                return

            logger.error(
                "[NODE_HELLO] Failed to register node: status=%s, hardware_id=%s, response=%s",
                response.status_code,
                hardware_id,
                response.text[:500],
            )
            NODE_HELLO_ERRORS.labels(error_type=f"http_{response.status_code}").inc()
            return

        except httpx.TimeoutException as e:
            last_error = f"Timeout: {str(e)}"
            if attempt < MAX_API_RETRIES - 1:
                backoff_seconds = API_RETRY_BACKOFF_BASE**attempt
                logger.warning(
                    "[NODE_HELLO] Timeout (attempt %s/%s), retrying in %ss: hardware_id=%s",
                    attempt + 1,
                    MAX_API_RETRIES,
                    backoff_seconds,
                    hardware_id,
                )
                await asyncio.sleep(backoff_seconds)
            else:
                logger.error(
                    "[NODE_HELLO] Timeout while registering node after %s attempts: hardware_id=%s",
                    MAX_API_RETRIES,
                    hardware_id,
                )
                NODE_HELLO_ERRORS.labels(error_type="timeout").inc()
                return
        except httpx.RequestError as e:
            last_error = f"Request error: {str(e)}"
            if attempt < MAX_API_RETRIES - 1:
                backoff_seconds = API_RETRY_BACKOFF_BASE**attempt
                logger.warning(
                    "[NODE_HELLO] Request error (attempt %s/%s), retrying in %ss: hardware_id=%s, error=%s",
                    attempt + 1,
                    MAX_API_RETRIES,
                    backoff_seconds,
                    hardware_id,
                    str(e),
                )
                await asyncio.sleep(backoff_seconds)
            else:
                logger.error(
                    "[NODE_HELLO] Request error while registering node after %s attempts: hardware_id=%s, error=%s",
                    MAX_API_RETRIES,
                    hardware_id,
                    str(e),
                )
                NODE_HELLO_ERRORS.labels(error_type="request_error").inc()
                return

    if last_error:
        logger.error(
            "[NODE_HELLO] Failed to register node after %s attempts: hardware_id=%s, last_error=%s",
            MAX_API_RETRIES,
            hardware_id,
            last_error,
        )
        NODE_HELLO_ERRORS.labels(error_type="max_retries_exceeded").inc()
