import asyncio
import hashlib
import logging
import os
import re
import uuid
from collections import OrderedDict
from typing import Any, Dict, Optional

import httpx

import state
from common.command_status_queue import CommandStatus, normalize_status, send_status_to_laravel
from common.db import create_zone_event, execute, fetch, upsert_unassigned_node_error
from common.env import get_settings
from common.error_handler import get_error_handler
from common.mqtt import get_mqtt_client
from common.node_types import normalize_node_type
from common.simulation_events import record_simulation_event
from common.trace_context import clear_trace_id, inject_trace_id_header, set_trace_id_from_payload
from common.utils.time import utcnow
from metrics import (
    COMMAND_RESPONSE_ERROR,
    COMMAND_RESPONSE_RECEIVED,
    CONFIG_REPORT_ERROR,
    CONFIG_REPORT_PROCESSED,
    CONFIG_REPORT_RECEIVED,
    DIAGNOSTICS_RECEIVED,
    ERROR_RECEIVED,
    HEARTBEAT_RECEIVED,
    NODE_HELLO_ERRORS,
    NODE_HELLO_RECEIVED,
    NODE_HELLO_REGISTERED,
    NODE_EVENT_ERROR,
    NODE_EVENT_RECEIVED,
    NODE_EVENT_UNKNOWN,
    STATUS_RECEIVED,
)
from utils import (
    _extract_channel_from_topic,
    _extract_gh_uid,
    _extract_node_uid,
    _extract_zone_uid,
    _parse_json,
)

logger = logging.getLogger(__name__)

_PENDING_CONFIG_REPORT_TTL_SEC = int(os.getenv("CONFIG_REPORT_BUFFER_TTL_SEC", "120"))
_PENDING_CONFIG_REPORT_MAX = int(os.getenv("CONFIG_REPORT_BUFFER_MAX", "128"))
_ZONE_EVENT_TYPE_MAX_LEN = 255
_ZONE_EVENT_TYPE_HASH_LEN = 10
_NODE_EVENT_METRIC_FALLBACK = "OTHER"
_NODE_EVENT_METRIC_ALLOWED_CODES = {
    "NODE_EVENT",
    "CLEAN_FILL_STARTED",
    "CLEAN_FILL_COMPLETED",
    "CLEAN_FILL_TIMEOUT",
    "CLEAN_FILL_FAILED",
    "SOLUTION_FILL_STARTED",
    "SOLUTION_FILL_COMPLETED",
    "SOLUTION_FILL_TIMEOUT",
    "SOLUTION_FILL_FAILED",
    "SOLUTION_PREP_STARTED",
    "SOLUTION_PREP_COMPLETED",
    "SOLUTION_PREP_FAILED",
    "IRRIGATION_STARTED",
    "IRRIGATION_COMPLETED",
    "IRRIGATION_FAILED",
    "IRRIGATION_RECOVERY_STARTED",
    "IRRIGATION_RECOVERY_COMPLETED",
    "IRRIGATION_RECOVERY_FAILED",
}
_PENDING_CONFIG_REPORTS: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_PENDING_CONFIG_REPORTS_LOCK = asyncio.Lock()
_BINDING_COMPLETION_LOCKS: dict[int, asyncio.Lock] = {}
_BINDING_COMPLETION_LOCKS_GUARD = asyncio.Lock()


def _resolve_stub_insert_status(normalized_status: CommandStatus) -> str:
    """
    Для unknown cmd_id вставляем pre-terminal статус, чтобы terminal side-effects
    формировались в Laravel через commandAck, а не терялись на early-return.
    """
    terminal_statuses = {
        CommandStatus.DONE,
        CommandStatus.ERROR,
        CommandStatus.INVALID,
        CommandStatus.BUSY,
        CommandStatus.NO_EFFECT,
        CommandStatus.TIMEOUT,
        CommandStatus.SEND_FAILED,
    }
    if normalized_status in terminal_statuses:
        return CommandStatus.ACK.value
    return normalized_status.value


def _prune_pending_config_reports_locked(now_ts: float) -> None:
    if not _PENDING_CONFIG_REPORTS:
        return

    expired_keys = [
        hardware_id
        for hardware_id, entry in _PENDING_CONFIG_REPORTS.items()
        if now_ts - entry.get("ts", now_ts) > _PENDING_CONFIG_REPORT_TTL_SEC
    ]

    for hardware_id in expired_keys:
        _PENDING_CONFIG_REPORTS.pop(hardware_id, None)


async def _store_pending_config_report(
    hardware_id: str, topic: str, payload: bytes
) -> None:
    now_ts = utcnow().timestamp()

    async with _PENDING_CONFIG_REPORTS_LOCK:
        _prune_pending_config_reports_locked(now_ts)
        _PENDING_CONFIG_REPORTS[hardware_id] = {
            "topic": topic,
            "payload": payload,
            "ts": now_ts,
        }
        _PENDING_CONFIG_REPORTS.move_to_end(hardware_id)

        while len(_PENDING_CONFIG_REPORTS) > _PENDING_CONFIG_REPORT_MAX:
            dropped_hardware_id, _ = _PENDING_CONFIG_REPORTS.popitem(last=False)
            logger.warning(
                "[CONFIG_REPORT] Dropped buffered config_report due to buffer limit: hardware_id=%s",
                dropped_hardware_id,
            )


