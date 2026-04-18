"""MQTT message handlers facade. Вся логика декомпозирована в ``handlers/`` subpackage.

Этот модуль остаётся публичным API для ``app.py`` и существующих тестов —
re-export handlers + зависимостей, которые тесты patch-ят через ``mqtt_handlers.X``.
"""

from __future__ import annotations

# Re-export dependencies: historical test patches target ``mqtt_handlers.X``.
from common.command_status_queue import (
    CommandStatus,
    deliver_status_to_laravel,
    normalize_status,
)
from common.db import (
    create_zone_event,
    execute,
    fetch,
    notify_zone_event_ingested,
    upsert_unassigned_node_error,
)
from common.env import get_settings
from common.error_handler import get_error_handler
from common.mqtt import get_mqtt_client
from common.simulation_events import record_simulation_event
from metrics import (
    COMMAND_RESPONSE_ERROR,
    COMMAND_RESPONSE_RECEIVED,
    CONFIG_REPORT_ERROR,
    CONFIG_REPORT_PROCESSED,
    CONFIG_REPORT_RECEIVED,
    DIAGNOSTICS_RECEIVED,
    ERROR_RECEIVED,
    HEARTBEAT_RECEIVED,
    NODE_EVENT_ERROR,
    NODE_EVENT_RECEIVED,
    NODE_EVENT_UNKNOWN,
    NODE_HELLO_ERRORS,
    NODE_HELLO_RECEIVED,
    NODE_HELLO_REGISTERED,
    STATUS_RECEIVED,
)
from utils import (
    _extract_channel_from_topic,
    _extract_gh_uid,
    _extract_node_uid,
    _extract_zone_uid,
    _parse_json,
)

# Public handlers (используются ``app.py`` для подписок MQTT).
from handlers.command_response import handle_command_response
from handlers.config_report import handle_config_report, sync_node_channels_from_payload
from handlers.diagnostics_error import handle_diagnostics, handle_error
from handlers.heartbeat_status import (
    handle_heartbeat,
    handle_lwt,
    handle_status,
    monitor_offline_nodes,
)
from handlers.node_event import handle_node_event
from handlers.node_hello import handle_node_hello
from handlers.time_request import handle_time_request

__all__ = [
    # Handlers
    "handle_command_response",
    "handle_config_report",
    "handle_diagnostics",
    "handle_error",
    "handle_heartbeat",
    "handle_lwt",
    "handle_node_event",
    "handle_node_hello",
    "handle_status",
    "handle_time_request",
    "monitor_offline_nodes",
    "sync_node_channels_from_payload",
    # Re-exported dependencies (retained for test patch compatibility)
    "CommandStatus",
    "COMMAND_RESPONSE_ERROR",
    "COMMAND_RESPONSE_RECEIVED",
    "CONFIG_REPORT_ERROR",
    "CONFIG_REPORT_PROCESSED",
    "CONFIG_REPORT_RECEIVED",
    "DIAGNOSTICS_RECEIVED",
    "ERROR_RECEIVED",
    "HEARTBEAT_RECEIVED",
    "NODE_EVENT_ERROR",
    "NODE_EVENT_RECEIVED",
    "NODE_EVENT_UNKNOWN",
    "NODE_HELLO_ERRORS",
    "NODE_HELLO_RECEIVED",
    "NODE_HELLO_REGISTERED",
    "STATUS_RECEIVED",
    "create_zone_event",
    "deliver_status_to_laravel",
    "execute",
    "fetch",
    "get_error_handler",
    "get_mqtt_client",
    "get_settings",
    "normalize_status",
    "notify_zone_event_ingested",
    "record_simulation_event",
    "upsert_unassigned_node_error",
    "_extract_channel_from_topic",
    "_extract_gh_uid",
    "_extract_node_uid",
    "_extract_zone_uid",
    "_parse_json",
]
