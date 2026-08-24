from fastapi import FastAPI, Path
from fastapi import HTTPException, Request
from fastapi import Query, Response
from contextlib import asynccontextmanager
import asyncio
import hmac
import logging
import os
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from common.env import get_settings
from common.service_logs import send_service_log
from common.logging_setup import setup_standard_logging, install_exception_handlers
from common.trace_context import clear_trace_id, set_trace_id_from_headers
from status_probe import probe_node_status

# Настройка логирования
setup_standard_logging("mqtt-bridge")
install_exception_handlers("mqtt-bridge")
logger = logging.getLogger(__name__)

REQ_COUNTER = Counter("bridge_requests_total", "Bridge HTTP requests", ["path"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager для управления startup и shutdown событиями."""
    # Startup
    logger.info("Starting MQTT Bridge service")
    send_service_log(
        service="mqtt-bridge",
        level="info",
        message="MQTT Bridge service starting",
        context={"stage": "startup"},
    )

    yield

    # Shutdown
    logger.info("Stopping MQTT Bridge service")
    logger.info("MQTT Bridge service stopped")
    send_service_log(
        service="mqtt-bridge",
        level="info",
        message="MQTT Bridge service stopped",
        context={"stage": "shutdown"},
    )


app = FastAPI(title="MQTT Bridge", version="0.1.3", lifespan=lifespan)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = set_trace_id_from_headers(request.headers, fallback_generate=True)
    try:
        response = await call_next(request)
    finally:
        clear_trace_id()
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return response


def _auth(request: Request):
    """
    Проверка токена аутентификации.
    В production токен обязателен всегда, без исключений для внутренних IP.
    В dev окружении разрешаем внутренние запросы без токена только если токен не настроен.

    S1.4 (AUDIT_2026_05_28_BUGFIX_PLAN): сравнение токена через
    `hmac.compare_digest` (timing-safe), чтобы исключить side-channel при
    подборе токена через измерение времени ответа.
    """
    s = get_settings()

    # Проверяем окружение
    app_env = os.getenv("APP_ENV", "").lower().strip()
    is_prod = app_env in ("production", "prod") and app_env != ""

    # В production токен обязателен всегда
    if is_prod:
        if not s.bridge_api_token:
            logger.error("PY_API_TOKEN must be set in production environment")
            raise HTTPException(
                status_code=500,
                detail="Server configuration error: API token not configured"
            )

        token = request.headers.get("Authorization", "")
        expected = f"Bearer {s.bridge_api_token}"
        if not token or not hmac.compare_digest(token, expected):
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(
                f"Invalid or missing token in production: token_present={bool(token)}, "
                f"client_ip={client_ip}"
            )
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: token required in production"
            )
        return

    # В dev окружении: если токен настроен, он обязателен
    # Если токен не настроен, разрешаем только localhost (не все внутренние IP)
    if s.bridge_api_token:
        token = request.headers.get("Authorization", "")
        expected = f"Bearer {s.bridge_api_token}"
        if not token or not hmac.compare_digest(token, expected):
            logger.warning(f"Invalid or missing token: token_present={bool(token)}")
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: invalid or missing token"
            )
        return
    
    # Dev окружение без токена: разрешаем только localhost
    client_ip = request.client.host if request.client else ""
    is_localhost = client_ip in ["127.0.0.1", "::1", "localhost"]
    
    if not is_localhost:
        logger.warning(
            f"Rejecting non-localhost request without token in dev: client_ip={client_ip}. "
            f"Set PY_API_TOKEN for production or use localhost in dev."
        )
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: token required for non-localhost requests. Set PY_API_TOKEN or use localhost."
        )
    
    logger.debug(f"Allowing localhost request without token (dev mode): client_ip={client_ip}")


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/bridge/nodes/{node_uid}/live-status")
async def live_node_status(
    request: Request,
    node_uid: str = Path(..., min_length=1),
    greenhouse_uid: str = Query(..., min_length=1),
    zone_segment: str = Query(..., min_length=1),
    timeout_sec: float = Query(5.0, ge=1.0, le=15.0),
):
    """
    Проверка доступности узла по MQTT: подписка на retained/online status,
    без чтения состояния из БД Laravel.
    """
    _auth(request)
    REQ_COUNTER.labels(path="/bridge/nodes/{node_uid}/live-status").inc()

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: probe_node_status(
                greenhouse_uid.strip(),
                zone_segment.strip(),
                node_uid,
                float(timeout_sec),
            ),
        )
    except Exception as e:
        logger.error("live_node_status probe failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"live_status_probe_failed: {e!s}") from e

    return {"status": "ok", "data": result}