async def _pop_pending_config_report(hardware_id: str) -> Optional[Dict[str, Any]]:
    now_ts = utcnow().timestamp()

    async with _PENDING_CONFIG_REPORTS_LOCK:
        _prune_pending_config_reports_locked(now_ts)
        return _PENDING_CONFIG_REPORTS.pop(hardware_id, None)


async def _process_pending_config_report_after_registration(hardware_id: str) -> None:
    pending = await _pop_pending_config_report(hardware_id)
    if not pending:
        return

    logger.info(
        "[NODE_HELLO] Processing buffered config_report after registration: hardware_id=%s",
        hardware_id,
    )

    try:
        await handle_config_report(pending["topic"], pending["payload"])
    except Exception as e:
        logger.error(
            "[NODE_HELLO] Failed to process buffered config_report: hardware_id=%s, error=%s",
            hardware_id,
            e,
            exc_info=True,
        )


async def _get_binding_completion_lock(node_id: int) -> asyncio.Lock:
    async with _BINDING_COMPLETION_LOCKS_GUARD:
        lock = _BINDING_COMPLETION_LOCKS.get(node_id)
        if lock is None:
            lock = asyncio.Lock()
            _BINDING_COMPLETION_LOCKS[node_id] = lock
        return lock


def _apply_trace_context(payload_data: Dict[str, Any], *, fallback_keys: Optional[tuple[str, ...]] = None) -> None:
    if fallback_keys:
        set_trace_id_from_payload(payload_data, keys=fallback_keys, fallback_generate=False)
    else:
        set_trace_id_from_payload(payload_data, fallback_generate=False)


def _normalize_command_response_details(raw_details: Any) -> Dict[str, Any]:
    if raw_details is None:
        return {}
    if isinstance(raw_details, dict):
        return dict(raw_details)
    raise ValueError("'details' must be object when present")


def _normalize_node_event_type(raw_event_code: Any) -> str:
    event_code = str(raw_event_code or "").strip().upper()
    if not event_code:
        return "NODE_EVENT"
    normalized = re.sub(r"[^A-Z0-9]+", "_", event_code)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    normalized = normalized or "NODE_EVENT"
    if len(normalized) <= _ZONE_EVENT_TYPE_MAX_LEN:
        return normalized
    hash_suffix = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[
        :_ZONE_EVENT_TYPE_HASH_LEN
    ].upper()
    trimmed_len = _ZONE_EVENT_TYPE_MAX_LEN - _ZONE_EVENT_TYPE_HASH_LEN - 1
    return f"{normalized[:trimmed_len]}_{hash_suffix}"


def _metric_event_code_label(event_type: str) -> str:
    if event_type in _NODE_EVENT_METRIC_ALLOWED_CODES:
        return event_type
    return _NODE_EVENT_METRIC_FALLBACK


async def _resolve_zone_id_for_node_event(zone_uid: Optional[str], node_uid: Optional[str]) -> Optional[int]:
    if zone_uid:
        zone_uid_str = str(zone_uid).strip()
        if zone_uid_str.startswith("zn-"):
            try:
                return int(zone_uid_str.split("-", 1)[1])
            except (ValueError, IndexError):
                pass
        else:
            try:
                return int(zone_uid_str)
            except ValueError:
                pass

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


async def handle_node_hello(topic: str, payload: bytes) -> None:
    """
    Обработчик node_hello сообщений от узлов ESP32.
    Регистрирует новые узлы через Laravel API.
    """
    try:
        logger.info("[NODE_HELLO] ===== START processing node_hello =====")
        logger.info(f"[NODE_HELLO] Topic: {topic}, payload length: {len(payload)}")

        try:
            data = _parse_json(payload)
            if not data or not isinstance(data, dict):
                logger.warning(
                    f"[NODE_HELLO] Invalid JSON in node_hello from topic {topic}"
                )
                NODE_HELLO_ERRORS.labels(error_type="invalid_json").inc()
                return

            _apply_trace_context(data)

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

            logger.info(
                f"[NODE_HELLO] Processing node_hello from hardware_id: {hardware_id}"
            )
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
                logger.error(
                    "[NODE_HELLO] Cannot register node without ingest token in production"
                )
                NODE_HELLO_ERRORS.labels(error_type="token_missing").inc()
                return
            else:
                logger.warning(
                    "[NODE_HELLO] No ingest token configured, registering without auth (dev mode only)"
                )

            MAX_API_RETRIES = 3
            API_RETRY_BACKOFF_BASE = 2
            API_TIMEOUT = s.laravel_api_timeout_sec

            last_error = None
            for attempt in range(MAX_API_RETRIES):
                try:
                    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
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
                        NODE_HELLO_ERRORS.labels(
                            error_type=f"http_{response.status_code}"
                        ).inc()
                        return

                    logger.error(
                        "[NODE_HELLO] Failed to register node: status=%s, hardware_id=%s, response=%s",
                        response.status_code,
                        hardware_id,
                        response.text[:500],
                    )
                    NODE_HELLO_ERRORS.labels(
                        error_type=f"http_{response.status_code}"
                    ).inc()
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


