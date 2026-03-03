from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

import httpx

import ae2lite.main_runtime_shared as shared
from ae2lite.effective_targets_notify_runtime import (
    start_effective_targets_notify_listener,
    stop_effective_targets_notify_listener,
)
from ae2lite.main_runtime_ops import (
    calculate_optimal_concurrency,
    extract_gh_uid_from_config,
    fetch_full_config,
    process_zones_parallel,
    validate_config,
)
from common.infra_alerts import send_infra_alert, send_infra_exception_alert
from common.simulation_clock import get_simulation_clocks
from common.utils.time import utcnow
from error_handler import handle_automation_error
from exceptions import InvalidConfigurationError
from infrastructure import CommandBus
from infrastructure.circuit_breaker import CircuitBreakerOpenError
from infrastructure.command_audit import CommandAudit
from repositories import (
    GrowCycleRepository,
    InfrastructureRepository,
    NodeRepository,
    RecipeRepository,
    TelemetryRepository,
    ZoneRepository,
)
from repositories.laravel_api_repository import LaravelApiRepository
from services.resilience_contract import (
    INFRA_API_CIRCUIT_OPEN_NO_CACHE,
    INFRA_AUTOMATION_LOOP_ERROR,
    INFRA_CONFIG_FETCH_UNAVAILABLE,
    INFRA_CONFIG_MISSING_GREENHOUSE_UID,
    INFRA_DB_CIRCUIT_OPEN,
)
from services.zone_automation_service import ZoneAutomationService
from utils.system_state_logger import log_system_state
from utils.zone_prioritizer import prioritize_zones


async def _get_config_with_cache(
    *,
    client: httpx.AsyncClient,
    laravel_api_url: str,
    laravel_api_token: str,
    api_circuit_breaker: Any,
    automation_settings: Any,
    last_config: Optional[Dict[str, Any]],
    last_config_ts: float,
    now_mono: float,
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], float, bool]:
    cfg: Optional[Dict[str, Any]] = None
    used_cached = False
    next_last_config = last_config
    next_last_config_ts = last_config_ts

    if last_config and (now_mono - last_config_ts) < automation_settings.CONFIG_FETCH_MIN_INTERVAL_SECONDS:
        return last_config, next_last_config, next_last_config_ts, True

    try:
        cfg = await fetch_full_config(client, laravel_api_url, laravel_api_token, api_circuit_breaker)
    except CircuitBreakerOpenError:
        if last_config:
            shared.logger.warning("API Circuit Breaker is OPEN, using cached config")
            return last_config, next_last_config, now_mono, True

        shared.logger.warning("API Circuit Breaker is OPEN, no cached config available")
        if shared._should_emit_config_unavailable_alert(utcnow()):
            await send_infra_alert(
                code=INFRA_API_CIRCUIT_OPEN_NO_CACHE,
                alert_type="API Circuit Open Without Cache",
                message="API circuit breaker is open and no cached config is available",
                severity="critical",
                zone_id=None,
                service="automation-engine",
                component="config_fetch",
                error_type="CircuitBreakerOpenError",
                details={"throttle_seconds": shared._CONFIG_UNAVAILABLE_ALERT_THROTTLE_SECONDS},
            )
        await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
        return None, next_last_config, next_last_config_ts, False

    if not cfg:
        if last_config:
            shared.logger.warning("Config fetch returned None, using cached config")
            return last_config, next_last_config, now_mono, True

        shared.logger.warning("Config fetch returned None, sleeping before retry")
        if shared._should_emit_config_unavailable_alert(utcnow()):
            await send_infra_alert(
                code=INFRA_CONFIG_FETCH_UNAVAILABLE,
                alert_type="Config Unavailable",
                message="Config fetch returned empty response and no cached config is available",
                severity="error",
                zone_id=None,
                service="automation-engine",
                component="config_fetch",
                error_type="ConfigUnavailable",
                details={"throttle_seconds": shared._CONFIG_UNAVAILABLE_ALERT_THROTTLE_SECONDS},
            )
        await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
        return None, next_last_config, next_last_config_ts, False

    next_last_config = cfg
    next_last_config_ts = now_mono
    return cfg, next_last_config, next_last_config_ts, used_cached


