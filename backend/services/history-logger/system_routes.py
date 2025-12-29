import logging

from fastapi import APIRouter, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from common.alert_queue import get_alert_queue
from common.command_status_queue import get_status_queue
from common.infra_monitor import check_db_health, check_mqtt_health
from common.mqtt import get_mqtt_client
from common.pipeline_metrics import (
    update_db_health,
    update_mqtt_health,
    update_queue_health,
    update_queue_metrics,
)
from common.db import get_pool

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health():
    """
    Health check endpoint с проверкой компонентов.
    """
    health_status = {"status": "ok", "components": {}}

    db_ok = False
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
        update_db_health(True)
        await check_db_health(True)
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")
        update_db_health(False)
        await check_db_health(False)
        health_status["status"] = "degraded"

    health_status["components"]["db"] = "ok" if db_ok else "fail"

    mqtt_ok = False
    try:
        mqtt = await get_mqtt_client()
        if mqtt and hasattr(mqtt, "is_connected") and mqtt.is_connected():
            mqtt_ok = True
            update_mqtt_health(True)
            await check_mqtt_health(True)
        else:
            update_mqtt_health(False)
            await check_mqtt_health(False)
            health_status["status"] = "degraded"
    except Exception as e:
        logger.warning(f"MQTT health check failed: {e}")
        update_mqtt_health(False)
        await check_mqtt_health(False)
        health_status["status"] = "degraded"

    health_status["components"]["mqtt"] = "ok" if mqtt_ok else "fail"

    try:
        alert_queue = await get_alert_queue()
        alert_metrics = await alert_queue.get_queue_metrics()
        update_queue_metrics(
            "alerts", alert_metrics["size"], alert_metrics["oldest_age_seconds"]
        )

        alerts_healthy = (
            alert_metrics["size"] < 1000
            and alert_metrics["oldest_age_seconds"] < 3600
        )
        update_queue_health("alerts", alerts_healthy)
        health_status["components"]["queue_alerts"] = {
            "status": "ok" if alerts_healthy else "degraded",
            "size": alert_metrics["size"],
            "oldest_age_seconds": alert_metrics["oldest_age_seconds"],
            "dlq_size": alert_metrics.get("dlq_size", 0),
            "success_rate": alert_metrics.get("success_rate", 1.0),
        }

        status_queue = await get_status_queue()
        status_metrics = await status_queue.get_queue_metrics()
        update_queue_metrics(
            "status_updates", status_metrics["size"], status_metrics["oldest_age_seconds"]
        )

        status_healthy = (
            status_metrics["size"] < 1000
            and status_metrics["oldest_age_seconds"] < 3600
        )
        update_queue_health("status_updates", status_healthy)
        health_status["components"]["queue_status_updates"] = {
            "status": "ok" if status_healthy else "degraded",
            "size": status_metrics["size"],
            "oldest_age_seconds": status_metrics["oldest_age_seconds"],
            "dlq_size": status_metrics.get("dlq_size", 0),
            "success_rate": status_metrics.get("success_rate", 1.0),
        }

        if not alerts_healthy or not status_healthy:
            health_status["status"] = "degraded"
    except Exception as e:
        logger.warning(f"Queue health check failed: {e}")
        health_status["components"]["queue_alerts"] = "unknown"
        health_status["components"]["queue_status_updates"] = "unknown"
        health_status["status"] = "degraded"

    return health_status


