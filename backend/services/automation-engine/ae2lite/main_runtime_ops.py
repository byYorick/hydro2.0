from __future__ import annotations

import asyncio
import math
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

import ae2lite.main_runtime_shared as shared
from common.infra_alerts import send_infra_alert, send_infra_exception_alert
from common.mqtt import MqttClient
from common.trace_context import inject_trace_id_header
from common.utils.time import utcnow
from infrastructure import CommandBus
from infrastructure.circuit_breaker import CircuitBreaker
from repositories import (
    GrowCycleRepository,
    InfrastructureRepository,
    NodeRepository,
    RecipeRepository,
    TelemetryRepository,
    ZoneRepository,
)
from services import ZoneAutomationService
from services.resilience_contract import (
    INFRA_CONFIG_FETCH_FAILED,
    INFRA_ZONE_FAILURE_RATE_HIGH,
    INFRA_ZONE_PROCESSING_FAILED,
)
from utils.logging_context import set_trace_id, set_zone_id


def validate_config(cfg: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not isinstance(cfg, dict):
        return False, "Config must be a dictionary"
    if "greenhouses" not in cfg:
        return False, "Config missing 'greenhouses' key"
    if not isinstance(cfg["greenhouses"], list):
        return False, "'greenhouses' must be a list"
    if len(cfg["greenhouses"]) == 0:
        return False, "'greenhouses' list is empty"
    gh = cfg["greenhouses"][0]
    if not isinstance(gh, dict):
        return False, "Greenhouse must be a dictionary"
    if "uid" not in gh:
        return False, "Greenhouse must have 'uid' field"
    if not isinstance(gh["uid"], str) or not gh["uid"]:
        return False, "Greenhouse 'uid' must be a non-empty string"
    return True, None


def extract_gh_uid_from_config(cfg: Dict[str, Any]) -> Optional[str]:
    gh_list = cfg.get("greenhouses", [])
    if gh_list and isinstance(gh_list, list):
        return gh_list[0].get("uid")
    return None


async def get_zone_recipe_and_targets(zone_id: int) -> Optional[Dict[str, Any]]:
    repo = RecipeRepository()
    return await repo.get_zone_recipe_and_targets(zone_id)


async def get_zone_telemetry_last(zone_id: int) -> Dict[str, Optional[float]]:
    repo = TelemetryRepository()
    return await repo.get_last_telemetry(zone_id)


async def get_zone_nodes(zone_id: int) -> Dict[str, Dict[str, Any]]:
    repo = NodeRepository()
    return await repo.get_zone_nodes(zone_id)


async def get_zone_capabilities(zone_id: int) -> Dict[str, bool]:
    repo = ZoneRepository()
    return await repo.get_zone_capabilities(zone_id)


async def publish_correction_command(
    mqtt: MqttClient,
    gh_uid: str,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    params: Optional[Dict[str, Any]] = None,
) -> bool:
    raise RuntimeError("publish_correction_command is removed; use CommandGateway/CommandBus path")


async def check_phase_transitions(zone_id: int):
    shared.logger.info(
        "check_phase_transitions is disabled; use GrowCyclePhase transitions via Laravel instead",
        extra={"zone_id": zone_id},
    )


def validate_zone_id(zone_id: Any) -> int:
    if not isinstance(zone_id, int):
        raise ValueError(f"zone_id must be int, got {type(zone_id)}")
    if zone_id <= 0:
        raise ValueError(f"zone_id must be positive, got {zone_id}")
    return zone_id


async def calculate_optimal_concurrency(total_zones: int, target_cycle_time: int, avg_zone_processing_time: float) -> int:
    if avg_zone_processing_time <= 0:
        return 5
    optimal = math.ceil((total_zones * avg_zone_processing_time) / target_cycle_time)
    return max(5, min(optimal, 50))


async def process_zones_parallel(
    zones: List[Dict[str, Any]],
    zone_service: ZoneAutomationService,
    max_concurrent: int = 5,
    simulation_clocks: Optional[Dict[int, Any]] = None,
    per_zone_timeout_sec: Optional[float] = None,
) -> Dict[str, Any]:
    results: Dict[str, Any] = {"total": len(zones), "success": 0, "failed": 0, "errors": []}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_tracking(zone_row: Dict[str, Any]) -> None:
        zone_id = zone_row.get("id")
        zone_name = zone_row.get("name", "unknown")
        sim_clock = simulation_clocks.get(zone_id) if simulation_clocks and zone_id else None
        set_zone_id(zone_id)
        set_trace_id()
        try:
            async with semaphore:
                try:
                    start = time.monotonic()
                    if per_zone_timeout_sec is not None and per_zone_timeout_sec > 0:
                        await asyncio.wait_for(zone_service.process_zone(zone_id, sim_clock=sim_clock), timeout=float(per_zone_timeout_sec))
                    else:
                        await zone_service.process_zone(zone_id, sim_clock=sim_clock)
                    duration = time.monotonic() - start
                    shared.ZONE_PROCESSING_TIME.observe(duration)
                    async with shared._processing_times_lock:
                        shared._processing_times.append(duration)
                        if len(shared._processing_times) > shared._MAX_SAMPLES:
                            shared._processing_times.pop(0)
                        shared._avg_processing_time = (
                            sum(shared._processing_times) / len(shared._processing_times)
                            if shared._processing_times
                            else 1.0
                        )
                    results["success"] += 1
                    shared.logger.debug("Zone %s processed successfully (%.2fs)", zone_id, duration)
                except Exception as exc:
                    results["failed"] += 1
                    error_info = {
                        "zone_id": zone_id,
                        "zone_name": zone_name,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "timestamp": utcnow().isoformat(),
                    }
                    results["errors"].append(error_info)
                    shared.ZONE_PROCESSING_ERRORS.labels(zone_id=str(zone_id), error_type=type(exc).__name__).inc()
                    from error_handler import handle_zone_error

                    handle_zone_error(zone_id, exc, {"action": "process_zone"})
                    shared.logger.error(
                        "Error processing zone %s: %s",
                        zone_id,
                        exc,
                        exc_info=True,
                        extra={"zone_id": zone_id, "zone_name": zone_name},
                    )
                    try:
                        await asyncio.wait_for(
                            send_infra_exception_alert(
                                error=exc,
                                code=INFRA_ZONE_PROCESSING_FAILED,
                                alert_type="Zone Processing Failed",
                                severity="error",
                                zone_id=zone_id,
                                service="automation-engine",
                                component="zone_processing",
                                details={"zone_name": zone_name},
                            ),
                            timeout=shared.ALERT_SEND_TIMEOUT_SECONDS,
                        )
                    except Exception as alert_error:
                        shared.logger.warning(
                            "Zone %s: Failed to send infra exception alert: %s",
                            zone_id,
                            alert_error,
                            extra={"zone_id": zone_id},
                        )
        finally:
            set_zone_id(None)

    await asyncio.gather(*[process_with_tracking(zone_row) for zone_row in zones])
    shared.logger.info(
        "Zone processing completed: %s/%s success, %s failed",
        results["success"],
        results["total"],
        results["failed"],
    )

    if results["failed"] > 0 and results["total"] > 0:
        failure_rate = results["failed"] / results["total"]
        if failure_rate > 0.1:
            severity = "warning" if failure_rate < 0.3 else "critical"
            shared.logger.warning(
                "High zone processing failure rate: %.1f%%",
                failure_rate * 100,
                extra={
                    "total": results["total"],
                    "failed": results["failed"],
                    "failure_rate": failure_rate,
                    "severity": severity,
                    "errors": results["errors"][:10],
                },
            )
            try:
                await asyncio.wait_for(
                    send_infra_alert(
                        code=INFRA_ZONE_FAILURE_RATE_HIGH,
                        alert_type="Zone Failure Rate High",
                        message=f"Высокая доля ошибок обработки зон: {failure_rate:.1%}",
                        severity=severity,
                        zone_id=None,
                        service="automation-engine",
                        component="zone_processing",
                        error_type="HighFailureRate",
                        details={
                            "total": results["total"],
                            "failed": results["failed"],
                            "failure_rate": failure_rate,
                            "sample_errors": results["errors"][:5],
                        },
                    ),
                    timeout=shared.ALERT_SEND_TIMEOUT_SECONDS,
                )
            except Exception as alert_error:
                shared.logger.warning("Failed to send high failure-rate infra alert: %s", alert_error)

    return results


async def check_and_correct_zone(
    zone_id: int,
    mqtt: MqttClient,
    gh_uid: str,
    cfg: Dict[str, Any],
    zone_repo: ZoneRepository,
    telemetry_repo: TelemetryRepository,
    node_repo: NodeRepository,
    recipe_repo: RecipeRepository,
):
    try:
        zone_id = validate_zone_id(zone_id)
    except ValueError as exc:
        shared.logger.error("Invalid zone_id: %s", exc)
        return

    if shared._command_bus is None:
        history_logger_url = os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
        history_logger_token = os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
        shared._command_bus = CommandBus(
            mqtt=None,
            gh_uid=gh_uid,
            history_logger_url=history_logger_url,
            history_logger_token=history_logger_token,
            enforce_node_zone_assignment=True,
        )
        await shared._command_bus.start()

    zone_service = ZoneAutomationService(
        zone_repo,
        telemetry_repo,
        node_repo,
        recipe_repo,
        GrowCycleRepository(),
        InfrastructureRepository(),
        shared._command_bus,
    )
    await zone_service.process_zone(zone_id)


async def fetch_full_config(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> Optional[Dict[str, Any]]:
    headers = inject_trace_id_header({"Authorization": f"Bearer {token}"} if token else {})
    max_retries = 3
    retry_delay = 2.0

    async def _fetch():
        response = await client.get(f"{base_url}/api/system/config/full", headers=headers, timeout=30.0)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        shared.CONFIG_FETCH_SUCCESS.inc()
        return data

    for attempt in range(max_retries):
        try:
            return await circuit_breaker.call(_fetch) if circuit_breaker else await _fetch()
        except httpx.HTTPStatusError as exc:
            error_type = f"http_{exc.response.status_code}"
            shared.CONFIG_FETCH_ERRORS.labels(error_type=error_type).inc()
            if exc.response.status_code == 401:
                await shared._emit_config_fetch_failure_alert(error_type=error_type, message="Config fetch failed: Unauthorized (401) - invalid or missing token")
                return None
            if exc.response.status_code == 429 and attempt < max_retries - 1:
                retry_after = exc.response.headers.get("Retry-After")
                try:
                    retry_after_sec = float(retry_after) if retry_after else retry_delay * (attempt + 1)
                except ValueError:
                    retry_after_sec = retry_delay * (attempt + 1)
                await asyncio.sleep(retry_after_sec)
                continue
            if exc.response.status_code >= 500 and attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            await shared._emit_config_fetch_failure_alert(error_type=error_type, message=f"Config fetch failed: HTTP {exc.response.status_code}")
            return None
        except httpx.TimeoutException:
            error_type = "timeout"
            shared.CONFIG_FETCH_ERRORS.labels(error_type=error_type).inc()
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            await shared._emit_config_fetch_failure_alert(error_type=error_type, message=f"Config fetch failed after {max_retries} attempts: timeout")
            return None
        except httpx.NetworkError as exc:
            error_type = "network_error"
            shared.CONFIG_FETCH_ERRORS.labels(error_type=error_type).inc()
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            await shared._emit_config_fetch_failure_alert(error_type=error_type, message=f"Config fetch failed after {max_retries} attempts: network error", details={"error_message": str(exc)})
            return None
        except Exception as exc:
            error_type = type(exc).__name__
            shared.CONFIG_FETCH_ERRORS.labels(error_type=error_type).inc()
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            await shared._emit_config_fetch_failure_alert(error_type=error_type, message=f"Config fetch failed after {max_retries} attempts: unexpected error", details={"error_message": str(exc)})
            return None
    return None


def signal_handler(signum, frame):
    shared.logger.info("Received signal %s, initiating graceful shutdown...", signum)
    shared._shutdown_event.set()


async def finish_current_zones(zone_service: ZoneAutomationService, active_zones: List[Dict[str, Any]]) -> None:
    if not active_zones:
        return
    shared.logger.info("Finishing processing of %s zones...", len(active_zones))
    await asyncio.sleep(2.0)


__all__ = [
    "calculate_optimal_concurrency",
    "check_and_correct_zone",
    "check_phase_transitions",
    "extract_gh_uid_from_config",
    "fetch_full_config",
    "finish_current_zones",
    "get_zone_capabilities",
    "get_zone_nodes",
    "get_zone_recipe_and_targets",
    "get_zone_telemetry_last",
    "process_zones_parallel",
    "publish_correction_command",
    "signal_handler",
    "validate_config",
    "validate_zone_id",
]