async def _partition_zones_by_single_writer(zones: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[int]]:
    if not zones:
        shared._scheduler_writer_active_since.clear()
        return [], []

    if not shared._AE2_RUNTIME_SINGLE_WRITER_ENFORCE or shared._AE2_FALLBACK_LOOP_WRITER_ENABLED:
        shared._scheduler_writer_active_since.clear()
        return zones, []

    now_mono = time.monotonic()
    current_zone_ids: set[int] = set()
    gated_zone_ids: List[int] = []

    for zone in zones:
        raw_zone_id = zone.get("id")
        try:
            zone_id = int(raw_zone_id)
        except Exception:
            continue
        current_zone_ids.add(zone_id)

        scheduler_writer_active = await shared._is_scheduler_single_writer_active(zone_id=zone_id)
        if not scheduler_writer_active:
            shared._scheduler_writer_active_since.pop(zone_id, None)
            continue

        active_since = shared._scheduler_writer_active_since.get(zone_id)
        if active_since is None:
            active_since = now_mono
            shared._scheduler_writer_active_since[zone_id] = now_mono
        elapsed = now_mono - active_since
        if elapsed >= shared._SCHEDULER_WRITER_WATCHDOG_TIMEOUT_SEC:
            shared.logger.warning(
                "Scheduler writer watchdog expired for zone_id=%s after %.0fs (limit %.0fs), "
                "forcing fallback zone processing",
                zone_id,
                elapsed,
                shared._SCHEDULER_WRITER_WATCHDOG_TIMEOUT_SEC,
            )
            shared._scheduler_writer_active_since.pop(zone_id, None)
            continue

        gated_zone_ids.append(zone_id)

    for tracked_zone_id in list(shared._scheduler_writer_active_since.keys()):
        if tracked_zone_id not in current_zone_ids:
            shared._scheduler_writer_active_since.pop(tracked_zone_id, None)

    if gated_zone_ids and shared._should_log_scheduler_single_writer_skip(utcnow()):
        shared.logger.info(
            "Scheduler single-writer active for zones=%s: continuous loop side-effects are gated "
            "(watchdog %.0fs, set AE2_FALLBACK_LOOP_WRITER_ENABLED=true to allow fallback writer)",
            sorted(gated_zone_ids),
            shared._SCHEDULER_WRITER_WATCHDOG_TIMEOUT_SEC,
        )

    gated_zone_ids_set = set(gated_zone_ids)
    zones_for_processing: List[Dict[str, Any]] = []
    for zone in zones:
        try:
            zone_id = int(zone.get("id"))
        except Exception:
            zones_for_processing.append(zone)
            continue
        if zone_id not in gated_zone_ids_set:
            zones_for_processing.append(zone)

    return zones_for_processing, gated_zone_ids


