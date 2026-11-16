"""Запросы live runtime monitor для выполнения cycle_start в AE3-Lite."""

from __future__ import annotations
from functools import cached_property

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from common.db import get_pool

from ae3lite.domain.level_switch_semantics import confirmed_level_switch, newer_level_sample
from ae3lite.domain.services.metric_window_validator import is_stub_telemetry
from ae3lite.domain.services.solution_temp_irrigation_guard import SOLUTION_TEMP_CHANNEL_LABELS


from ae3lite.infrastructure.read_models.runtime_monitor_shared import logger

from ae3lite.infrastructure.read_models.runtime_monitor_values import RuntimeMonitorValues, RuntimeMonitorValuesPorts
from ae3lite.infrastructure.read_models.runtime_monitor_levels import RuntimeMonitorLevels, RuntimeMonitorLevelsPorts
from ae3lite.infrastructure.read_models.runtime_monitor_metric_windows import (
    RuntimeMonitorMetricWindows,
    RuntimeMonitorMetricWindowsPorts,
)
from ae3lite.infrastructure.read_models.runtime_monitor_temperature import (
    RuntimeMonitorTemperature,
    RuntimeMonitorTemperaturePorts,
)
from ae3lite.infrastructure.read_models.runtime_monitor_events import RuntimeMonitorEvents, RuntimeMonitorEventsPorts


