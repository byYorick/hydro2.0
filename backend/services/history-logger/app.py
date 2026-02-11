import asyncio
import logging
import signal
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

import state
from command_routes import router as command_router
from common.alert_queue import retry_worker as alert_retry_worker
from common.command_status_queue import retry_worker as command_retry_worker
from common.env import get_settings
from common.http_client_pool import close_http_client as close_unified_http_client
from common.mqtt import get_mqtt_client
from common.redis_queue import TelemetryQueue, close_redis_client
from common.service_logs import send_service_log
from common.trace_context import clear_trace_id, set_trace_id_from_headers
from ingest_routes import router as ingest_router
from mqtt_handlers import (
    handle_command_response,
    handle_config_report,
    handle_diagnostics,
    handle_error,
    handle_heartbeat,
    handle_lwt,
    handle_node_hello,
    handle_status,
    handle_time_request,
    monitor_offline_nodes,
)
from system_routes import router as system_router
from telemetry_processing import handle_telemetry, process_realtime_queue, process_telemetry_queue

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager для управления startup и shutdown событиями."""
    logger.info("Starting History Logger service")
    send_service_log(
        service="history-logger",
        level="info",
        message="History Logger service starting",
        context={"stage": "startup"},
    )

    if state.telemetry_queue is None:
        state.telemetry_queue = TelemetryQueue()

    task = asyncio.create_task(process_telemetry_queue())
    state.background_tasks.append(task)

    realtime_task = asyncio.create_task(process_realtime_queue())
    state.background_tasks.append(realtime_task)

    command_retry_task = asyncio.create_task(
        command_retry_worker(interval=30.0, shutdown_event=state.shutdown_event)
    )
    state.background_tasks.append(command_retry_task)

    alert_retry_task = asyncio.create_task(
        alert_retry_worker(interval=30.0, shutdown_event=state.shutdown_event)
    )
    state.background_tasks.append(alert_retry_task)

    offline_task = asyncio.create_task(monitor_offline_nodes())
    state.background_tasks.append(offline_task)

    mqtt = await get_mqtt_client()
    await mqtt.subscribe("hydro/+/+/+/+/telemetry", handle_telemetry)
    await mqtt.subscribe("hydro/+/+/+/heartbeat", handle_heartbeat)
    await mqtt.subscribe("hydro/+/+/+/status", handle_status)
    await mqtt.subscribe("hydro/+/+/+/lwt", handle_lwt)
    await mqtt.subscribe("hydro/+/+/+/diagnostics", handle_diagnostics)
    await mqtt.subscribe("hydro/+/+/+/error", handle_error)
    await mqtt.subscribe("hydro/node_hello", handle_node_hello)
    await mqtt.subscribe("hydro/+/+/+/node_hello", handle_node_hello)
    await mqtt.subscribe("hydro/+/+/+/config_report", handle_config_report)
    await mqtt.subscribe("hydro/+/+/+/+/command_response", handle_command_response)
    await mqtt.subscribe("hydro/time/request", handle_time_request)

    logger.info("History Logger service started")
    logger.info(
        "Subscribed to MQTT topics: hydro/+/+/+/+/telemetry, hydro/+/+/+/heartbeat, "
        "hydro/+/+/+/status, hydro/+/+/+/lwt, hydro/+/+/+/diagnostics, "
        "hydro/+/+/+/error, hydro/node_hello, hydro/+/+/+/node_hello, "
        "hydro/+/+/+/config_report, "
        "hydro/+/+/+/+/command_response"
    )

    yield

    logger.info("Shutting down History Logger service")

    state.shutdown_event.set()

    s = get_settings()
    if state.background_tasks:
        logger.info(
            f"Waiting for {len(state.background_tasks)} background tasks to complete..."
        )
        try:
            await asyncio.wait_for(
                asyncio.gather(*state.background_tasks, return_exceptions=True),
                timeout=s.shutdown_timeout_sec,
            )
            logger.info("All background tasks completed")
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for background tasks, forcing shutdown")
            for task in state.background_tasks:
                if not task.done():
                    task.cancel()

    await asyncio.sleep(s.shutdown_wait_sec)

    await close_redis_client()
    await close_unified_http_client()

    logger.info("History Logger service stopped")
    send_service_log(
        service="history-logger",
        level="info",
        message="History Logger service stopped",
        context={"stage": "shutdown"},
    )


async def log_requests(request: Request, call_next):
    """Логирование всех входящих HTTP запросов для диагностики."""
    trace_id = set_trace_id_from_headers(request.headers, fallback_generate=True)
    start_time = time.time()

    client_ip = request.client.host if request.client else "unknown"
    full_url = str(request.url)
    logger.info(
        "[HTTP_REQUEST] %s %s from %s, full_url=%s, headers_count=%s, has_body=%s",
        request.method,
        request.url.path,
        client_ip,
        full_url,
        len(request.headers),
        request.headers.get("content-length", "0") != "0",
    )

    auth_header = request.headers.get("Authorization", "")
    if auth_header:
        logger.debug("[HTTP_REQUEST] Authorization header present")
    else:
        logger.debug("[HTTP_REQUEST] No Authorization header")

    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(
            "[HTTP_REQUEST] %s %s -> %s (%.3fs)",
            request.method,
            request.url.path,
            response.status_code,
            process_time,
        )
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            "[HTTP_REQUEST] %s %s -> ERROR: %s (%.3fs)",
            request.method,
            request.url.path,
            e,
            process_time,
            exc_info=True,
        )
        raise
    finally:
        clear_trace_id()


def create_app() -> FastAPI:
    app = FastAPI(title="History Logger", lifespan=lifespan)
    app.middleware("http")(log_requests)
    app.include_router(system_router)
    app.include_router(command_router)
    app.include_router(ingest_router)
    return app


app = create_app()


def setup_signal_handlers() -> None:
    """Настройка обработчиков сигналов для graceful shutdown."""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        state.shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
