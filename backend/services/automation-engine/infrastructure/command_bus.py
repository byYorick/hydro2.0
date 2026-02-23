"""
Command Bus - централизованная публикация команд через history-logger REST API.
Интегрирован с валидацией команд и отслеживанием выполнения.
Все общение с нодами происходит через history-logger.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

import httpx
from common.mqtt import MqttClient

from .circuit_breaker import CircuitBreaker
from .command_audit import CommandAudit
from .command_bus_alerts import emit_closed_loop_failure_alert, emit_publish_failure_alert
from .command_bus_controller import publish_controller_command, publish_controller_command_closed_loop
from .command_bus_dedupe import (
    bind_dedupe_cmd_id,
    build_dedupe_reference_key,
    complete_command_dedupe,
    normalized_json_payload,
    prune_dedupe_store_locked,
    reserve_command_dedupe,
    resolve_dedupe_ttl_sec,
)
from .command_bus_guards import (
    handle_command_channel_compatibility_failure,
    resolve_greenhouse_uid_for_zone,
    safe_create_zone_event,
    verify_command_channel_compatibility,
    verify_node_zone_assignment,
)
from .command_bus_publish import publish_command
from .command_bus_shared import (
    COMMANDS_SENT,
    COMMAND_DEDUPE_DECISIONS,
    COMMAND_DEDUPE_HITS,
    COMMAND_DEDUPE_RESERVE_CONFLICTS,
    COMMAND_REST_LATENCY,
    COMMAND_VALIDATION_FAILED,
    REST_PUBLISH_ERRORS,
    _DEFAULT_CLOSED_LOOP_TIMEOUT_SEC,
    _DEFAULT_COMMAND_DEDUPE_TTL_SEC,
    _MAX_COMMAND_DEDUPE_ENTRIES,
    _TERMINAL_COMMAND_STATUSES,
    _TRUE_VALUES,
)
from .command_tracker import CommandTracker
from .command_validator import CommandValidator

logger = logging.getLogger(__name__)


class CommandBus:
    """Централизованная публикация команд через history-logger REST API с валидацией и отслеживанием."""

    _safe_create_zone_event = safe_create_zone_event
    _verify_node_zone_assignment = verify_node_zone_assignment
    _resolve_greenhouse_uid_for_zone = resolve_greenhouse_uid_for_zone
    _verify_command_channel_compatibility = verify_command_channel_compatibility
    _handle_command_channel_compatibility_failure = handle_command_channel_compatibility_failure

    _resolve_dedupe_ttl_sec = resolve_dedupe_ttl_sec
    _normalized_json_payload = staticmethod(normalized_json_payload)
    _build_dedupe_reference_key = build_dedupe_reference_key
    _prune_dedupe_store_locked = prune_dedupe_store_locked
    _reserve_command_dedupe = reserve_command_dedupe
    _bind_dedupe_cmd_id = bind_dedupe_cmd_id
    _complete_command_dedupe = complete_command_dedupe

    _emit_publish_failure_alert = emit_publish_failure_alert
    _emit_closed_loop_failure_alert = emit_closed_loop_failure_alert

    publish_command = publish_command
    publish_controller_command = publish_controller_command
    publish_controller_command_closed_loop = publish_controller_command_closed_loop

    def __init__(
        self,
        mqtt: Optional[MqttClient] = None,
        gh_uid: str = "",
        history_logger_url: Optional[str] = None,
        history_logger_token: Optional[str] = None,
        command_source: Optional[str] = None,
        command_validator: Optional[CommandValidator] = None,
        command_tracker: Optional[CommandTracker] = None,
        command_audit: Optional[CommandAudit] = None,
        http_timeout: float = 5.0,
        api_circuit_breaker: Optional[CircuitBreaker] = None,
        enforce_node_zone_assignment: Optional[bool] = None,
        enforce_command_channel_compatibility: Optional[bool] = None,
    ):
        self.mqtt = mqtt
        self.gh_uid = gh_uid
        self.history_logger_url = history_logger_url or os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
        self.history_logger_token = history_logger_token or os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
        self.command_source = command_source or os.getenv("COMMAND_SOURCE", "automation")
        self.validator = command_validator or CommandValidator()
        self.tracker = command_tracker
        self.audit = command_audit or CommandAudit()
        self.http_timeout = http_timeout
        self.api_circuit_breaker = api_circuit_breaker
        self._zone_gh_uid_cache: Dict[int, str] = {}

        self.command_dedupe_ttl_sec = _DEFAULT_COMMAND_DEDUPE_TTL_SEC
        self.command_dedupe_enabled = str(os.getenv("AE_COMMAND_DEDUPE_ENABLED", "1")).strip().lower() in _TRUE_VALUES
        self._dedupe_store: Dict[str, Dict[str, Any]] = {}
        self._dedupe_lock = asyncio.Lock()

        if enforce_node_zone_assignment is None:
            raw_guard = str(os.getenv("AE_ENFORCE_NODE_ZONE_ASSIGNMENT", "1")).strip().lower()
            self.enforce_node_zone_assignment = raw_guard in _TRUE_VALUES
        else:
            self.enforce_node_zone_assignment = bool(enforce_node_zone_assignment)

        if enforce_command_channel_compatibility is None:
            raw_guard = str(os.getenv("AE_ENFORCE_COMMAND_CHANNEL_COMPATIBILITY", "1")).strip().lower()
            self.enforce_command_channel_compatibility = raw_guard in _TRUE_VALUES
        else:
            self.enforce_command_channel_compatibility = bool(enforce_command_channel_compatibility)

        self._http_client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Инициализировать долгоживущий HTTP клиент."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.http_timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
            logger.debug("CommandBus HTTP client initialized")

    async def stop(self):
        """Закрыть HTTP клиент и освободить ресурсы."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
            logger.debug("CommandBus HTTP client closed")

    def _get_client(self):
        """Получить HTTP клиент или None для временного клиента."""
        if self._http_client is None:
            logger.warning("CommandBus HTTP client not initialized, using temporary client")
            return None
        return self._http_client


__all__ = [
    "CommandBus",
    "COMMANDS_SENT",
    "COMMAND_DEDUPE_DECISIONS",
    "COMMAND_DEDUPE_HITS",
    "COMMAND_DEDUPE_RESERVE_CONFLICTS",
    "COMMAND_REST_LATENCY",
    "COMMAND_VALIDATION_FAILED",
    "REST_PUBLISH_ERRORS",
    "_DEFAULT_CLOSED_LOOP_TIMEOUT_SEC",
    "_DEFAULT_COMMAND_DEDUPE_TTL_SEC",
    "_MAX_COMMAND_DEDUPE_ENTRIES",
    "_TERMINAL_COMMAND_STATUSES",
    "_TRUE_VALUES",
]