class PgZoneRuntimeMonitor:
    """Читает свежую телеметрию и snapshot'ы irr-state во время выполнения AE3."""

    @cached_property
    def _runtime_monitor_values(self):
        return RuntimeMonitorValues(RuntimeMonitorValuesPorts())

    @cached_property
    def _runtime_monitor_levels(self):
        return RuntimeMonitorLevels(
            RuntimeMonitorLevelsPorts(
                age_sec=lambda *args, **kwargs: self._age_sec(*args, **kwargs),
                coerce_optional_bool=lambda *args, **kwargs: self._coerce_optional_bool(*args, **kwargs),
                extract_level_state_from_event=lambda *args, **kwargs: self._extract_level_state_from_event(
                    *args, **kwargs
                ),
                normalize_labels=lambda *args, **kwargs: self._normalize_labels(*args, **kwargs),
                payload_field=lambda *args, **kwargs: self._payload_field(*args, **kwargs),
                prefer_event_over_telemetry=lambda *args, **kwargs: self._prefer_event_over_telemetry(*args, **kwargs),
                resolve_zone_event_payload=lambda *args, **kwargs: self._resolve_zone_event_payload(*args, **kwargs),
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )

    @cached_property
    def _runtime_monitor_metric_windows(self):
        return RuntimeMonitorMetricWindows(
            RuntimeMonitorMetricWindowsPorts(
                age_sec=lambda *args, **kwargs: self._age_sec(*args, **kwargs),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                read_metric_sensor=lambda *args, **kwargs: self._read_metric_sensor(*args, **kwargs),
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )

    @cached_property
    def _runtime_monitor_temperature(self):
        return RuntimeMonitorTemperature(
            RuntimeMonitorTemperaturePorts(
                normalize_labels=lambda *args, **kwargs: self._normalize_labels(*args, **kwargs),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )

    @cached_property
    def _runtime_monitor_events(self):
        return RuntimeMonitorEvents(
            RuntimeMonitorEventsPorts(
                age_sec=lambda *args, **kwargs: self._age_sec(*args, **kwargs),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                resolve_zone_event_payload=lambda *args, **kwargs: self._resolve_zone_event_payload(*args, **kwargs),
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )

    def _normalize_timestamp(self, value: Optional[datetime]) -> Optional[datetime]:
        return self._runtime_monitor_values.normalize_timestamp(value=value)

    def _normalize_labels(self, labels: Sequence[str]) -> list[str]:
        return self._runtime_monitor_values.normalize_labels(labels=labels)

    def _age_sec(self, sample_ts: Optional[datetime]) -> Optional[float]:
        return self._runtime_monitor_values.age_sec(sample_ts=sample_ts)

    def _resolve_zone_event_payload(self, row: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._runtime_monitor_values.resolve_zone_event_payload(row=row)

    def _coerce_optional_bool(self, value: Any) -> bool | None:
        return self._runtime_monitor_values.coerce_optional_bool(value=value)

    def _payload_field(self, payload: Mapping[str, Any], key: str) -> Any:
        return self._runtime_monitor_values.payload_field(payload=payload, key=key)

    def _level_snapshot_aliases(self, label: str) -> tuple[str, ...]:
        return self._runtime_monitor_values.level_snapshot_aliases(label=label)

    def _extract_level_state_from_event(
        self,
        *,
        payload: Mapping[str, Any],
        labels: Sequence[str],
    ) -> tuple[str, bool] | None:
        return self._runtime_monitor_values.extract_level_state_from_event(payload=payload, labels=labels)

    async def read_latest_level_switch_event(
        self,
        *,
        zone_id: int,
        sensor_labels: Sequence[str],
        max_age_sec: int,
        allow_initial_event: bool = False,
    ) -> Mapping[str, Any] | None:
        return await self._runtime_monitor_levels.read_latest_level_switch_event(
            zone_id=zone_id,
            sensor_labels=sensor_labels,
            max_age_sec=max_age_sec,
            allow_initial_event=allow_initial_event,
        )

    def _prefer_event_over_telemetry(
        self,
        *,
        telemetry_level: Mapping[str, Any],
        event_level: Mapping[str, Any] | None,
        allow_if_telemetry_fresh: bool,
    ) -> Mapping[str, Any] | None:
        return self._runtime_monitor_values.prefer_event_over_telemetry(
            telemetry_level=telemetry_level, event_level=event_level, allow_if_telemetry_fresh=allow_if_telemetry_fresh
        )

    async def _read_metric_sensor(self, *, zone_id: int, sensor_type: str) -> Mapping[str, Any] | None:
        return await self._runtime_monitor_levels.read_metric_sensor(zone_id=zone_id, sensor_type=sensor_type)

    async def read_level_switch(
        self,
        *,
        zone_id: int,
        sensor_labels: Sequence[str],
        threshold: float,
        telemetry_max_age_sec: int,
        allow_initial_event: bool = False,
        allow_initial_event_fallback: bool = False,
    ) -> Mapping[str, Any]:
        return await self._runtime_monitor_levels.read_level_switch(
            zone_id=zone_id,
            sensor_labels=sensor_labels,
            threshold=threshold,
            telemetry_max_age_sec=telemetry_max_age_sec,
            allow_initial_event=allow_initial_event,
            allow_initial_event_fallback=allow_initial_event_fallback,
        )

    async def read_metric(self, *, zone_id: int, sensor_type: str, telemetry_max_age_sec: int) -> Mapping[str, Any]:
        return await self._runtime_monitor_metric_windows.read_metric(
            zone_id=zone_id, sensor_type=sensor_type, telemetry_max_age_sec=telemetry_max_age_sec
        )

    async def read_metric_window(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        since_ts: datetime,
        telemetry_max_age_sec: int,
        limit: int = 64,
    ) -> Mapping[str, Any]:
        return await self._runtime_monitor_metric_windows.read_metric_window(
            zone_id=zone_id,
            sensor_type=sensor_type,
            since_ts=since_ts,
            telemetry_max_age_sec=telemetry_max_age_sec,
            limit=limit,
        )

    async def read_metric_windows(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        since_ts: datetime,
        telemetry_max_age_sec: int,
        limit_per_sensor: int = 64,
        until_ts: datetime | None = None,
    ) -> Mapping[str, Any]:
        return await self._runtime_monitor_metric_windows.read_metric_windows(
            zone_id=zone_id,
            sensor_type=sensor_type,
            since_ts=since_ts,
            telemetry_max_age_sec=telemetry_max_age_sec,
            limit_per_sensor=limit_per_sensor,
            until_ts=until_ts,
        )

    async def read_solution_temp_window(
        self,
        *,
        zone_id: int,
        since_ts: datetime,
        until_ts: datetime,
        limit: int = 5000,
    ) -> Mapping[str, Any]:
        return await self._runtime_monitor_temperature.read_solution_temp_window(
            zone_id=zone_id, since_ts=since_ts, until_ts=until_ts, limit=limit
        )

    async def read_latest_irr_state(
        self,
        *,
        zone_id: int,
        max_age_sec: int,
        expected_cmd_id: str | None = None,
    ) -> Mapping[str, Any]:
        return await self._runtime_monitor_events.read_latest_irr_state(
            zone_id=zone_id, max_age_sec=max_age_sec, expected_cmd_id=expected_cmd_id
        )

    async def read_node_liveness(self, *, node_uid: str) -> Mapping[str, Any]:
        return await self._runtime_monitor_events.read_node_liveness(node_uid=node_uid)

    async def read_latest_zone_event(
        self,
        *,
        zone_id: int,
        event_types: Sequence[str],
        max_age_sec: int,
        since_ts: datetime | None = None,
        channel: str | None = None,
    ) -> Mapping[str, Any] | None:
        return await self._runtime_monitor_events.read_latest_zone_event(
            zone_id=zone_id, event_types=event_types, max_age_sec=max_age_sec, since_ts=since_ts, channel=channel
        )
