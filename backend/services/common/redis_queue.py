"""
Redis queue для буферизации телеметрии перед записью в БД.
"""
import base64
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from .utils.time import utcnow

try:
    from prometheus_client import Counter, Gauge

    try:
        QUEUE_SIZE = Gauge("telemetry_queue_size", "Current size of telemetry queue")
    except ValueError:
        class _NoOpGauge:
            def set(self, *args, **kwargs): pass
        QUEUE_SIZE = _NoOpGauge()

    try:
        QUEUE_DROPPED = Counter("telemetry_queue_dropped_total", "Dropped messages due to queue overflow")
    except ValueError:
        class _NoOpCounter:
            def inc(self, *args, **kwargs): pass
            def labels(self, *args, **kwargs): return self
        QUEUE_DROPPED = _NoOpCounter()

    try:
        QUEUE_OVERFLOW_ALERTS = Counter("telemetry_queue_overflow_alerts_total", "Number of overflow alerts sent")
    except ValueError:
        class _NoOpCounter2:
            def inc(self, *args, **kwargs): pass
            def labels(self, *args, **kwargs): return self
        QUEUE_OVERFLOW_ALERTS = _NoOpCounter2()
except ImportError:
    class _Counter:
        def inc(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
    class _Gauge:
        def set(self, *args, **kwargs): pass
    QUEUE_SIZE = _Gauge()
    QUEUE_DROPPED = _Counter()
    QUEUE_OVERFLOW_ALERTS = _Counter()

try:
    import redis.asyncio as redis_async
except ImportError:
    raise ImportError(
        "redis.asyncio is required. Please install redis with asyncio support: "
        "pip install 'redis[asyncio]' or add 'redis[asyncio]' to requirements.txt"
    )

from .db import create_zone_event
from .env import get_settings

logger = logging.getLogger(__name__)

_redis_client = None

_QUEUE_ENVELOPE_MARKER = "__hydro_q"


def _wrap_queue_bytes(raw: bytes, retry_count: int) -> bytes:
    if retry_count <= 0:
        return raw
    envelope = {
        _QUEUE_ENVELOPE_MARKER: 1,
        "retry": int(retry_count),
        "payload_b64": base64.b64encode(raw).decode("ascii"),
    }
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def _unwrap_queue_bytes(data: bytes) -> Tuple[bytes, int]:
    try:
        obj = json.loads(data.decode("utf-8"))
        if isinstance(obj, dict) and obj.get(_QUEUE_ENVELOPE_MARKER) == 1:
            payload_b64 = obj.get("payload_b64")
            retry = int(obj.get("retry", 0))
            if isinstance(payload_b64, str):
                return base64.b64decode(payload_b64), retry
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
        pass
    return data, 0


@dataclass
class TelemetryQueueItem:
    """Элемент очереди телеметрии."""

    node_uid: str
    zone_uid: Optional[str] = None
    gh_uid: Optional[str] = None
    metric_type: str = ""
    value: float = 0.0
    ts: Optional[datetime] = None
    raw: Optional[dict] = None
    channel: Optional[str] = None
    enqueued_at: Optional[datetime] = None

    def dict(self) -> dict:
        from dataclasses import asdict

        data = asdict(self)
        if data.get("ts") and isinstance(data["ts"], datetime):
            data["ts"] = data["ts"].isoformat()
        if data.get("enqueued_at") and isinstance(data["enqueued_at"], datetime):
            data["enqueued_at"] = data["enqueued_at"].isoformat()
        return data

    def to_json(self) -> bytes:
        return json.dumps(self.dict(), default=str).encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes) -> Optional["TelemetryQueueItem"]:
        try:
            obj = json.loads(data.decode("utf-8"))
            if obj.get("ts"):
                try:
                    ts = datetime.fromisoformat(obj["ts"].replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    obj["ts"] = ts
                except (ValueError, AttributeError):
                    obj["ts"] = None
            if obj.get("enqueued_at"):
                try:
                    enq = datetime.fromisoformat(obj["enqueued_at"].replace("Z", "+00:00"))
                    if enq.tzinfo is None:
                        enq = enq.replace(tzinfo=timezone.utc)
                    obj["enqueued_at"] = enq
                except (ValueError, AttributeError):
                    obj["enqueued_at"] = None
            return cls(**obj)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to deserialize TelemetryQueueItem: {e}")
            return None


@dataclass
class QueueEntry:
    raw: bytes
    item: TelemetryQueueItem
    retry_count: int = 0


@dataclass
class PopBatchResult:
    entries: List[QueueEntry] = field(default_factory=list)


_POP_BATCH_SCRIPT = """
local queue_key = KEYS[1]
local processing_key = KEYS[2]
local batch_size = tonumber(ARGV[1])
local results = {}
for i = 1, batch_size do
  local item = redis.call('LMOVE', queue_key, processing_key, 'LEFT', 'RIGHT')
  if not item then
    break
  end
  table.insert(results, item)
end
return results
"""

_RECLAIM_PROCESSING_SCRIPT = """
local processing_key = KEYS[1]
local queue_key = KEYS[2]
local count = 0
while true do
  local item = redis.call('LMOVE', processing_key, queue_key, 'LEFT', 'LEFT')
  if not item then
    break
  end
  count = count + 1
end
return count
"""


class TelemetryQueue:
    """Очередь телеметрии в Redis для буферизации перед записью в БД."""

    QUEUE_KEY = "hydro:telemetry:queue"
    PROCESSING_KEY = "hydro:telemetry:processing"
    DEAD_KEY = "hydro:telemetry:dead"
    MAX_QUEUE_SIZE = 50000

    def __init__(self):
        self._client: Optional[redis_async.Redis] = None
        self._pop_script = None
        self._reclaim_script = None

    def _max_pg_retries(self) -> int:
        return max(1, int(get_settings().telemetry_max_pg_retries))

    async def _ensure_client(self):
        if self._client is None:
            self._client = await get_redis_client()
        if self._pop_script is None:
            self._pop_script = self._client.register_script(_POP_BATCH_SCRIPT)
        if self._reclaim_script is None:
            self._reclaim_script = self._client.register_script(_RECLAIM_PROCESSING_SCRIPT)

    async def push(self, item: TelemetryQueueItem) -> bool:
        try:
            await self._ensure_client()

            size = await self._client.llen(self.QUEUE_KEY)
            QUEUE_SIZE.set(size)

            utilization = size / self.MAX_QUEUE_SIZE if self.MAX_QUEUE_SIZE > 0 else 0.0
            if utilization > 0.95:
                await self._send_overflow_alert(size)
                sample_rate = 0.8 if utilization < 0.98 else 0.5
                if random.random() > sample_rate:
                    QUEUE_DROPPED.labels(reason="backpressure").inc()
                    logger.warning(
                        f"Dropping telemetry due to backpressure (queue {utilization:.1%} full)",
                        extra={"queue_utilization": utilization, "queue_size": size},
                    )
                    return False

            if size >= self.MAX_QUEUE_SIZE:
                QUEUE_DROPPED.labels(reason="overflow").inc()
                if size >= self.MAX_QUEUE_SIZE * 0.95:
                    await self._send_overflow_alert(size)
                logger.warning(
                    f"Telemetry queue is full ({size} items), dropping message",
                    extra={
                        "queue_size": size,
                        "max_size": self.MAX_QUEUE_SIZE,
                        "utilization": f"{utilization:.1%}",
                    },
                )
                return False

            item.enqueued_at = utcnow()
            await self._client.rpush(self.QUEUE_KEY, item.to_json())
            return True

        except Exception as e:
            logger.error(f"Failed to push to telemetry queue: {e}", exc_info=True)
            return False

    async def _send_overflow_alert(self, current_size: int):
        try:
            await self._ensure_client()
            throttle_key = "alert_throttle:queue_overflow"
            if await self._client.exists(throttle_key):
                return

            await self._client.setex(throttle_key, 60, "1")
            QUEUE_OVERFLOW_ALERTS.inc()
            logger.error(
                f"CRITICAL: Telemetry queue overflow! Size: {current_size}/{self.MAX_QUEUE_SIZE}",
                extra={
                    "queue_size": current_size,
                    "max_size": self.MAX_QUEUE_SIZE,
                    "utilization": f"{current_size/self.MAX_QUEUE_SIZE:.1%}",
                },
            )
            try:
                await create_zone_event(
                    zone_id=None,
                    event_type="system_queue_overflow",
                    details={
                        "queue_size": current_size,
                        "max_size": self.MAX_QUEUE_SIZE,
                        "severity": "critical",
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to create zone event for queue overflow: {e}")
        except Exception as e:
            logger.error(f"Failed to send overflow alert: {e}", exc_info=True)

    async def pop_batch(self, batch_size: int) -> PopBatchResult:
        try:
            await self._ensure_client()
            if batch_size <= 0:
                return PopBatchResult()

            raw_items = await self._pop_script(
                keys=[self.QUEUE_KEY, self.PROCESSING_KEY],
                args=[max(1, int(batch_size))],
            )
            if not raw_items:
                return PopBatchResult()

            entries: List[QueueEntry] = []
            for wrapped in raw_items:
                if wrapped is None:
                    continue
                if isinstance(wrapped, str):
                    wrapped = wrapped.encode("utf-8")
                inner, retry_count = _unwrap_queue_bytes(wrapped)
                item = TelemetryQueueItem.from_json(inner)
                if item is None:
                    await self._move_raw_to_dead(wrapped, reason="deserialize_failed")
                    continue
                entries.append(
                    QueueEntry(raw=wrapped, item=item, retry_count=retry_count)
                )

            return PopBatchResult(entries=entries)

        except Exception as e:
            logger.error(f"Failed to pop batch from telemetry queue: {e}", exc_info=True)
            return PopBatchResult()

    async def ack_batch(self, raw_items: List[bytes]) -> int:
        if not raw_items:
            return 0
        try:
            await self._ensure_client()
            removed = 0
            for raw in raw_items:
                count = await self._client.lrem(self.PROCESSING_KEY, 1, raw)
                removed += int(count or 0)
            return removed
        except Exception as e:
            logger.error(f"Failed to ack telemetry batch: {e}", exc_info=True)
            return 0

    async def requeue_batch(self, entries: List[QueueEntry]) -> int:
        if not entries:
            return 0
        try:
            await self._ensure_client()
            max_retries = self._max_pg_retries()
            requeued = 0
            for entry in entries:
                next_retry = int(entry.retry_count) + 1
                if next_retry > max_retries:
                    await self._move_raw_to_dead(entry.raw, reason="max_pg_retries")
                    continue
                wrapped = _wrap_queue_bytes(
                    _unwrap_queue_bytes(entry.raw)[0],
                    next_retry,
                )
                await self._client.lrem(self.PROCESSING_KEY, 1, entry.raw)
                await self._client.lpush(self.QUEUE_KEY, wrapped)
                requeued += 1
            return requeued
        except Exception as e:
            logger.error(f"Failed to requeue telemetry batch: {e}", exc_info=True)
            return 0

    async def reclaim_processing(self) -> int:
        try:
            await self._ensure_client()
            reclaimed = await self._reclaim_script(
                keys=[self.PROCESSING_KEY, self.QUEUE_KEY],
                args=[],
            )
            return int(reclaimed or 0)
        except Exception as e:
            logger.error(f"Failed to reclaim telemetry processing list: {e}", exc_info=True)
            return 0

    async def _move_raw_to_dead(self, raw: bytes, *, reason: str) -> bool:
        try:
            await self._ensure_client()
            dead_payload = json.dumps(
                {
                    "reason": reason,
                    "retry": _unwrap_queue_bytes(raw)[1],
                    "payload_b64": base64.b64encode(_unwrap_queue_bytes(raw)[0]).decode("ascii"),
                    "moved_at": utcnow().isoformat(),
                },
                separators=(",", ":"),
            ).encode("utf-8")
            await self._client.lrem(self.PROCESSING_KEY, 1, raw)
            await self._client.rpush(self.DEAD_KEY, dead_payload)
            try:
                from metrics import TELEMETRY_DESERIALIZE_FAILED

                if reason == "deserialize_failed":
                    TELEMETRY_DESERIALIZE_FAILED.inc()
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"Failed to move telemetry item to dead list: {e}", exc_info=True)
            return False

    async def total_pending_size(self) -> int:
        try:
            await self._ensure_client()
            queue_size, processing_size = await self._client.llen(self.QUEUE_KEY), await self._client.llen(
                self.PROCESSING_KEY
            )
            return int(queue_size or 0) + int(processing_size or 0)
        except Exception as e:
            logger.error(f"Failed to get total pending queue size: {e}", exc_info=True)
            return 0

    async def size(self) -> int:
        try:
            await self._ensure_client()
            return int(await self._client.llen(self.QUEUE_KEY) or 0)
        except Exception as e:
            logger.error(f"Failed to get queue size: {e}", exc_info=True)
            return 0

    async def get_oldest_age_seconds(self) -> Optional[float]:
        try:
            await self._ensure_client()
            oldest_item_data = await self._client.lindex(self.QUEUE_KEY, 0)
            if not oldest_item_data:
                return None

            inner, _ = _unwrap_queue_bytes(oldest_item_data)
            oldest_item = TelemetryQueueItem.from_json(inner)
            if not oldest_item or not oldest_item.enqueued_at:
                return None

            age = (utcnow() - oldest_item.enqueued_at).total_seconds()
            return max(0.0, age)

        except Exception as e:
            logger.error(f"Failed to get queue oldest age: {e}", exc_info=True)
            return None

    async def clear(self):
        try:
            await self._ensure_client()
            await self._client.delete(self.QUEUE_KEY, self.PROCESSING_KEY)
            logger.info("Telemetry queue cleared")
        except Exception as e:
            logger.error(f"Failed to clear telemetry queue: {e}", exc_info=True)


async def get_redis_client():
    global _redis_client

    if _redis_client is None:
        s = get_settings()
        _redis_client = redis_async.Redis(
            host=s.redis_host if hasattr(s, "redis_host") else "redis",
            port=s.redis_port if hasattr(s, "redis_port") else 6379,
            db=0,
            decode_responses=False,
        )
        try:
            await _redis_client.ping()
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            _redis_client = None
            raise

    return _redis_client


async def close_redis_client():
    global _redis_client

    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception as e:
            logger.error(f"Error closing Redis client: {e}")
        finally:
            _redis_client = None