async def handle_heartbeat(topic: str, payload: bytes) -> None:
    """
    Обработчик heartbeat сообщений от узлов ESP32.
    Обновляет статус узла в БД.
    """
    try:
        logger.info("[HEARTBEAT] ===== START processing heartbeat =====")
        logger.info(f"[HEARTBEAT] Topic: {topic}, payload length: {len(payload)}")

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[HEARTBEAT] Invalid JSON in heartbeat from topic {topic}")
            return

        _apply_trace_context(data)

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[HEARTBEAT] Could not extract node_uid from topic {topic}")
            return

        gh_uid = _extract_gh_uid(topic)
        zone_uid = _extract_zone_uid(topic)
        is_temp_topic = gh_uid == "gh-temp" and zone_uid == "zn-temp"

        logger.info(
            f"[HEARTBEAT] Extracted gh_uid='{gh_uid}', zone_uid='{zone_uid}', is_temp_topic={is_temp_topic}, topic='{topic}'"
        )

        if is_temp_topic:
            # Для temp топиков node_uid на самом деле hardware_id
            hardware_id = node_uid
            logger.info(
                f"[HEARTBEAT] Processing heartbeat for temp topic, hardware_id: {hardware_id}, data: {data}"
            )

            # Найдем реальный node_uid по hardware_id
            node_rows = await fetch(
                "SELECT uid FROM nodes WHERE hardware_id = $1",
                hardware_id,
            )
            if not node_rows:
                logger.warning(f"[HEARTBEAT] Node not found for hardware_id: {hardware_id}")
                return
            node_uid = node_rows[0]["uid"]
            logger.info(f"[HEARTBEAT] Found node_uid: {node_uid} for hardware_id: {hardware_id}")
        else:
            logger.info(
                f"[HEARTBEAT] Processing heartbeat for node_uid: {node_uid}, data: {data}"
            )

        uptime = data.get("uptime")
        free_heap = data.get("free_heap") or data.get("free_heap_bytes")
        rssi = data.get("rssi")

        updates = []
        params = [node_uid]
        param_index = 1

        if uptime is not None:
            try:
                uptime_seconds = int(float(uptime))
                updates.append(f"uptime_seconds=${param_index + 1}")
                params.append(uptime_seconds)
                param_index += 1
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Invalid uptime value: %s",
                    uptime,
                    extra={"error": str(e), "node_uid": node_uid},
                )

        if free_heap is not None:
            try:
                free_heap_int = int(free_heap)
                updates.append(f"free_heap_bytes=${param_index + 1}")
                params.append(free_heap_int)
                param_index += 1
            except (ValueError, TypeError):
                logger.warning(f"Invalid free_heap value: {free_heap}")

        if rssi is not None:
            try:
                rssi_int = int(rssi)
                updates.append(f"rssi=${param_index + 1}")
                params.append(rssi_int)
                param_index += 1
            except (ValueError, TypeError):
                logger.warning(f"Invalid rssi value: {rssi}")

        updates.append("last_heartbeat_at=NOW()")
        updates.append("updated_at=NOW()")
        updates.append("last_seen_at=NOW()")
        updates.append("status='online'")

        if len(updates) > 4:
            query = "UPDATE nodes SET " + ", ".join(updates) + " WHERE uid=$1"
            await execute(query, *params)
        else:
            await execute(
                "UPDATE nodes SET last_heartbeat_at=NOW(), updated_at=NOW(), last_seen_at=NOW(), status='online' WHERE uid=$1",
                node_uid,
            )

        HEARTBEAT_RECEIVED.labels(node_uid=node_uid).inc()

        logged_uptime = None
        if uptime is not None:
            try:
                logged_uptime = int(float(uptime))
            except (ValueError, TypeError):
                logged_uptime = uptime

        logger.info(
            "[HEARTBEAT] Node heartbeat processed successfully: node_uid=%s, uptime_seconds=%s, free_heap=%s, rssi=%s",
            node_uid,
            logged_uptime,
            free_heap,
            rssi,
        )
    finally:
        clear_trace_id()


async def handle_status(topic: str, payload: bytes) -> None:
    """
    Обработчик status сообщений от узлов ESP32.
    Обновляет статус узла в БД при получении ONLINE/OFFLINE.
    """
    try:
        logger.info("[STATUS] ===== START processing status =====")
        logger.info(f"[STATUS] Topic: {topic}, payload length: {len(payload)}")

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[STATUS] Invalid JSON in status from topic {topic}")
            return

        _apply_trace_context(data)

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[STATUS] Could not extract node_uid from topic {topic}")
            return

        status = data.get("status", "").upper()

        logger.info(
            "[STATUS] Processing status for node_uid: %s, status: %s", node_uid, status
        )

        if status == "ONLINE":
            await execute(
                "UPDATE nodes SET status='online', last_seen_at=NOW(), updated_at=NOW() WHERE uid=$1",
                node_uid,
            )
            logger.info(f"[STATUS] Node {node_uid} marked as ONLINE")
        elif status == "OFFLINE":
            await execute(
                "UPDATE nodes SET status='offline', updated_at=NOW() WHERE uid=$1",
                node_uid,
            )
            logger.info(f"[STATUS] Node {node_uid} marked as OFFLINE")
        else:
            logger.warning(f"[STATUS] Unknown status value: {status} for node {node_uid}")

        STATUS_RECEIVED.labels(node_uid=node_uid, status=status.lower()).inc()
    finally:
        clear_trace_id()


