from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import ae2lite.main_runtime_shared as shared
from ae2lite.main_runtime_ops import finish_current_zones


async def graceful_shutdown(
    *,
    api_server: Any,
    api_task: asyncio.Task,
    health_task: asyncio.Task,
    active_zones: List[Dict[str, Any]],
    mqtt: Any,
    automation_settings: Any,
) -> None:
    shared.logger.info("Graceful shutdown initiated")

    try:
        api_server.should_exit = True
        await asyncio.wait_for(api_task, timeout=10.0)
    except asyncio.TimeoutError:
        shared.logger.warning("Timeout waiting for API server shutdown")
        api_task.cancel()
        try:
            await api_task
        except asyncio.CancelledError:
            pass
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        shared.logger.warning("Failed to stop API server cleanly: %s", exc, exc_info=True)

    health_task.cancel()
    try:
        await health_task
    except asyncio.CancelledError:
        pass

    if shared._zone_service and active_zones:
        try:
            await asyncio.wait_for(finish_current_zones(shared._zone_service, active_zones), timeout=30.0)
        except asyncio.TimeoutError:
            shared.logger.warning("Timeout waiting for zones to finish")

    if shared._zone_service:
        try:
            await asyncio.wait_for(shared._zone_service.save_all_pid_states(), timeout=10.0)
        except asyncio.TimeoutError:
            shared.logger.warning("Timeout saving PID state")
        except Exception as exc:
            shared.logger.error("Error saving PID state: %s", exc, exc_info=True)
        try:
            shared._save_zone_runtime_state_snapshot(shared._zone_service, automation_settings)
        except Exception as exc:
            shared.logger.warning("Failed to save runtime snapshot: %s", exc, exc_info=True)

    if shared._command_tracker:
        try:
            await shared._command_tracker.stop_polling()
        except Exception as exc:
            shared.logger.warning("Failed to stop command polling: %s", exc)

    if shared._command_bus:
        try:
            await shared._command_bus.stop()
        except Exception as exc:
            shared.logger.warning("Failed to stop CommandBus: %s", exc)

    try:
        mqtt.stop()
    except Exception as exc:
        shared.logger.warning("Error stopping MQTT: %s", exc)

    shared.logger.info("Graceful shutdown completed")


__all__ = ["graceful_shutdown"]
