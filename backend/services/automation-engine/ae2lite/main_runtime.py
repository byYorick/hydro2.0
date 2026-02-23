from __future__ import annotations

import asyncio
import os
import signal
from typing import Any, Dict, List, Optional

import httpx
from prometheus_client import start_http_server

import ae2lite.main_runtime_shared as shared
from ae2lite.main_runtime_cycle import run_runtime_cycle
from ae2lite.main_runtime_ops import (
    calculate_optimal_concurrency,
    check_and_correct_zone,
    check_phase_transitions,
    extract_gh_uid_from_config,
    fetch_full_config,
    get_zone_capabilities,
    get_zone_nodes,
    get_zone_recipe_and_targets,
    get_zone_telemetry_last,
    process_zones_parallel,
    publish_correction_command,
    signal_handler,
    validate_config,
    validate_zone_id,
)
from ae2lite.main_runtime_shutdown import graceful_shutdown
from common.env import get_settings
from common.infra_alerts import send_infra_alert, send_infra_exception_alert
from common.mqtt import MqttClient
from common.service_logs import send_service_log
from common.utils.time import utcnow
from infrastructure.circuit_breaker import CircuitBreaker
from infrastructure.command_tracker import CommandTracker
from infrastructure.command_validator import CommandValidator
from infrastructure.system_health import SystemHealthMonitor
from services.pid_state_manager import PidStateManager
from services.resilience_contract import INFRA_HEALTH_CHECK_FAILED, INFRA_SYSTEM_UNHEALTHY


def _register_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def _build_health_loop(health_monitor: SystemHealthMonitor):
    async def health_check_loop():
        while not shared._shutdown_event.is_set():
            try:
                health = await health_monitor.check_health()
                if health["status"] != "healthy":
                    shared.logger.warning("System health: %s", health["status"], extra=health)
                    now = utcnow()
                    if shared._should_emit_health_unhealthy_alert(now):
                        await send_infra_alert(
                            code=INFRA_SYSTEM_UNHEALTHY,
                            alert_type="System Health Degraded",
                            message=f"Automation system health is '{health['status']}'",
                            severity="error",
                            zone_id=None,
                            service="automation-engine",
                            component="health_monitor",
                            error_type="Unhealthy",
                            details={
                                "health": health,
                                "throttle_seconds": shared._HEALTH_UNHEALTHY_ALERT_THROTTLE_SECONDS,
                            },
                        )
            except Exception as exc:
                shared.logger.error("Health check failed: %s", exc, exc_info=True)
                now = utcnow()
                if shared._should_emit_health_check_failed_alert(now):
                    await send_infra_exception_alert(
                        error=exc,
                        code=INFRA_HEALTH_CHECK_FAILED,
                        alert_type="Health Check Failed",
                        severity="error",
                        zone_id=None,
                        service="automation-engine",
                        component="health_monitor",
                        details={"throttle_seconds": shared._HEALTH_CHECK_FAILED_ALERT_THROTTLE_SECONDS},
                    )
            await asyncio.sleep(30)

    return health_check_loop


async def main():
    _register_signal_handlers()
    s = get_settings()
    automation_settings = shared.get_automation_settings()

    start_http_server(automation_settings.PROMETHEUS_PORT)

    import uvicorn
    from api import app as api_app

    api_port = int(os.getenv("AUTOMATION_ENGINE_API_PORT", "9405"))
    api_server = uvicorn.Server(
        uvicorn.Config(api_app, host="0.0.0.0", port=api_port, log_level="info", access_log=False)
    )
    api_task = asyncio.create_task(api_server.serve(), name="automation_api_server")

    send_service_log(
        service="automation-engine",
        level="info",
        message="Automation Engine service started",
        context={"prometheus_port": automation_settings.PROMETHEUS_PORT, "api_port": api_port},
    )

    mqtt = MqttClient(client_id_suffix="-auto")
    mqtt.start()

    db_circuit_breaker = CircuitBreaker("database", failure_threshold=5, timeout=60.0)
    api_circuit_breaker = CircuitBreaker("laravel_api", failure_threshold=5, timeout=60.0)
    command_api_circuit_breaker = CircuitBreaker("history_logger_api", failure_threshold=5, timeout=30.0)
    mqtt_circuit_breaker = CircuitBreaker("mqtt", failure_threshold=3, timeout=30.0)

    shared._command_tracker = CommandTracker(command_timeout=300, poll_interval=5)
    await shared._command_tracker.restore_pending_commands()
    await shared._command_tracker.start_polling()

    command_validator = CommandValidator()
    pid_state_manager = PidStateManager()
    health_monitor = SystemHealthMonitor(mqtt, db_circuit_breaker, api_circuit_breaker, mqtt_circuit_breaker)
    health_task = asyncio.create_task(_build_health_loop(health_monitor)())

    active_zones: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient() as client:
            active_zones = await run_runtime_cycle(
                client=client,
                laravel_api_url=s.laravel_api_url,
                laravel_api_token=s.laravel_api_token,
                automation_settings=automation_settings,
                db_circuit_breaker=db_circuit_breaker,
                api_circuit_breaker=api_circuit_breaker,
                mqtt_circuit_breaker=mqtt_circuit_breaker,
                command_api_circuit_breaker=command_api_circuit_breaker,
                command_validator=command_validator,
                pid_state_manager=pid_state_manager,
            )
    finally:
        await graceful_shutdown(
            api_server=api_server,
            api_task=api_task,
            health_task=health_task,
            active_zones=active_zones,
            mqtt=mqtt,
            automation_settings=automation_settings,
        )


__all__ = [
    "main",
    "calculate_optimal_concurrency",
    "check_and_correct_zone",
    "check_phase_transitions",
    "extract_gh_uid_from_config",
    "fetch_full_config",
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