async def handle_lwt(topic: str, payload: bytes) -> None:
    """
    Обработчик LWT сообщений от узлов ESP32.
    LWT приходит как строка "offline" при потере связи.
    """
    try:
        logger.info("[LWT] ===== START processing LWT =====")
        logger.info(f"[LWT] Topic: {topic}, payload length: {len(payload)}")

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[LWT] Could not extract node_uid from topic {topic}")
            return

        raw_payload = payload.decode("utf-8", errors="ignore").strip()
        status = raw_payload.upper()
        if not status:
            data = _parse_json(payload)
            if isinstance(data, dict):
                _apply_trace_context(data)
                status = str(data.get("status", "")).upper()

        if status not in ("OFFLINE", "ONLINE"):
            status = "OFFLINE"

        if status == "ONLINE":
            await execute(
                "UPDATE nodes SET status='online', last_seen_at=NOW(), updated_at=NOW() WHERE uid=$1",
                node_uid,
            )
            logger.info(f"[LWT] Node {node_uid} marked as ONLINE (unexpected LWT payload)")
        else:
            await execute(
                "UPDATE nodes SET status='offline', updated_at=NOW() WHERE uid=$1",
                node_uid,
            )
            logger.info(f"[LWT] Node {node_uid} marked as OFFLINE")

        STATUS_RECEIVED.labels(node_uid=node_uid, status=status.lower()).inc()
    finally:
        clear_trace_id()


