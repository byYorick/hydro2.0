from fastapi import FastAPI, Path
from fastapi import HTTPException, Request
from fastapi import Body, Query, Response
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from typing import Optional
import hashlib
import hmac
from common.hmac_utils import canonical_json_payload
import asyncio
import logging
import os
import time
from publisher import Publisher
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from common.env import get_settings
from common.db import fetch
from common.simulation_events import record_simulation_event
from common.service_logs import send_service_log
from common.logging_setup import setup_standard_logging, install_exception_handlers
from common.trace_context import clear_trace_id, get_trace_id, set_trace_id, set_trace_id_from_headers
from status_probe import probe_node_status

# Настройка логирования
setup_standard_logging("mqtt-bridge")
install_exception_handlers("mqtt-bridge")
logger = logging.getLogger(__name__)

REQ_COUNTER = Counter("bridge_requests_total", "Bridge HTTP requests", ["path"])

# Глобальная переменная для Publisher
publisher: Optional[Publisher] = None


def _maybe_attach_hmac(payload: dict, cmd: str, ts: Optional[int], sig: Optional[str]) -> None:
    if sig and ts is None:
        raise ValueError("sig requires ts")
    secret = get_settings().node_default_secret
    if ts is None and sig is None:
        if not secret:
            return
        ts = int(time.time())
    elif ts is not None and sig is None and not secret:
        raise ValueError("sig requires node_default_secret")

    if ts is not None:
        payload["ts"] = ts
    if sig is None and secret:
        payload_str = canonical_json_payload(payload)
        sig = hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
    if sig:
        payload["sig"] = sig


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager для управления startup и shutdown событиями."""
    global publisher
    
    # Startup
    logger.info("Starting MQTT Bridge service")
    send_service_log(
        service="mqtt-bridge",
        level="info",
        message="MQTT Bridge service starting",
        context={"stage": "startup"},
    )
    
    try:
        publisher = Publisher()
        publisher.start()  # Запускаем подключение и фоновые ретраи
        logger.info("Publisher initialized, MQTT connection in progress...")
        send_service_log(
            service="mqtt-bridge",
            level="info",
            message="MQTT Bridge Publisher initialized",
            context={"mqtt_ready": publisher.is_ready()},
        )
    except Exception as e:
        logger.error(f"Failed to initialize Publisher: {e}", exc_info=True)
        send_service_log(
            service="mqtt-bridge",
            level="critical",
            message=f"Failed to initialize Publisher: {e}",
            context={"error": str(e)},
        )
        publisher = None
    
    yield
    
    # Shutdown
    logger.info("Stopping MQTT Bridge service")
    if publisher:
        try:
            publisher.stop()
        except Exception as e:
            logger.error(f"Error stopping Publisher: {e}", exc_info=True)
    
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


def _ensure_trace_for_command(cmd_id: Optional[str]) -> None:
    if cmd_id:
        set_trace_id(cmd_id, allow_generate=False)


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


@app.post("/bridge/zones/{zone_id}/commands")
async def send_zone_command(
    request: Request,
    zone_id: int = Path(..., ge=1),
):
    _auth(request)
    REQ_COUNTER.labels(path="/bridge/zones/{zone_id}/commands").inc()
    raise HTTPException(
        status_code=410,
        detail="endpoint_deprecated_use_history_logger",
    )


@app.post("/bridge/nodes/{node_uid}/commands")
async def send_node_command(
    request: Request,
    node_uid: str = Path(..., min_length=1),
):
    _auth(request)
    REQ_COUNTER.labels(path="/bridge/nodes/{node_uid}/commands").inc()
    raise HTTPException(
        status_code=410,
        detail="endpoint_deprecated_use_history_logger",
    )


from common.schemas import NodeConfigModel

class NodeConfigRequest(BaseModel):
    node_uid: str = Field(..., min_length=1, max_length=128)
    hardware_id: Optional[str] = Field(None, max_length=128)  # Для временного топика
    zone_id: Optional[int] = Field(None, ge=1)
    greenhouse_uid: Optional[str] = Field(None, max_length=128)
    config: NodeConfigModel


@app.post("/bridge/nodes/{node_uid}/config")
async def publish_node_config(
    request: Request,
    node_uid: str = Path(..., min_length=1),
    req: NodeConfigRequest = Body(...),
):
    """Публиковать NodeConfig в MQTT."""
    _auth(request)
    REQ_COUNTER.labels(path="/bridge/nodes/{node_uid}/config").inc()
    
    # Проверяем готовность bridge
    if not publisher or not publisher.is_ready():
        raise HTTPException(
            status_code=503,
            detail="bridge_not_ready"
        )
    
    # Получаем zone_id и gh_uid из запроса или из БД
    zone_id = req.zone_id
    gh_uid = req.greenhouse_uid
    
    # Если не указаны, пытаемся получить из БД
    if not zone_id or not gh_uid:
        rows = await fetch(
            """
            SELECT n.zone_id, g.uid as gh_uid, n.lifecycle_state
            FROM nodes n
            LEFT JOIN zones z ON n.zone_id = z.id
            LEFT JOIN greenhouses g ON z.greenhouse_id = g.id
            WHERE n.uid = $1
            """,
            node_uid,
        )
        if rows and len(rows) > 0:
            if not zone_id:
                zone_id = rows[0].get("zone_id")
            if not gh_uid:
                gh_uid = rows[0].get("gh_uid")
    
    if not zone_id:
        raise HTTPException(status_code=400, detail="zone_id is required (node must be assigned to a zone)")
    if not gh_uid:
        raise HTTPException(status_code=400, detail="greenhouse_uid is required (zone must have a greenhouse)")
    
    # Получаем node_preconfig из БД (lifecycle_state = REGISTERED_BACKEND)
    node_preconfig = False
    node_rows = await fetch(
        """
        SELECT lifecycle_state
        FROM nodes
        WHERE uid = $1
        """,
        node_uid,
    )
    if node_rows and len(node_rows) > 0:
        lifecycle_state = node_rows[0].get("lifecycle_state")
        # Узлы в состоянии REGISTERED_BACKEND еще не получили конфигурацию
        node_preconfig = (lifecycle_state == "REGISTERED_BACKEND")
    
    try:
        logger.info(f"Publishing config for node {node_uid}, zone_id: {zone_id}, gh_uid: {gh_uid}, hardware_id: {req.hardware_id}, node_preconfig: {node_preconfig}")
        # Преобразуем Pydantic модель в dict для публикации
        config_dict = req.config.model_dump() if hasattr(req.config, 'model_dump') else req.config.dict() if hasattr(req.config, 'dict') else dict(req.config)
        publisher.publish_config(gh_uid, zone_id, node_uid, config_dict, hardware_id=req.hardware_id, node_preconfig=node_preconfig)
        logger.info(f"Config published successfully for node {node_uid}")
        return {"status": "ok", "data": {"published": True, "topic": f"hydro/{gh_uid}/zn-{zone_id}/{node_uid}/config"}}
    except Exception as e:
        logger.error(f"Failed to publish config for node {node_uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to publish config: {str(e)}")