async def run_runtime_cycle(
    *,
    client: httpx.AsyncClient,
    laravel_api_url: str,
    laravel_api_token: str,
    automation_settings: Any,
    db_circuit_breaker: Any,
    api_circuit_breaker: Any,
    mqtt_circuit_breaker: Any,
    command_api_circuit_breaker: Any,
    command_validator: Any,
    pid_state_manager: Any,
) -> List[Dict[str, Any]]:
    active_zones: List[Dict[str, Any]] = []
    laravel_api_repo = LaravelApiRepository()
    last_config: Optional[Dict[str, Any]] = None
    last_config_ts = 0.0
    next_system_state_log_at = time.monotonic() + shared.SYSTEM_STATE_LOG_INTERVAL_SEC
    signal_listener = None
    signal_listener_task = None

    signal_listener, signal_listener_task = await start_effective_targets_notify_listener(
        invalidate_cache_fn=laravel_api_repo.invalidate_effective_targets_cache,
        shutdown_event=shared._shutdown_event,
        logger=shared.logger,
    )

    try:
        while not shared._shutdown_event.is_set():
            simulation_clocks: Dict[int, Any] = {}
            skip_cycle_sleep = False
            try:
                now_mono = time.monotonic()
                cfg, last_config, last_config_ts, _ = await _get_config_with_cache(
                    client=client,
                    laravel_api_url=laravel_api_url,
                    laravel_api_token=laravel_api_token,
                    api_circuit_breaker=api_circuit_breaker,
                    automation_settings=automation_settings,
                    last_config=last_config,
                    last_config_ts=last_config_ts,
                    now_mono=now_mono,
                )
                if not cfg:
                    continue

                is_valid, error_msg = validate_config(cfg)
                if not is_valid:
                    handle_automation_error(InvalidConfigurationError(error_msg, cfg), {"action": "config_validation"})
                    await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
                    continue

                gh_uid = extract_gh_uid_from_config(cfg)
                if not gh_uid:
                    shared.logger.warning("No greenhouse UID found in config, sleeping before retry")
                    if shared._should_emit_missing_gh_uid_alert(utcnow()):
                        await send_infra_alert(
                            code=INFRA_CONFIG_MISSING_GREENHOUSE_UID,
                            alert_type="Config Missing Greenhouse UID",
                            message="Config does not contain greenhouse UID",
                            severity="error",
                            zone_id=None,
                            service="automation-engine",
                            component="config_validation",
                            error_type="MissingGreenhouseUid",
                            details={"throttle_seconds": shared._MISSING_GH_UID_ALERT_THROTTLE_SECONDS},
                        )
                    await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
                    continue

                zone_repo = ZoneRepository()
                telemetry_repo = TelemetryRepository(db_circuit_breaker=db_circuit_breaker)
                node_repo = NodeRepository()
                recipe_repo = RecipeRepository(db_circuit_breaker=db_circuit_breaker)
                grow_cycle_repo = GrowCycleRepository(laravel_api_repo=laravel_api_repo, db_circuit_breaker=db_circuit_breaker)
                infrastructure_repo = InfrastructureRepository(db_circuit_breaker=db_circuit_breaker)

                if shared._command_bus is None:
                    history_logger_url = os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
                    history_logger_token = os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
                    shared._command_bus = CommandBus(
                        mqtt=None,
                        gh_uid=gh_uid,
                        history_logger_url=history_logger_url,
                        history_logger_token=history_logger_token,
                        command_validator=command_validator,
                        command_tracker=shared._command_tracker,
                        command_audit=CommandAudit(),
                        api_circuit_breaker=command_api_circuit_breaker,
                        enforce_node_zone_assignment=True,
                    )
                    await shared._command_bus.start()
                    shared.logger.info("CommandBus initialized with long-lived HTTP client")

                try:
                    from api import set_command_bus

                    set_command_bus(shared._command_bus, gh_uid, loop_id=id(asyncio.get_running_loop()))
                except ImportError:
                    shared.logger.warning("API module not available, scheduler endpoint will not work")

                if shared._zone_service is None:
                    shared._zone_service = ZoneAutomationService(
                        zone_repo,
                        telemetry_repo,
                        node_repo,
                        recipe_repo,
                        grow_cycle_repo,
                        infrastructure_repo,
                        shared._command_bus,
                        pid_state_manager,
                    )
                    try:
                        from api import set_zone_service

                        set_zone_service(shared._zone_service, loop_id=id(asyncio.get_running_loop()))
                    except ImportError:
                        shared.logger.warning("API module not available, scheduler task executor fallback is disabled")

                if shared._zone_service is not None and not shared._runtime_state_restored:
                    shared._runtime_state_restored = shared._restore_zone_runtime_state_snapshot(shared._zone_service, automation_settings)

                try:
                    zones = await db_circuit_breaker.call(zone_repo.get_active_zones)
                except CircuitBreakerOpenError:
                    shared.logger.warning("Database Circuit Breaker is OPEN, skipping zone processing")
                    now = utcnow()
                    if shared._should_emit_db_circuit_open_alert(now):
                        await send_infra_alert(
                            code=INFRA_DB_CIRCUIT_OPEN,
                            alert_type="Database Circuit Breaker Open",
                            message="Database circuit breaker is OPEN, zone processing is skipped",
                            severity="critical",
                            zone_id=None,
                            service="automation-engine",
                            component="main_loop",
                            error_type="CircuitBreakerOpenError",
                            details={
                                "throttle_seconds": shared._DB_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS,
                                "detected_at": now.isoformat(),
                            },
                        )
                    await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
                    continue

                zones = prioritize_zones(zones)
                active_zones = zones
                zone_ids = [zone.get("id") for zone in zones if zone.get("id")]
                if zone_ids:
                    simulation_clocks = await get_simulation_clocks(zone_ids)

                if zones:
                    zones_for_processing, _ = await _partition_zones_by_single_writer(zones)
                    if zones_for_processing:
                        if automation_settings.ADAPTIVE_CONCURRENCY:
                            optimal_concurrency = await calculate_optimal_concurrency(
                                total_zones=len(zones_for_processing),
                                target_cycle_time=automation_settings.TARGET_CYCLE_TIME_SEC,
                                avg_zone_processing_time=shared._avg_processing_time,
                            )
                            shared.OPTIMAL_CONCURRENCY.set(optimal_concurrency)
                            max_concurrent = optimal_concurrency
                        else:
                            max_concurrent = automation_settings.MAX_CONCURRENT_ZONES

                        results = await process_zones_parallel(
                            zones_for_processing,
                            shared._zone_service,
                            max_concurrent=max_concurrent,
                            simulation_clocks=simulation_clocks,
                            per_zone_timeout_sec=shared.AE_ZONE_PROCESS_TIMEOUT_SEC,
                        )

                        if results["failed"] > 0:
                            shared.logger.warning(
                                "Zone processing completed with errors: %s/%s success, %s failed",
                                results["success"],
                                results["total"],
                                results["failed"],
                            )

                    now_mono = time.monotonic()
                    if now_mono >= next_system_state_log_at:
                        await log_system_state(
                            shared._zone_service,
                            zones,
                            shared._command_tracker,
                            db_circuit_breaker,
                            api_circuit_breaker,
                            mqtt_circuit_breaker,
                        )
                        next_system_state_log_at = now_mono + shared.SYSTEM_STATE_LOG_INTERVAL_SEC
            except KeyboardInterrupt:
                shared.logger.info("Received interrupt signal, shutting down")
                shared._shutdown_event.set()
                break
            except Exception as exc:
                handle_automation_error(exc, {"action": "main_loop"})
                await send_infra_exception_alert(
                    error=exc,
                    code=INFRA_AUTOMATION_LOOP_ERROR,
                    alert_type="Automation Loop Error",
                    severity="error",
                    zone_id=None,
                    service="automation-engine",
                    component="main_loop",
                )
                await asyncio.sleep(automation_settings.CONFIG_FETCH_RETRY_SLEEP_SECONDS)
                skip_cycle_sleep = True

            if shared._shutdown_event.is_set():
                break
            if skip_cycle_sleep:
                continue

            sleep_seconds = automation_settings.MAIN_LOOP_SLEEP_SECONDS
            if simulation_clocks:
                try:
                    max_scale = max(clock.time_scale for clock in simulation_clocks.values())
                    if max_scale > 1:
                        sleep_seconds = max(1.0, sleep_seconds / max_scale)
                except ValueError:
                    pass
            await asyncio.sleep(sleep_seconds)
    finally:
        await stop_effective_targets_notify_listener(
            listener=signal_listener,
            task=signal_listener_task,
        )

    return active_zones


__all__ = ["run_runtime_cycle", "_partition_zones_by_single_writer"]
