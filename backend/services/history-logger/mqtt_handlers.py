"""MQTT message handlers facade. Вся логика декомпозирована в ``handlers/`` subpackage.

Этот модуль остаётся публичным API для ``app.py`` и существующих тестов —
re-export handlers + зависимостей, которые тесты patch-ят через ``mqtt_handlers.X``.
"""

from __future__ import annotations

import logging
import httpx
import asyncio
import state
from handlers.dependencies import bind_dependencies as bind_config_report_dependencies
from handlers.dependencies import snapshot as config_report_dependency_snapshot

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
from handlers import command_response as command_response_module  # noqa: F401 - legacy facade re-export
from handlers import heartbeat_status as heartbeat_status_module  # noqa: F401 - legacy facade re-export
from handlers import node_event as node_event_module  # noqa: F401 - legacy facade re-export
from handlers import node_hello as node_hello_module  # noqa: F401 - legacy facade re-export
from handlers import _shared as handlers_shared_module  # noqa: F401 - legacy facade re-export
from handlers.command_response import handle_command_response as _handle_command_response_impl
from handlers.config_report import handle_config_report as _handle_config_report_impl
from handlers.config_report import sync_node_channels_from_payload as _sync_node_channels_from_payload_impl
from handlers.diagnostics_error import handle_diagnostics, handle_error
from handlers.heartbeat_status import (
    handle_heartbeat as _handle_heartbeat_impl,
    handle_lwt,
    handle_status as _handle_status_impl,
    monitor_offline_nodes as _monitor_offline_nodes_impl,
)
from handlers.node_event import handle_node_event as _handle_node_event_impl
from handlers.node_hello import handle_node_hello as _handle_node_hello_impl
from handlers.time_request import handle_time_request
from handlers._shared import (
    PENDING_CONFIG_REPORTS as _PENDING_CONFIG_REPORTS,
    BINDING_COMPLETION_LOCKS as _BINDING_COMPLETION_LOCKS,
    _transient_warning_last_seen,
    pop_pending_config_report as _pop_pending_config_report,
    store_pending_config_report as _store_pending_config_report_impl,
)
from handlers.config_report import (
    _complete_binding_after_config_report,
    _complete_sensor_calibrations_after_config_report,
)

logger = logging.getLogger(__name__)
_ORIG_COMPLETE_BINDING_AFTER_CONFIG_REPORT = _complete_binding_after_config_report
_ORIG_COMPLETE_SENSOR_CALIBRATIONS_AFTER_CONFIG_REPORT = _complete_sensor_calibrations_after_config_report


async def handle_command_response(topic: str, payload: bytes) -> None:
    with bind_config_report_dependencies(
        **config_report_dependency_snapshot(
            {
                'fetch': fetch,
                'execute': execute,
                'deliver_status_to_laravel': deliver_status_to_laravel,
                'record_simulation_event': record_simulation_event,
                'create_zone_event': create_zone_event,
                'normalize_status': normalize_status,
                'COMMAND_RESPONSE_RECEIVED': COMMAND_RESPONSE_RECEIVED,
                'COMMAND_RESPONSE_ERROR': COMMAND_RESPONSE_ERROR,
                '_extract_node_uid': _extract_node_uid,
                '_extract_channel_from_topic': _extract_channel_from_topic,
                '_extract_gh_uid': _extract_gh_uid,
                '_parse_json': _parse_json,
            }
        ).values
    ):
        await _handle_command_response_impl(topic, payload)


def _config_report_dependencies() -> dict:
    return {
        "fetch": fetch,
        "execute": execute,
        "get_settings": get_settings,
        "_parse_json": _parse_json,
        "_extract_node_uid": _extract_node_uid,
        "_extract_gh_uid": _extract_gh_uid,
        "_extract_zone_uid": _extract_zone_uid,
        "httpx": httpx,
        "logger": logger,
        "CONFIG_REPORT_RECEIVED": CONFIG_REPORT_RECEIVED,
        "CONFIG_REPORT_PROCESSED": CONFIG_REPORT_PROCESSED,
        "CONFIG_REPORT_ERROR": CONFIG_REPORT_ERROR,
        "store_pending_config_report": _store_pending_config_report,
        "sync_node_channels_from_payload": sync_node_channels_from_payload,
        "_complete_binding_after_config_report": _complete_binding_after_config_report,
        "_complete_sensor_calibrations_after_config_report": _complete_sensor_calibrations_after_config_report,
    }


async def handle_config_report(topic: str, payload: bytes) -> None:
    with bind_config_report_dependencies(**config_report_dependency_snapshot(_config_report_dependencies()).values):
        await _handle_config_report_impl(topic, payload)


async def sync_node_channels_from_payload(
    node_id: int, node_uid: str, channels_payload, *, allow_prune: bool = False
) -> None:
    await _sync_node_channels_from_payload_impl(
        node_id,
        node_uid,
        channels_payload,
        allow_prune=allow_prune,
        execute_fn=config_report_dependency_snapshot({"execute": execute}).execute,
    )


async def handle_heartbeat(topic: str, payload: bytes) -> None:
    with bind_config_report_dependencies(
        **config_report_dependency_snapshot(
            {
                'fetch': fetch,
                'execute': execute,
                'logger': logger,
                'HEARTBEAT_RECEIVED': HEARTBEAT_RECEIVED,
                '_extract_node_uid': _extract_node_uid,
                '_extract_gh_uid': _extract_gh_uid,
                '_extract_zone_uid': _extract_zone_uid,
                '_parse_json': _parse_json,
            }
        ).values
    ):
        await _handle_heartbeat_impl(topic, payload)