@router.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    metrics_data = generate_latest()
    return Response(
        content=metrics_data.decode("utf-8")
        if isinstance(metrics_data, bytes)
        else metrics_data,
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/api/dlq/alerts")
async def list_alerts_dlq(limit: int = 100, offset: int = 0):
    """Получить список элементов из DLQ алертов."""
    try:
        alert_queue = await get_alert_queue()
        items = await alert_queue.list_dlq(limit=limit, offset=offset)
        metrics_data = await alert_queue.get_queue_metrics()

        return {
            "items": items,
            "total": metrics_data.get("dlq_size", 0),
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error(f"Failed to list alerts DLQ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/dlq/alerts/{dlq_id}/replay")
async def replay_alert_dlq(dlq_id: int):
    """Переместить элемент из DLQ алертов обратно в очередь для повторной попытки."""
    try:
        alert_queue = await get_alert_queue()
        success = await alert_queue.replay_dlq_item(dlq_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"DLQ item {dlq_id} not found")

        return {
            "success": True,
            "message": f"Alert DLQ item {dlq_id} replayed successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to replay alert DLQ item {dlq_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/dlq/alerts/{dlq_id}")
async def purge_alert_dlq_item(dlq_id: int):
    """Удалить элемент из DLQ алертов."""
    try:
        alert_queue = await get_alert_queue()
        success = await alert_queue.purge_dlq_item(dlq_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"DLQ item {dlq_id} not found")

        return {"success": True, "message": f"Alert DLQ item {dlq_id} purged successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to purge alert DLQ item {dlq_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/dlq/alerts")
async def purge_all_alerts_dlq():
    """Удалить все элементы из DLQ алертов."""
    try:
        alert_queue = await get_alert_queue()
        count = await alert_queue.purge_dlq_all()

        return {"success": True, "message": f"Purged {count} alert DLQ items"}
    except Exception as e:
        logger.error(f"Failed to purge all alerts DLQ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/dlq/status-updates")
async def list_status_updates_dlq(limit: int = 100, offset: int = 0):
    """Получить список элементов из DLQ статусов команд."""
    try:
        status_queue = await get_status_queue()
        items = await status_queue.list_dlq(limit=limit, offset=offset)
        metrics_data = await status_queue.get_queue_metrics()

        return {
            "items": items,
            "total": metrics_data.get("dlq_size", 0),
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error(f"Failed to list status updates DLQ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/dlq/status-updates/{dlq_id}/replay")
async def replay_status_update_dlq(dlq_id: int):
    """Переместить элемент из DLQ статусов команд обратно в очередь для повторной попытки."""
    try:
        status_queue = await get_status_queue()
        success = await status_queue.replay_dlq_item(dlq_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"DLQ item {dlq_id} not found")

        return {
            "success": True,
            "message": f"Status update DLQ item {dlq_id} replayed successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to replay status update DLQ item {dlq_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/dlq/status-updates/{dlq_id}")
async def purge_status_update_dlq_item(dlq_id: int):
    """Удалить элемент из DLQ статусов команд."""
    try:
        status_queue = await get_status_queue()
        success = await status_queue.purge_dlq_item(dlq_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"DLQ item {dlq_id} not found")

        return {
            "success": True,
            "message": f"Status update DLQ item {dlq_id} purged successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to purge status update DLQ item {dlq_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/dlq/status-updates")
async def purge_all_status_updates_dlq():
    """Удалить все элементы из DLQ статусов команд."""
    try:
        status_queue = await get_status_queue()
        count = await status_queue.purge_dlq_all()

        return {"success": True, "message": f"Purged {count} status update DLQ items"}
    except Exception as e:
        logger.error(f"Failed to purge all status updates DLQ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/dlq/metrics")
async def get_dlq_metrics():
    """Получить метрики всех DLQ очередей."""
    try:
        alert_queue = await get_alert_queue()
        status_queue = await get_status_queue()

        alert_metrics = await alert_queue.get_queue_metrics()
        status_metrics = await status_queue.get_queue_metrics()

        return {
            "alerts": {
                "size": alert_metrics.get("size", 0),
                "oldest_age_seconds": alert_metrics.get("oldest_age_seconds", 0.0),
                "dlq_size": alert_metrics.get("dlq_size", 0),
                "success_rate": alert_metrics.get("success_rate", 1.0),
            },
            "status_updates": {
                "size": status_metrics.get("size", 0),
                "oldest_age_seconds": status_metrics.get("oldest_age_seconds", 0.0),
                "dlq_size": status_metrics.get("dlq_size", 0),
                "success_rate": status_metrics.get("success_rate", 1.0),
            },
        }
    except Exception as e:
        logger.error(f"Failed to get DLQ metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