async def monitor_offline_nodes() -> None:
    """Периодически помечает узлы offline, если давно не было last_seen_at."""
    s = get_settings()
    timeout_sec = max(1, s.node_offline_timeout_sec)
    interval_sec = max(1, s.node_offline_check_interval_sec)

    logger.info(
        f"[OFFLINE_MONITOR] Started (timeout={timeout_sec}s, interval={interval_sec}s)"
    )

    while not state.shutdown_event.is_set():
        try:
            result = await execute(
                """
                UPDATE nodes
                SET status='offline', updated_at=NOW()
                WHERE status='online'
                  AND COALESCE(last_seen_at, last_heartbeat_at, updated_at, created_at)
                      < NOW() - ($1 * interval '1 second')
                """,
                timeout_sec,
            )
            if isinstance(result, str) and result.startswith("UPDATE"):
                try:
                    updated = int(result.split()[-1])
                except (ValueError, IndexError):
                    updated = 0
                if updated > 0:
                    logger.warning(f"[OFFLINE_MONITOR] Marked offline: {updated}")
        except Exception as exc:
            logger.error(f"[OFFLINE_MONITOR] Failed to update offline nodes: {exc}")

        try:
            await asyncio.wait_for(state.shutdown_event.wait(), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue


async def handle_diagnostics(topic: str, payload: bytes) -> None:
    """
    Обработчик diagnostics сообщений от узлов ESP32.
    Обрабатывает метрики ошибок через общий компонент error_handler.
    """
    try:
        logger.info("[DIAGNOSTICS] ===== START processing diagnostics =====")
        logger.info(f"[DIAGNOSTICS] Topic: {topic}, payload length: {len(payload)}")

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[DIAGNOSTICS] Invalid JSON in diagnostics from topic {topic}")
            return

        _apply_trace_context(data)

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[DIAGNOSTICS] Could not extract node_uid from topic {topic}")
            return

        logger.info(f"[DIAGNOSTICS] Processing diagnostics for node_uid: {node_uid}")

        error_handler = get_error_handler()
        await error_handler.handle_diagnostics(node_uid, data)

        DIAGNOSTICS_RECEIVED.labels(node_uid=node_uid).inc()
    finally:
        clear_trace_id()


async def handle_error(topic: str, payload: bytes) -> None:
    """
    Обработчик error сообщений от узлов ESP32.
    Обрабатывает немедленные ошибки через общий компонент error_handler.
    Для temp-топиков (gh-temp/zn-temp) записывает ошибки в unassigned_node_errors.
    """
    try:
        logger.info("[ERROR] ===== START processing error =====")
        logger.info(f"[ERROR] Topic: {topic}, payload length: {len(payload)}")

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[ERROR] Invalid JSON in error from topic {topic}")
            return

        _apply_trace_context(data)

        gh_uid = _extract_gh_uid(topic)
        zone_uid = _extract_zone_uid(topic)
        is_temp_topic = gh_uid == "gh-temp" and zone_uid == "zn-temp"

        if is_temp_topic:
            hardware_id = _extract_node_uid(topic)
            if not hardware_id:
                logger.warning(f"[ERROR] Could not extract hardware_id from temp topic {topic}")
                return

            level = data.get("level", "ERROR")
            component = data.get("component", "unknown")
            error_code = data.get("error_code")
            error_message = data.get("message", data.get("error", "Unknown error"))

            logger.info(
                "[ERROR] Processing error for unassigned node (hardware_id: %s), level: %s, component: %s, error_code: %s",
                hardware_id,
                level,
                component,
                error_code,
            )

            try:
                await upsert_unassigned_node_error(
                    hardware_id=hardware_id,
                    error_message=error_message,
                    error_code=error_code,
                    severity=level,
                    topic=topic,
                    last_payload=data,
                )
                logger.info(
                    f"[ERROR] Saved error for unassigned node hardware_id={hardware_id}"
                )
            except Exception as e:
                logger.error(
                    f"[ERROR] Failed to save unassigned node error: {e}", exc_info=True
                )

            ERROR_RECEIVED.labels(
                node_uid=f"unassigned-{hardware_id}", level=level.lower()
            ).inc()
            return

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[ERROR] Could not extract node_uid from topic {topic}")
            return

        level = data.get("level", "ERROR")
        component = data.get("component", "unknown")
        error_code = data.get("error_code", "unknown")

        logger.info(
            "[ERROR] Processing error for node_uid: %s, level: %s, component: %s, error_code: %s",
            node_uid,
            level,
            component,
            error_code,
        )

        try:
            node_rows = await fetch(
                """
                SELECT n.id, n.hardware_id, n.zone_id
                FROM nodes n
                WHERE n.uid = $1
                """,
                node_uid,
            )

            if not node_rows:
                hardware_id_from_topic = node_uid
                hardware_id_from_payload = data.get("hardware_id")
                hardware_id = hardware_id_from_payload or hardware_id_from_topic

                error_message = data.get("message", data.get("error", "Unknown error"))

                logger.info(
                    "[ERROR] Node not found in DB, saving to unassigned errors: node_uid=%s, hardware_id=%s",
                    node_uid,
                    hardware_id,
                )

                try:
                    await upsert_unassigned_node_error(
                        hardware_id=hardware_id,
                        error_message=error_message,
                        error_code=error_code,
                        severity=level,
                        topic=topic,
                        last_payload=data,
                    )
                    logger.info(
                        f"[ERROR] Saved error for unassigned node hardware_id={hardware_id}"
                    )
                except Exception as e:
                    logger.error(
                        f"[ERROR] Failed to save unassigned node error: {e}",
                        exc_info=True,
                    )

                ERROR_RECEIVED.labels(
                    node_uid=f"unassigned-{hardware_id}", level=level.lower()
                ).inc()
                return

            node = node_rows[0]
            zone_id = node.get("zone_id")

            if not zone_id:
                hardware_id = node.get("hardware_id")
                if hardware_id:
                    error_message = data.get("message", data.get("error", "Unknown error"))
                    logger.info(
                        "[ERROR] Node not assigned to zone, saving to unassigned errors: node_uid=%s, hardware_id=%s, node_id=%s",
                        node_uid,
                        hardware_id,
                        node["id"],
                    )
                    try:
                        await upsert_unassigned_node_error(
                            hardware_id=hardware_id,
                            error_message=error_message,
                            error_code=error_code,
                            severity=level,
                            topic=topic,
                            last_payload=data,
                        )
                        logger.info(
                            f"[ERROR] Saved error for unassigned node hardware_id={hardware_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"[ERROR] Failed to save unassigned node error: {e}",
                            exc_info=True,
                        )
                    ERROR_RECEIVED.labels(
                        node_uid=f"unassigned-{hardware_id}", level=level.lower()
                    ).inc()
                    return

            error_handler = get_error_handler()
            await error_handler.handle_error(node_uid, data)

        except Exception as e:
            logger.error(f"[ERROR] Error checking node in DB: {e}", exc_info=True)
            error_handler = get_error_handler()
            await error_handler.handle_error(node_uid, data)

        ERROR_RECEIVED.labels(node_uid=node_uid, level=level.lower()).inc()
    finally:
        clear_trace_id()


async def handle_node_event(topic: str, payload: bytes) -> None:
    """
    Обработчик channel-level event сообщений от узлов ESP32.
    Пример топика: hydro/{gh}/{zone}/{node}/{channel}/event
    """
    try:
        logger.info("[NODE_EVENT] ===== START processing node event =====")
        logger.info("[NODE_EVENT] Topic: %s, payload length: %s", topic, len(payload))

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning("[NODE_EVENT] Invalid JSON in event from topic %s", topic)
            NODE_EVENT_ERROR.labels(reason="invalid_json").inc()
            return

        _apply_trace_context(data, fallback_keys=("trace_id", "event_id", "cmd_id"))

        gh_uid = _extract_gh_uid(topic)
        zone_uid = _extract_zone_uid(topic)
        node_uid = _extract_node_uid(topic)
        channel = _extract_channel_from_topic(topic)

        event_code_raw = data.get("event_code") or data.get("event") or data.get("type") or "node_event"
        event_code = str(event_code_raw).strip()
        if not event_code:
            event_code = "node_event"
        event_type = _normalize_node_event_type(event_code)

        zone_id = await _resolve_zone_id_for_node_event(zone_uid, node_uid)
        if not zone_id:
            logger.warning(
                "[NODE_EVENT] Could not resolve zone_id for event, skipping: gh_uid=%s zone_uid=%s node_uid=%s channel=%s event_code=%s",
                gh_uid,
                zone_uid,
                node_uid,
                channel,
                event_code,
            )
            NODE_EVENT_ERROR.labels(reason="zone_not_resolved").inc()
            return

        details = {
            "source": "node_event",
            "topic": topic,
            "gh_uid": gh_uid,
            "zone_uid": zone_uid,
            "node_uid": node_uid,
            "channel": channel,
            "event_code": event_code,
            "payload": data,
        }
        await create_zone_event(zone_id, event_type, details)
        metric_event_code = _metric_event_code_label(event_type)
        NODE_EVENT_RECEIVED.labels(event_code=metric_event_code).inc()
        if metric_event_code == _NODE_EVENT_METRIC_FALLBACK:
            NODE_EVENT_UNKNOWN.inc()

        logger.info(
            "[NODE_EVENT] Stored zone event: zone_id=%s node_uid=%s channel=%s event_type=%s",
            zone_id,
            node_uid,
            channel,
            event_type,
        )
    except Exception:
        NODE_EVENT_ERROR.labels(reason="handler_exception").inc()
        logger.exception("[NODE_EVENT] Unexpected error while handling event topic %s", topic)
    finally:
        clear_trace_id()


async def handle_config_report(topic: str, payload: bytes) -> None:
    """
    Обработчик config_report сообщений от узлов ESP32.
    Сохраняет NodeConfig в БД и синхронизирует каналы.
    """
    try:
        logger.info("[CONFIG_REPORT] ===== START processing config_report =====")
        logger.info(f"[CONFIG_REPORT] Topic: {topic}, payload length: {len(payload)}")

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(
                f"[CONFIG_REPORT] Invalid JSON in config_report from topic {topic}"
            )
            CONFIG_REPORT_ERROR.labels(node_uid="unknown").inc()
            return

        _apply_trace_context(data)

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(
                f"[CONFIG_REPORT] Could not extract node_uid from topic {topic}"
            )
            CONFIG_REPORT_ERROR.labels(node_uid="unknown").inc()
            return

        gh_uid = _extract_gh_uid(topic)
        zone_uid = _extract_zone_uid(topic)
        is_temp_topic = gh_uid == "gh-temp" and zone_uid == "zn-temp"

        if is_temp_topic:
            hardware_id = node_uid
            node_rows = await fetch(
                """
                SELECT id,
                       uid,
                       lifecycle_state,
                       zone_id,
                       pending_zone_id
                FROM nodes
                WHERE hardware_id = $1
                """,
                hardware_id,
            )
            if not node_rows:
                logger.warning(
                    f"[CONFIG_REPORT] Node not found for hardware_id {hardware_id}, skipping config_report"
                )
                CONFIG_REPORT_ERROR.labels(node_uid="unknown").inc()
                await _store_pending_config_report(hardware_id, topic, payload)
                logger.info(
                    "[CONFIG_REPORT] Buffered config_report until node registration: hardware_id=%s",
                    hardware_id,
                )
                return
            node = node_rows[0]
            node_uid = node.get("uid")
            node_id = node.get("id")
            if node_uid and isinstance(data, dict):
                data["node_id"] = node_uid
            logger.info(
                "[CONFIG_REPORT] Mapped temp config_report: hardware_id=%s -> node_uid=%s",
                hardware_id,
                node_uid,
            )
        else:
            node_rows = await fetch(
                """
                SELECT id,
                       uid,
                       lifecycle_state,
                       zone_id,
                       pending_zone_id
                FROM nodes
                WHERE uid = $1
                """,
                node_uid,
            )
            if not node_rows:
                logger.warning(
                    f"[CONFIG_REPORT] Node {node_uid} not found in database, skipping config_report"
                )
                CONFIG_REPORT_ERROR.labels(node_uid=node_uid).inc()
                return
            node = node_rows[0]
            node_id = node.get("id")

        CONFIG_REPORT_RECEIVED.inc()

        await execute(
            """
            UPDATE nodes
            SET config = $1,
                updated_at = NOW()
            WHERE id = $2
            """,
            data,
            node_id,
        )

        channels_payload = data.get("channels")
        if channels_payload is not None:
            try:
                await sync_node_channels_from_payload(
                    node_id, node_uid, channels_payload
                )
            except Exception as sync_err:
                logger.warning(
                    "[CONFIG_REPORT] Failed to sync channels for node %s: %s",
                    node_uid,
                    sync_err,
                    exc_info=True,
                )

        await _complete_binding_after_config_report(node, node_uid)

        CONFIG_REPORT_PROCESSED.inc()
        logger.info(f"[CONFIG_REPORT] Config stored for node {node_uid}")
    except Exception as e:
        logger.error(
            f"[CONFIG_REPORT] Unexpected error processing config_report: {e}",
            exc_info=True,
        )
        CONFIG_REPORT_ERROR.labels(node_uid="unknown").inc()
    finally:
        clear_trace_id()


async def _complete_binding_after_config_report(
    node: Dict[str, Any], node_uid: str
) -> None:
    node_id = node.get("id")
    if not node_id:
        return

    lock = await _get_binding_completion_lock(int(node_id))
    async with lock:
        current_rows = await fetch(
            """
            SELECT lifecycle_state, zone_id, pending_zone_id
            FROM nodes
            WHERE id = $1
            """,
            node_id,
        )
        if not current_rows:
            return

        current_state = current_rows[0]
        lifecycle_state = current_state.get("lifecycle_state")
        zone_id = current_state.get("zone_id")
        pending_zone_id = current_state.get("pending_zone_id")
        target_zone_id = zone_id or pending_zone_id

        if lifecycle_state != "REGISTERED_BACKEND" or not target_zone_id:
            return

        zone_check = await fetch("SELECT id FROM zones WHERE id = $1", target_zone_id)
        if not zone_check:
            logger.warning(
                "[CONFIG_REPORT] Zone %s not found, cannot complete binding for node %s",
                target_zone_id,
                node_uid,
            )
            return

        s = get_settings()
        laravel_url = s.laravel_api_url if hasattr(s, "laravel_api_url") else None
        ingest_token = (
            s.history_logger_api_token
            if hasattr(s, "history_logger_api_token") and s.history_logger_api_token
            else (
                s.ingest_token
                if hasattr(s, "ingest_token") and s.ingest_token
                else None
            )
        )

        if not laravel_url:
            logger.error(
                "[CONFIG_REPORT] Laravel API URL not configured, cannot update node lifecycle"
            )
            return

        headers = inject_trace_id_header(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        if ingest_token:
            headers["Authorization"] = f"Bearer {ingest_token}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if pending_zone_id and not zone_id:
                    update_response = await client.patch(
                        f"{laravel_url}/api/nodes/{node_id}/service-update",
                        headers=headers,
                        json={
                            "zone_id": pending_zone_id,
                            "pending_zone_id": None,
                        },
                    )
                    if update_response.status_code != 200:
                        logger.warning(
                            "[CONFIG_REPORT] Failed to update zone_id for node %s (id=%s): %s %s",
                            node_uid,
                            node_id,
                            update_response.status_code,
                            update_response.text,
                        )
                        return

                transition_response = await client.post(
                    f"{laravel_url}/api/nodes/{node_id}/lifecycle/service-transition",
                    headers=headers,
                    json={
                        "target_state": "ASSIGNED_TO_ZONE",
                        "reason": "Config report received from node",
                    },
                )

                if transition_response.status_code != 200:
                    logger.warning(
                        "[CONFIG_REPORT] Failed to transition node %s (id=%s) to ASSIGNED_TO_ZONE: %s %s",
                        node_uid,
                        node_id,
                        transition_response.status_code,
                        transition_response.text,
                    )
        except Exception as e:
            logger.error(
                "[CONFIG_REPORT] Error while completing binding for node %s: %s",
                node_uid,
                e,
                exc_info=True,
            )


async def sync_node_channels_from_payload(
    node_id: int, node_uid: str, channels_payload: Any
) -> None:
    if not node_id:
        logger.warning("[CONFIG_REPORT] Cannot sync channels: node_id missing")
        return

    if not isinstance(channels_payload, list):
        logger.warning(
            "[CONFIG_REPORT] channels payload is not a list for node %s: %s",
            node_uid,
            type(channels_payload),
        )
        return

    if len(channels_payload) == 0:
        logger.info(
            f"[CONFIG_REPORT] channels payload empty for node {node_uid}, skipping sync"
        )
        return

    updated = 0
    skipped = 0
    channel_names: list[str] = []
    for channel in channels_payload:
        if not isinstance(channel, dict):
            skipped += 1
            continue

        channel_name = channel.get("name") or channel.get("channel")
        if channel_name is None:
            skipped += 1
            continue

        channel_name = str(channel_name).strip()
        if not channel_name:
            skipped += 1
            continue

        channel_name = channel_name[:255]

        type_value = channel.get("type") or channel.get("channel_type")
        if type_value is not None:
            type_value = str(type_value).strip().upper()
            if not type_value:
                type_value = None

        metric_value = channel.get("metric") or channel.get("metrics")
        if metric_value is not None:
            metric_value = str(metric_value).strip().upper()
            if not metric_value:
                metric_value = None

        unit_value = channel.get("unit")
        if unit_value is not None:
            unit_value = str(unit_value).strip()
            if not unit_value:
                unit_value = None

        config = {
            key: value
            for key, value in channel.items()
            if key not in {"name", "channel", "type", "channel_type", "metric", "metrics", "unit"}
        }
        if not config:
            config = None

        await execute(
            """
            INSERT INTO node_channels (node_id, channel, type, metric, unit, config, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
            ON CONFLICT (node_id, channel)
            DO UPDATE SET
                type = COALESCE(EXCLUDED.type, node_channels.type),
                metric = COALESCE(EXCLUDED.metric, node_channels.metric),
                unit = COALESCE(EXCLUDED.unit, node_channels.unit),
                config = COALESCE(EXCLUDED.config, node_channels.config),
                updated_at = NOW()
            """,
            node_id,
            channel_name,
            type_value,
            metric_value,
            unit_value,
            config,
        )
        channel_names.append(channel_name)
        updated += 1

    if channel_names:
        await execute(
            """
            DELETE FROM node_channels
            WHERE node_id = $1
              AND NOT (channel = ANY($2))
            """,
            node_id,
            list(set(channel_names)),
        )
    else:
        await execute(
            "DELETE FROM node_channels WHERE node_id = $1",
            node_id,
        )

    logger.info(
        "[CONFIG_REPORT] Synced %s channel(s) for node %s, skipped %s",
        updated,
        node_uid,
        skipped,
    )


async def handle_command_response(topic: str, payload: bytes) -> None:
    """
    Обработчик command_response сообщений от узлов.
    Обновляет статус команды через Laravel API с использованием надёжной доставки.
    """
    try:
        logger.info(
            f"[COMMAND_RESPONSE] STEP 0: Received message on topic {topic}, payload length: {len(payload)}"
        )
        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(
                f"[COMMAND_RESPONSE] STEP 0.1: Invalid JSON in command_response from topic {topic}"
            )
            COMMAND_RESPONSE_ERROR.inc()
            return

        _apply_trace_context(data, fallback_keys=("trace_id", "cmd_id", "cmdId"))

        cmd_id = data.get("cmd_id")
        raw_status = data.get("status", "")
        response_ts = data.get("ts")

        logger.info(
            "[COMMAND_RESPONSE] STEP 0.2: Parsed command_response: cmd_id=%s, status=%s, ts=%s, topic=%s",
            cmd_id,
            raw_status,
            response_ts,
            topic,
        )
        node_uid = _extract_node_uid(topic)
        channel = _extract_channel_from_topic(topic)
        gh_uid = _extract_gh_uid(topic)

        if (
            not cmd_id
            or not raw_status
            or not isinstance(response_ts, int)
            or response_ts < 0
        ):
            logger.warning(
                "[COMMAND_RESPONSE] Missing or invalid required fields in payload: cmd_id=%s status=%s ts=%s payload=%s",
                cmd_id,
                raw_status,
                response_ts,
                data,
            )
            COMMAND_RESPONSE_ERROR.inc()
            return

        normalized_status = normalize_status(raw_status)
        if not normalized_status:
            logger.warning(
                "[COMMAND_RESPONSE] Unknown status '%s' for cmd_id=%s, node_uid=%s, channel=%s",
                raw_status,
                cmd_id,
                node_uid,
                channel,
            )
            COMMAND_RESPONSE_ERROR.inc()
            return

        COMMAND_RESPONSE_RECEIVED.inc()

        zone_id = None
        cmd_name = None
        try:
            existing_cmd = await fetch(
                "SELECT status, zone_id, cmd FROM commands WHERE cmd_id = $1", cmd_id
            )
            if not existing_cmd:
                node_id = None
                if node_uid:
                    node_rows = await fetch(
                        "SELECT id, zone_id FROM nodes WHERE uid = $1", node_uid
                    )
                    if node_rows:
                        node_id = node_rows[0]["id"]
                        zone_id = node_rows[0]["zone_id"]

                status_value = _resolve_stub_insert_status(normalized_status)
                cmd_name = "unknown"

                await execute(
                    """
                    INSERT INTO commands (zone_id, node_id, channel, cmd, params, status, source, cmd_id, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
                    """,
                    zone_id,
                    node_id,
                    channel,
                    cmd_name,
                    {},
                    status_value,
                    "device",
                    cmd_id,
                )
                logger.info(
                    "[COMMAND_RESPONSE] Created stub record for cmd_id=%s, status=%s, node_uid=%s, channel=%s, origin=device",
                    cmd_id,
                    status_value,
                    node_uid,
                    channel,
                )
            else:
                zone_id = existing_cmd[0].get("zone_id")
                cmd_name = existing_cmd[0].get("cmd")
        except Exception as e:
            logger.warning(
                "[COMMAND_RESPONSE] Failed to ensure stub record for cmd_id=%s: %s",
                cmd_id,
                e,
                exc_info=True,
            )

        try:
            details = _normalize_command_response_details(data.get("details"))
        except ValueError:
            logger.warning(
                "[COMMAND_RESPONSE] Invalid details type for cmd_id=%s: %s",
                cmd_id,
                type(data.get("details")).__name__,
            )
            COMMAND_RESPONSE_ERROR.inc()
            return
        if "error_code" in data and data.get("error_code") is not None:
            details["error_code"] = data.get("error_code")
        if "error_message" in data and data.get("error_message") is not None:
            details["error_message"] = data.get("error_message")
        details.update({
            "raw_status": str(raw_status),
            "response_ts": response_ts,
            "node_uid": node_uid,
            "channel": channel,
            "gh_uid": gh_uid,
        })
        details = {k: v for k, v in details.items() if v is not None}

        success = await send_status_to_laravel(cmd_id, normalized_status, details)

        if success:
            logger.info(
                "[COMMAND_RESPONSE] Status '%s' delivered to Laravel for cmd_id=%s, node_uid=%s, channel=%s",
                normalized_status.value,
                cmd_id,
                node_uid,
                channel,
            )
        else:
            logger.info(
                "[COMMAND_RESPONSE] Status '%s' queued for retry for cmd_id=%s, node_uid=%s, channel=%s",
                normalized_status.value,
                cmd_id,
                node_uid,
                channel,
            )

        if zone_id:
            status_value = (
                normalized_status.value
                if hasattr(normalized_status, "value")
                else str(normalized_status)
            )
            event_status = status_value.lower()
            level = "info"
            if event_status in ("error", "failed", "timeout", "send_failed"):
                level = "error"
            elif event_status in ("invalid", "busy", "no_effect"):
                level = "warning"

            await record_simulation_event(
                zone_id,
                service="history-logger",
                stage="command_response",
                status=event_status,
                level=level,
                message="Получен ответ на команду",
                payload={
                    "cmd_id": cmd_id,
                    "cmd": cmd_name,
                    "channel": channel,
                    "node_uid": node_uid,
                    "raw_status": raw_status,
                    "delivery": "delivered" if success else "queued",
                },
            )

    except Exception as e:
        logger.error(
            f"[COMMAND_RESPONSE] Unexpected error processing message: {e}",
            exc_info=True,
        )
        COMMAND_RESPONSE_ERROR.inc()
    finally:
        clear_trace_id()


async def handle_time_request(topic: str, payload: bytes) -> None:
    """
    Обработчик запросов времени от устройств (time_request).
    Отправляет команду set_time с текущим серверным временем.
    """
    try:
        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[TIME_REQUEST] Invalid JSON in time_request from topic {topic}")
            return

        _apply_trace_context(data)

        server_time = int(utcnow().timestamp())
        mqtt = await get_mqtt_client()

        command_payload = {
            "cmd": "set_time",
            "cmd_id": f"time_sync_{uuid.uuid4().hex[:8]}",
            "params": {"unix_ts": server_time},
        }

        broadcast_topic = "hydro/time/response"
        response_payload = {
            "message_type": "time_response",
            "unix_ts": server_time,
            "server_time": server_time,
        }

        mqtt._client.publish_json(broadcast_topic, response_payload, qos=1, retain=False)
        logger.info(
            "[TIME_REQUEST] Sent time response: server_time=%s, topic=%s",
            server_time,
            broadcast_topic,
        )
    except Exception as e:
        logger.error(
            f"[TIME_REQUEST] Unexpected error processing time_request: {e}",
            exc_info=True,
        )
    finally:
        clear_trace_id()