async def handle_status(topic: str, payload: bytes) -> None:
    with bind_config_report_dependencies(
        **config_report_dependency_snapshot(
            {
                'fetch': fetch,
                'execute': execute,
                'logger': logger,
                'HEARTBEAT_RECEIVED': HEARTBEAT_RECEIVED,
                '_extract_node_uid': _extract_node_uid,
                '_extract_gh_uid': _extract_gh_uid,
                '_extract_zone_uid': _extract_zone_uid,
                '_parse_json': _parse_json,
            }
        ).values
    ):
        await _handle_status_impl(topic, payload)


async def monitor_offline_nodes() -> None:
    with bind_config_report_dependencies(
        **config_report_dependency_snapshot(
            {
                'fetch': fetch,
                'execute': execute,
                'logger': logger,
                'HEARTBEAT_RECEIVED': HEARTBEAT_RECEIVED,
                '_extract_node_uid': _extract_node_uid,
                '_extract_gh_uid': _extract_gh_uid,
                '_extract_zone_uid': _extract_zone_uid,
                '_parse_json': _parse_json,
            }
        ).values
    ):
        await _monitor_offline_nodes_impl()


async def _resolve_zone_id_for_node_event_legacy(zone_uid, node_uid):
    """Runtime override for node_event zone resolution (DB uid → node fallback).

    Must stay aligned with ``handlers._shared.resolve_zone_id_for_node_event``:
    never map ``zn-<N>`` numeric suffix to ``zones.id`` (FK-unsafe for launch UIDs).
    """
    zone_uid_str = str(zone_uid or "").strip()
    if zone_uid_str:
        zone_rows = await fetch(
            """
            SELECT id
            FROM zones
            WHERE uid = $1
            LIMIT 1
            """,
            zone_uid_str,
        )
        if zone_rows:
            return zone_rows[0].get("id")

    if node_uid:
        node_rows = await fetch(
            """
            SELECT zone_id
            FROM nodes
            WHERE uid = $1
            LIMIT 1
            """,
            node_uid,
        )
        if node_rows:
            return node_rows[0].get("zone_id")

    return None


async def handle_node_event(topic: str, payload: bytes) -> None:
    with bind_config_report_dependencies(
        **config_report_dependency_snapshot(
            {
                'fetch': fetch,
                'resolve_zone_id_for_node_event': _resolve_zone_id_for_node_event_legacy,
                'create_zone_event': create_zone_event,
                'notify_zone_event_ingested': notify_zone_event_ingested,
                'NODE_EVENT_RECEIVED': NODE_EVENT_RECEIVED,
                'NODE_EVENT_ERROR': NODE_EVENT_ERROR,
                'NODE_EVENT_UNKNOWN': NODE_EVENT_UNKNOWN,
                '_parse_json': _parse_json,
                '_extract_gh_uid': _extract_gh_uid,
                '_extract_zone_uid': _extract_zone_uid,
                '_extract_node_uid': _extract_node_uid,
                '_extract_channel_from_topic': _extract_channel_from_topic,
            }
        ).values
    ):
        await _handle_node_event_impl(topic, payload)


async def handle_node_hello(topic: str, payload: bytes) -> None:
    with bind_config_report_dependencies(
        **config_report_dependency_snapshot(
            {
                'get_settings': get_settings,
                'asyncio': asyncio,
                'NODE_HELLO_RECEIVED': NODE_HELLO_RECEIVED,
                'NODE_HELLO_REGISTERED': NODE_HELLO_REGISTERED,
                'NODE_HELLO_ERRORS': NODE_HELLO_ERRORS,
                '_parse_json': _parse_json,
                'logger': logger,
                '_process_pending_config_report_after_registration': _process_pending_config_report_after_registration,
            }
        ).values
    ):
        await _handle_node_hello_impl(topic, payload)


async def _complete_sensor_calibrations_after_config_report(node_id: int, config):
    with bind_config_report_dependencies(**config_report_dependency_snapshot(_config_report_dependencies()).values):
        return await _ORIG_COMPLETE_SENSOR_CALIBRATIONS_AFTER_CONFIG_REPORT(node_id, config)


async def _complete_binding_after_config_report(node, node_uid: str, **kwargs):
    with bind_config_report_dependencies(**config_report_dependency_snapshot(_config_report_dependencies()).values):
        return await _ORIG_COMPLETE_BINDING_AFTER_CONFIG_REPORT(node, node_uid, **kwargs)


async def _store_pending_config_report(hardware_id: str, topic: str, payload: bytes) -> None:
    return await _store_pending_config_report_impl(hardware_id, topic, payload)


async def _process_pending_config_report_after_registration(hardware_id: str) -> None:
    pending = await _pop_pending_config_report(hardware_id)
    if not pending:
        return
    await handle_config_report(pending["topic"], pending["payload"])


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
    "_complete_binding_after_config_report",
    "_complete_sensor_calibrations_after_config_report",
    "_process_pending_config_report_after_registration",
    "_BINDING_COMPLETION_LOCKS",
    "_PENDING_CONFIG_REPORTS",
    "_transient_warning_last_seen",
    "_store_pending_config_report",
    "state",
]
