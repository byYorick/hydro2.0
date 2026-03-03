"""CommandBus publish flow."""

import logging
import time
from typing import Any, Dict, Optional

import httpx
from common.infra_alerts import send_infra_exception_alert
from common.simulation_events import record_simulation_event
from services.resilience_contract import (
    INFRA_COMMAND_PUBLISH_RESPONSE_DECODE_ERROR,
    INFRA_COMMAND_SEND_FAILED,
    INFRA_COMMAND_TIMEOUT,
    INFRA_UNKNOWN_ERROR,
)
from utils.logging_context import get_trace_id

from .command_bus_shared import COMMANDS_SENT, COMMAND_REST_LATENCY, COMMAND_VALIDATION_FAILED, REST_PUBLISH_ERRORS

logger = logging.getLogger(__name__)


async def publish_command(
    command_bus: Any,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    params: Optional[Dict[str, Any]] = None,
    cmd_id: Optional[str] = None,
    *,
    dedupe_state: Optional[Dict[str, Any]] = None,
) -> bool:
    start_time = time.time()
    publish_success = False
    dedupe_ttl_sec = command_bus._resolve_dedupe_ttl_sec(params)
    active_dedupe_state = dedupe_state
    if active_dedupe_state is None:
        active_dedupe_state = await command_bus._reserve_command_dedupe(
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            params=params,
            cmd_id=cmd_id,
            dedupe_ttl_sec=dedupe_ttl_sec,
        )

    dedupe_decision = str(active_dedupe_state.get("decision") or "new").strip().lower()
    dedupe_reference_key = str(active_dedupe_state.get("reference_key") or "").strip()
    dedupe_ttl_value = int(active_dedupe_state.get("dedupe_ttl_sec") or dedupe_ttl_sec)
    effective_cmd_id = str(cmd_id or active_dedupe_state.get("effective_cmd_id") or "").strip() or None

    if dedupe_decision in {"duplicate_blocked", "duplicate_no_effect"}:
        logger.info(
            "Zone %s: command dedupe prevented side-effect publish cmd=%s node_uid=%s channel=%s decision=%s",
            zone_id,
            cmd,
            node_uid,
            channel,
            dedupe_decision,
            extra={
                "zone_id": zone_id,
                "cmd": cmd,
                "node_uid": node_uid,
                "channel": channel,
                "dedupe_decision": dedupe_decision,
                "dedupe_reference_key": dedupe_reference_key,
                "dedupe_ttl_sec": dedupe_ttl_value,
            },
        )
        await record_simulation_event(
            zone_id,
            service="automation-engine",
            stage="command_dedupe",
            status=dedupe_decision,
            message="Команда пропущена dedupe арбитражем",
            payload={
                "cmd": cmd,
                "node_uid": node_uid,
                "channel": channel,
                "cmd_id": effective_cmd_id,
                "dedupe_decision": dedupe_decision,
                "dedupe_reference_key": dedupe_reference_key,
                "dedupe_ttl_sec": dedupe_ttl_value,
            },
        )
        publish_success = True
        return True

    try:
        await command_bus._bind_dedupe_cmd_id(active_dedupe_state, effective_cmd_id)
        is_assigned = await command_bus._verify_node_zone_assignment(
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
        )
        if not is_assigned:
            COMMAND_VALIDATION_FAILED.labels(zone_id=str(zone_id), reason="node_zone_mismatch").inc()
            logger.error(
                "Zone %s: command validation failed - node_uid=%s is not assigned to this zone",
                zone_id,
                node_uid,
            )
            await record_simulation_event(
                zone_id,
                service="automation-engine",
                stage="command_validate",
                status="validation_failed",
                level="error",
                message="Команда отклонена: node_uid не привязан к зоне",
                payload={
                    "node_uid": node_uid,
                    "channel": channel,
                    "cmd": cmd,
                    "reason": "node_zone_mismatch",
                },
            )
            return False

        is_channel_compatible, channel_error = await command_bus._verify_command_channel_compatibility(
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
        )
        if not is_channel_compatible:
            await command_bus._handle_command_channel_compatibility_failure(
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                error_code=str(channel_error or "channel_command_mismatch"),
            )
            return False

        trace_id = get_trace_id()
        if effective_cmd_id:
            trace_id = effective_cmd_id

        effective_gh_uid = await command_bus._resolve_greenhouse_uid_for_zone(zone_id)
        payload = {
            "cmd": cmd,
            "greenhouse_uid": effective_gh_uid,
            "zone_id": zone_id,
            "node_uid": node_uid,
            "channel": channel,
            "source": command_bus.command_source,
            "params": params or {},
        }
        if effective_cmd_id:
            payload["cmd_id"] = effective_cmd_id
        if trace_id:
            payload["trace_id"] = trace_id

        headers = {"Content-Type": "application/json"}
        if command_bus.history_logger_token:
            headers["Authorization"] = f"Bearer {command_bus.history_logger_token}"
        if trace_id:
            headers["X-Trace-Id"] = trace_id

        async def _send_request():
            client = command_bus._get_client()
            if client is None:
                async with httpx.AsyncClient(timeout=command_bus.http_timeout) as temp_client:
                    return await temp_client.post(
                        f"{command_bus.history_logger_url}/commands",
                        json=payload,
                        headers=headers,
                    )
            return await client.post(
                f"{command_bus.history_logger_url}/commands",
                json=payload,
                headers=headers,
            )

        if command_bus.api_circuit_breaker:
            response = await command_bus.api_circuit_breaker.call(_send_request)
        else:
            response = await _send_request()

        latency = time.time() - start_time
        COMMAND_REST_LATENCY.observe(latency)

        if response.status_code == 200:
            try:
                result = response.json()
                published_cmd_id = result.get("data", {}).get("command_id")
                logger.debug(
                    "Zone %s: Command %s sent successfully via REST, cmd_id: %s",
                    zone_id,
                    cmd,
                    published_cmd_id,
                    extra={"zone_id": zone_id, "cmd_id": published_cmd_id, "trace_id": trace_id},
                )
                COMMANDS_SENT.labels(zone_id=str(zone_id), metric=cmd).inc()
                await record_simulation_event(
                    zone_id,
                    service="automation-engine",
                    stage="command_publish",
                    status="sent",
                    message="Команда отправлена через history-logger",
                    payload={
                        "cmd": cmd,
                        "cmd_id": published_cmd_id,
                        "channel": channel,
                        "node_uid": node_uid,
                        "source": command_bus.command_source,
                        "dedupe_decision": dedupe_decision,
                        "dedupe_reference_key": dedupe_reference_key,
                        "dedupe_ttl_sec": dedupe_ttl_value,
                    },
                )
                publish_success = True
                return True
            except Exception as exc:
                error_type = "json_decode_error"
                REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
                logger.error(
                    "Zone %s: Failed to parse response JSON: %s",
                    zone_id,
                    exc,
                    extra={"zone_id": zone_id, "trace_id": trace_id},
                )
                await record_simulation_event(
                    zone_id,
                    service="automation-engine",
                    stage="command_publish",
                    status="failed",
                    level="error",
                    message="Ошибка разбора ответа history-logger",
                    payload={
                        "cmd": cmd,
                        "channel": channel,
                        "node_uid": node_uid,
                        "error": str(exc),
                        "dedupe_decision": dedupe_decision,
                        "dedupe_reference_key": dedupe_reference_key,
                        "dedupe_ttl_sec": dedupe_ttl_value,
                    },
                )
                await command_bus._emit_publish_failure_alert(
                    code=INFRA_COMMAND_PUBLISH_RESPONSE_DECODE_ERROR,
                    zone_id=zone_id,
                    node_uid=node_uid,
                    channel=channel,
                    cmd=cmd,
                    error=str(exc),
                    error_type=error_type,
                )
                return False

        try:
            error_msg = response.text
        except Exception:
            error_msg = f"HTTP {response.status_code}"
        error_type = f"http_{response.status_code}"
        REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
        logger.error(
            "Zone %s: Failed to publish command %s via REST: %s - %s",
            zone_id,
            cmd,
            response.status_code,
            error_msg,
            extra={"zone_id": zone_id, "trace_id": trace_id},
        )
        await record_simulation_event(
            zone_id,
            service="automation-engine",
            stage="command_publish",
            status="failed",
            level="error",
            message="Ошибка отправки команды через history-logger",
            payload={
                "cmd": cmd,
                "channel": channel,
                "node_uid": node_uid,
                "http_status": response.status_code,
                "error": error_msg,
                "dedupe_decision": dedupe_decision,
                "dedupe_reference_key": dedupe_reference_key,
                "dedupe_ttl_sec": dedupe_ttl_value,
            },
        )
        await command_bus._emit_publish_failure_alert(
            code=INFRA_COMMAND_SEND_FAILED,
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            error=error_msg,
            error_type=error_type,
            http_status=response.status_code,
        )
        return False

    except httpx.TimeoutException as exc:
        error_type = "timeout"
        REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
        logger.error("Zone %s: Timeout publishing command %s via REST: %s", zone_id, cmd, exc, exc_info=True)
        await record_simulation_event(
            zone_id,
            service="automation-engine",
            stage="command_publish",
            status="failed",
            level="error",
            message="Таймаут отправки команды через history-logger",
            payload={
                "cmd": cmd,
                "channel": channel,
                "node_uid": node_uid,
                "error": str(exc),
                "dedupe_decision": dedupe_decision,
                "dedupe_reference_key": dedupe_reference_key,
                "dedupe_ttl_sec": dedupe_ttl_value,
            },
        )
        await command_bus._emit_publish_failure_alert(
            code=INFRA_COMMAND_TIMEOUT,
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            error=str(exc),
            error_type=error_type,
        )
        return False
    except httpx.RequestError as exc:
        error_type = "request_error"
        REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
        logger.error("Zone %s: Request error publishing command %s via REST: %s", zone_id, cmd, exc, exc_info=True)
        await record_simulation_event(
            zone_id,
            service="automation-engine",
            stage="command_publish",
            status="failed",
            level="error",
            message="Ошибка запроса при отправке команды через history-logger",
            payload={
                "cmd": cmd,
                "channel": channel,
                "node_uid": node_uid,
                "error": str(exc),
                "dedupe_decision": dedupe_decision,
                "dedupe_reference_key": dedupe_reference_key,
                "dedupe_ttl_sec": dedupe_ttl_value,
            },
        )
        await command_bus._emit_publish_failure_alert(
            code=INFRA_COMMAND_SEND_FAILED,
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            error=str(exc),
            error_type=error_type,
        )
        return False
    except Exception as exc:
        error_type = type(exc).__name__
        REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
        logger.error("Zone %s: Failed to publish command %s via REST: %s", zone_id, cmd, exc, exc_info=True)
        await record_simulation_event(
            zone_id,
            service="automation-engine",
            stage="command_publish",
            status="failed",
            level="error",
            message="Не удалось отправить команду через history-logger",
            payload={
                "cmd": cmd,
                "channel": channel,
                "node_uid": node_uid,
                "error": str(exc),
                "dedupe_decision": dedupe_decision,
                "dedupe_reference_key": dedupe_reference_key,
                "dedupe_ttl_sec": dedupe_ttl_value,
            },
        )
        await send_infra_exception_alert(
            error=exc,
            code=INFRA_UNKNOWN_ERROR,
            alert_type="Command Publish Unexpected Error",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="command_bus",
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
        )
        return False
    finally:
        await command_bus._complete_command_dedupe(active_dedupe_state, success=publish_success)
