import asyncio
from typing import List, Optional

from common.redis_queue import TelemetryQueue

telemetry_queue: Optional[TelemetryQueue] = None
shutdown_event = asyncio.Event()
background_tasks: List[asyncio.Task] = []
