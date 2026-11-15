"""runtime thresholds: explicit dependencies and invocation data."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RuntimeThresholdsPorts:
    normalize_ts_for_db: Callable[..., Any]
    logger: Callable[..., Any]


class RuntimeThresholds:
    def __init__(self, ports: RuntimeThresholdsPorts) -> None:
        self._ports = ports

    async def evaluate_solution_temp_thresholds(self, *, written_items: Any) -> None:
        try:
            from handlers.solution_temp_threshold_alerts import (
                is_solution_temp_channel,
                process_solution_temp_telemetry_batch,
            )

            solution_temp_items = [
                {
                    "zone_id": item.get("zone_id"),
                    "channel": getattr(item.get("sample"), "channel", None),
                    "value": getattr(item.get("sample"), "value", None),
                    "ts": self._ports.normalize_ts_for_db(item["sample"].ts),
                }
                for item in written_items
                if item.get("zone_id") is not None
                and item.get("sample") is not None
                and is_solution_temp_channel(getattr(item["sample"], "channel", None))
            ]
            if solution_temp_items:
                await process_solution_temp_telemetry_batch(solution_temp_items)
        except Exception:
            self._ports.logger().error("solution_temp threshold evaluation failed", exc_info=True)
