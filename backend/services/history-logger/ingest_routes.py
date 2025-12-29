import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from auth import _check_rate_limit, _auth_ingest, INGEST_RATE_LIMIT_REQUESTS, INGEST_RATE_LIMIT_WINDOW_SEC
from metrics import INGEST_RATE_LIMITED, INGEST_REQUESTS, TELEMETRY_DROPPED
from models import TelemetryPayloadModel, TelemetrySampleModel
from telemetry_processing import process_telemetry_batch
from utils import MAX_PAYLOAD_SIZE, _filter_raw_data
from common.utils.time import utcnow

logger = logging.getLogger(__name__)

router = APIRouter()

# Максимальное количество samples в HTTP ingest батче для защиты от DoS
MAX_INGEST_SAMPLES = 1000


@router.post("/ingest/telemetry")
async def ingest_telemetry(request: Request):
    """
    HTTP endpoint для приема телеметрии.
    Принимает JSON с массивом samples и обрабатывает их батчем.
    """
    _auth_ingest(request)

    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        logger.warning(
            "Rate limit exceeded for HTTP ingest: client_ip=%s",
            client_ip,
            extra={"client_ip": client_ip},
        )
        INGEST_RATE_LIMITED.inc()
        INGEST_REQUESTS.labels(status="rate_limited").inc()
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: maximum {INGEST_RATE_LIMIT_REQUESTS} requests per {INGEST_RATE_LIMIT_WINDOW_SEC} seconds"
            ),
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
            if size > MAX_PAYLOAD_SIZE:
                logger.warning(
                    "HTTP ingest payload too large: %s bytes (max: %s)",
                    size,
                    MAX_PAYLOAD_SIZE,
                    extra={"content_length": size},
                )
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Payload too large: {size} bytes (max: {MAX_PAYLOAD_SIZE} bytes)"
                    ),
                )
        except ValueError:
            pass

    try:
        body = await request.body()
        if len(body) > MAX_PAYLOAD_SIZE:
            logger.warning(
                "HTTP ingest payload too large: %s bytes (max: %s)",
                len(body),
                MAX_PAYLOAD_SIZE,
                extra={"payload_size": len(body)},
            )
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Payload too large: {len(body)} bytes (max: {MAX_PAYLOAD_SIZE} bytes)"
                ),
            )

        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in HTTP ingest: {e}")
        INGEST_REQUESTS.labels(status="invalid_json").inc()
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error(f"Error parsing HTTP ingest payload: {e}", exc_info=True)
        INGEST_REQUESTS.labels(status="parse_error").inc()
        raise HTTPException(status_code=400, detail="Failed to parse payload")

    samples_data = payload.get("samples", [])
    if not samples_data:
        return {"status": "ok", "count": 0, "dropped": 0}

    if len(samples_data) > MAX_INGEST_SAMPLES:
        logger.warning(
            "HTTP ingest too many samples: %s (max: %s)",
            len(samples_data),
            MAX_INGEST_SAMPLES,
            extra={"samples_count": len(samples_data)},
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Too many samples: {len(samples_data)} (max: {MAX_INGEST_SAMPLES})"
            ),
        )

    samples = []
    dropped_count = 0
    MIN_VALID_TIMESTAMP = 1_000_000_000

    for idx, sample_data in enumerate(samples_data):
        if not isinstance(sample_data, dict):
            logger.warning(
                "Invalid sample type in HTTP ingest (not a dict), dropping",
                extra={"sample_index": idx, "sample_type": type(sample_data).__name__},
            )
            TELEMETRY_DROPPED.labels(reason="invalid_sample_type").inc()
            dropped_count += 1
            continue

        try:
            validated_data = TelemetryPayloadModel(**sample_data)
        except Exception as e:
            logger.warning(
                "Invalid telemetry sample in HTTP ingest, dropping",
                extra={
                    "error": str(e),
                    "sample_index": idx,
                    "sample_keys": list(sample_data.keys())
                    if isinstance(sample_data, dict)
                    else None,
                },
            )
            TELEMETRY_DROPPED.labels(reason="validation_failed").inc()
            dropped_count += 1
            continue

        if not validated_data.metric_type:
            logger.warning(
                "Missing metric_type in HTTP ingest sample, dropping",
                extra={"sample_index": idx, "sample_keys": list(sample_data.keys())},
            )
            TELEMETRY_DROPPED.labels(reason="missing_metric_type").inc()
            dropped_count += 1
            continue

        ts = None
        if validated_data.ts:
            try:
                if isinstance(validated_data.ts, (int, float)):
                    ts_value = float(validated_data.ts)
                    if ts_value >= MIN_VALID_TIMESTAMP:
                        ts = datetime.fromtimestamp(ts_value)
                    else:
                        logger.warning(
                            "Invalid timestamp in HTTP ingest (likely uptime), using server time",
                            extra={
                                "ts": ts_value,
                                "node_uid": validated_data.node_uid,
                                "zone_uid": validated_data.zone_uid,
                                "sample_index": idx,
                            },
                        )
                elif isinstance(validated_data.ts, str):
                    ts = datetime.fromisoformat(validated_data.ts.replace("Z", "+00:00"))
                    ts_timestamp = ts.timestamp()
                    if ts_timestamp < MIN_VALID_TIMESTAMP:
                        logger.warning(
                            "Invalid timestamp in HTTP ingest (likely uptime), using server time",
                            extra={
                                "ts": ts_timestamp,
                                "node_uid": validated_data.node_uid,
                                "zone_uid": validated_data.zone_uid,
                                "sample_index": idx,
                            },
                        )
                        ts = None
            except Exception as e:
                logger.warning(
                    "Failed to parse timestamp in HTTP ingest, using server time",
                    extra={
                        "ts": validated_data.ts,
                        "error": str(e),
                        "node_uid": validated_data.node_uid,
                        "zone_uid": validated_data.zone_uid,
                        "sample_index": idx,
                    },
                )

        if ts is None:
            ts = utcnow()

        zone_uid = validated_data.zone_uid
        zone_id = None
        node_uid = validated_data.node_uid or ""
        gh_uid = validated_data.gh_uid
        channel = validated_data.channel

        filtered_raw = _filter_raw_data(sample_data)

        sample = TelemetrySampleModel(
            node_uid=node_uid,
            zone_uid=zone_uid,
            zone_id=zone_id,
            gh_uid=gh_uid,
            metric_type=validated_data.metric_type,
            value=validated_data.value,
            ts=ts,
            raw=filtered_raw,
            channel=channel,
        )
        samples.append(sample)

    if samples:
        await process_telemetry_batch(samples)

    INGEST_REQUESTS.labels(status="success").inc()

    return {
        "status": "ok",
        "count": len(samples),
        "dropped": dropped_count,
        "total": len(samples_data),
    }
