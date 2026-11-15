"""Stage component: levels. Explicit ports; no handler dependency."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Sequence

_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageLevelReaderPorts:
    raise_execution_error: Callable[..., Awaitable[Any]]
    read_probe_level_snapshot: Callable[..., Any]
    runtime_monitor: Callable[[], Any]


class StageLevelReader:
    def __init__(self, ports: StageLevelReaderPorts) -> None:
        self._ports = ports

    async def read_level(
        self,
        *,
        task: Any,
        zone_id: int,
        labels: Sequence[str],
        threshold: float,
        telemetry_max_age_sec: int,
        unavailable_error: str,
        stale_error: str,
        stale_recheck_delay_sec: float | None = None,
        prefer_probe_snapshot: bool = False,
        allow_stale_if_untriggered: bool = False,
    ) -> Mapping[str, Any]:
        level = await self._ports.runtime_monitor().read_level_switch(
            zone_id=zone_id,
            sensor_labels=labels,
            threshold=threshold,
            telemetry_max_age_sec=telemetry_max_age_sec,
            allow_initial_event_fallback=True,
        )
        if prefer_probe_snapshot:
            probe_level = self._ports.read_probe_level_snapshot(
                task=task,
                labels=labels,
                threshold=threshold,
                telemetry_max_age_sec=telemetry_max_age_sec,
            )
            if probe_level is not None and self.should_use_probe_level(
                probe_level=probe_level,
                runtime_level=level,
            ):
                self.log_level_state(
                    task=task,
                    labels=labels,
                    level=probe_level,
                    telemetry_max_age_sec=telemetry_max_age_sec,
                    reason="probe_snapshot_used",
                    log_method=_logger.info,
                )
                return probe_level
        if not level["has_level"]:
            await self._ports.raise_execution_error(
                task=task,
                error_code=unavailable_error,
                error_message=f"Недоступен датчик уровня: {labels}",
            )
        if level["is_stale"]:
            if allow_stale_if_untriggered and not bool(level.get("is_triggered")):
                self.log_level_state(
                    task=task,
                    labels=labels,
                    level=level,
                    telemetry_max_age_sec=telemetry_max_age_sec,
                    reason="stale_untriggered_allowed",
                    log_method=_logger.info,
                )
                return level
            self.log_level_state(
                task=task,
                labels=labels,
                level=level,
                telemetry_max_age_sec=telemetry_max_age_sec,
                reason="stale_first_read",
            )
            if stale_recheck_delay_sec is not None and stale_recheck_delay_sec > 0:
                await asyncio.sleep(stale_recheck_delay_sec)
                refreshed_level = await self._ports.runtime_monitor().read_level_switch(
                    zone_id=zone_id,
                    sensor_labels=labels,
                    threshold=threshold,
                    telemetry_max_age_sec=telemetry_max_age_sec,
                    allow_initial_event_fallback=True,
                )
                if refreshed_level["has_level"] and not refreshed_level["is_stale"]:
                    self.log_level_state(
                        task=task,
                        labels=labels,
                        level=refreshed_level,
                        telemetry_max_age_sec=telemetry_max_age_sec,
                        reason="stale_recheck_recovered",
                        log_method=_logger.info,
                    )
                    return refreshed_level
                self.log_level_state(
                    task=task,
                    labels=labels,
                    level=refreshed_level,
                    telemetry_max_age_sec=telemetry_max_age_sec,
                    reason="stale_recheck_failed",
                )
            await self._ports.raise_execution_error(
                task=task,
                error_code=stale_error,
                error_message=f"Данные датчика уровня устарели: {labels}",
            )
        return level

    def should_use_probe_level(
        self,
        *,
        probe_level: Mapping[str, Any],
        runtime_level: Mapping[str, Any],
    ) -> bool:
        if not bool(probe_level.get("has_level")) or bool(probe_level.get("is_stale")):
            return False
        if not bool(runtime_level.get("has_level")) or bool(runtime_level.get("is_stale")):
            return True

        probe_ts = probe_level.get("sample_ts")
        runtime_ts = runtime_level.get("sample_ts")
        if isinstance(probe_ts, datetime) and isinstance(runtime_ts, datetime):
            return probe_ts > runtime_ts
        if isinstance(probe_ts, datetime) and runtime_ts is None:
            return True
        return False

    def log_level_state(
        self,
        *,
        task: Any,
        labels: Sequence[str],
        level: Mapping[str, Any],
        telemetry_max_age_sec: int,
        reason: str,
        log_method: Any = _logger.warning,
    ) -> None:
        sample_ts = level.get("sample_ts")
        serialized_sample_ts = sample_ts.isoformat() if hasattr(sample_ts, "isoformat") else sample_ts
        log_method(
            "AE3 level read zone_id=%s task_id=%s stage=%s reason=%s labels=%s sample_ts=%s sample_age_sec=%s "
            "telemetry_max_age_sec=%s has_level=%s is_stale=%s is_triggered=%s source=%s",
            int(getattr(task, "zone_id", 0) or 0),
            int(getattr(task, "id", 0) or 0),
            str(getattr(task, "current_stage", "") or ""),
            str(reason or ""),
            list(labels),
            serialized_sample_ts,
            level.get("sample_age_sec"),
            int(telemetry_max_age_sec),
            bool(level.get("has_level")),
            bool(level.get("is_stale")),
            bool(level.get("is_triggered")),
            str(level.get("source") or "telemetry_last"),
        )
