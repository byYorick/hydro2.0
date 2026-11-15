"""Исполнение одного tick климата теплицы (DB + history-logger)."""

from __future__ import annotations
from datetime import datetime
from typing import Mapping
from ae3lite.greenhouse_climate.decision_engine import ClimateDecision
from ae3lite.infrastructure.clients import HistoryLoggerClient

import asyncio
import json
import logging
import time
from uuid import uuid4
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from statistics import median
from typing import Any, Mapping

from ae3lite.greenhouse_climate.decision_engine import compute_climate_decision
from ae3lite.infrastructure.clients import HistoryLoggerClient
from ae3lite.infrastructure.metrics import (
    GREENHOUSE_CLIMATE_COMMAND_FAILED_TOTAL,
    GREENHOUSE_CLIMATE_COMMAND_TOTAL,
    GREENHOUSE_CLIMATE_DECISION_DURATION_SECONDS,
    GREENHOUSE_CLIMATE_RAIN_CLAMP_TOTAL,
    GREENHOUSE_CLIMATE_SENSOR_STALE_TOTAL,
    GREENHOUSE_CLIMATE_TICK_TOTAL,
    GREENHOUSE_CLIMATE_WIND_CLAMP_TOTAL,
    record_greenhouse_climate_crop_metrics,
)
from common.alert_publisher import AlertPublisher
from common.db import execute, fetch, get_pool

logger = logging.getLogger(__name__)

_LEASE_OWNER_PREFIX = "ae3_greenhouse_climate"
_DEFAULT_LEASE_TTL_SEC = 300


from ae3lite.greenhouse_climate.climate_tick_records import _GreenhouseLeaseStop
from ae3lite.greenhouse_climate.climate_tick_coordination import ClimateTickCoordination, ClimateTickCoordinationPorts


def _climate_tick_coordination() -> ClimateTickCoordination:
    return ClimateTickCoordination(
        ClimateTickCoordinationPorts(
            claim_greenhouse_lease=lambda *args, **kwargs: _claim_greenhouse_lease(*args, **kwargs),
            complete_active_tick=lambda *args, **kwargs: _complete_active_tick(*args, **kwargs),
            complete_disabled_tick=lambda *args, **kwargs: _complete_disabled_tick(*args, **kwargs),
            complete_missing_bundle=lambda *args, **kwargs: _complete_missing_bundle(*args, **kwargs),
            ensure_state_row=lambda *args, **kwargs: _ensure_state_row(*args, **kwargs),
            execute_vent_commands=lambda *args, **kwargs: _execute_vent_commands(*args, **kwargs),
            expired_manual_override_return_mode=lambda *args, **kwargs: _expired_manual_override_return_mode(
                *args, **kwargs
            ),
            parse_bundle=lambda *args, **kwargs: _parse_bundle(*args, **kwargs),
            persist_tick_exception=lambda *args, **kwargs: _persist_tick_exception(*args, **kwargs),
            plan_active_tick=lambda *args, **kwargs: _plan_active_tick(*args, **kwargs),
            record_tick_metric=lambda *args, **kwargs: _record_tick_metric(*args, **kwargs),
            release_greenhouse_lease=lambda *args, **kwargs: _release_greenhouse_lease(*args, **kwargs),
            execute=lambda *args, **kwargs: execute(*args, **kwargs),
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
            logger=lambda: logger,
            resolve_greenhouse_lease_owner=lambda *args, **kwargs: resolve_greenhouse_lease_owner(*args, **kwargs),
            uuid4=lambda *args, **kwargs: uuid4(*args, **kwargs),
        )
    )


from ae3lite.greenhouse_climate.climate_tick_lease import ClimateTickLease, ClimateTickLeasePorts


def _climate_tick_lease() -> ClimateTickLease:
    return ClimateTickLease(
        ClimateTickLeasePorts(
            lease_owner_prefix=lambda: _LEASE_OWNER_PREFIX,
            execute=lambda *args, **kwargs: execute(*args, **kwargs),
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
        )
    )


from ae3lite.greenhouse_climate.climate_tick_configuration import (
    ClimateTickConfiguration,
    ClimateTickConfigurationPorts,
)


def _climate_tick_configuration() -> ClimateTickConfiguration:
    return ClimateTickConfiguration(ClimateTickConfigurationPorts())


from ae3lite.greenhouse_climate.climate_tick_state_queries import ClimateTickStateQueries, ClimateTickStateQueriesPorts


def _climate_tick_state_queries() -> ClimateTickStateQueries:
    return ClimateTickStateQueries(
        ClimateTickStateQueriesPorts(
            execute=lambda *args, **kwargs: execute(*args, **kwargs),
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
        )
    )


from ae3lite.greenhouse_climate.climate_tick_alerts import ClimateTickAlerts, ClimateTickAlertsPorts


def _climate_tick_alerts() -> ClimateTickAlerts:
    return ClimateTickAlerts(
        ClimateTickAlertsPorts(
            greenhouse_climate_decision_duration_seconds=lambda: GREENHOUSE_CLIMATE_DECISION_DURATION_SECONDS,
            greenhouse_climate_tick_total=lambda: GREENHOUSE_CLIMATE_TICK_TOTAL,
            alert_publisher=lambda: _ALERT_PUBLISHER,
            greenhouse_alert_codes=lambda: _GREENHOUSE_ALERT_CODES,
            alert_severity=lambda *args, **kwargs: _alert_severity(*args, **kwargs),
            as_float=lambda *args, **kwargs: _as_float(*args, **kwargs),
            unique_alert_codes=lambda *args, **kwargs: _unique_alert_codes(*args, **kwargs),
            logger=lambda: logger,
        )
    )


from ae3lite.greenhouse_climate.climate_tick_sensors import ClimateTickSensors, ClimateTickSensorsPorts


def _climate_tick_sensors() -> ClimateTickSensors:
    return ClimateTickSensors(
        ClimateTickSensorsPorts(
            core_outside_weather_keys=lambda: _CORE_OUTSIDE_WEATHER_KEYS,
            outside_channel_hints=lambda: _OUTSIDE_CHANNEL_HINTS,
            outside_sensor_types=lambda: _OUTSIDE_SENSOR_TYPES,
            accumulate_sensor_row=lambda *args, **kwargs: _accumulate_sensor_row(*args, **kwargs),
            as_float=lambda *args, **kwargs: _as_float(*args, **kwargs),
            is_truthy_sensor_value=lambda *args, **kwargs: _is_truthy_sensor_value(*args, **kwargs),
            load_shared_weather_station_node_id=lambda *args, **kwargs: _load_shared_weather_station_node_id(
                *args, **kwargs
            ),
            weather_station_fresh=lambda *args, **kwargs: _weather_station_fresh(*args, **kwargs),
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
        )
    )


from ae3lite.greenhouse_climate.climate_tick_targets import ClimateTickTargets, ClimateTickTargetsPorts


def _climate_tick_targets() -> ClimateTickTargets:
    return ClimateTickTargets(
        ClimateTickTargetsPorts(
            as_float=lambda *args, **kwargs: _as_float(*args, **kwargs),
            greenhouse_targets=lambda *args, **kwargs: _greenhouse_targets(*args, **kwargs),
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
        )
    )


from ae3lite.greenhouse_climate.climate_tick_command_wait import ClimateTickCommandWait, ClimateTickCommandWaitPorts


def _climate_tick_command_wait() -> ClimateTickCommandWait:
    return ClimateTickCommandWait(
        ClimateTickCommandWaitPorts(
            lease_lost_status=lambda: _LEASE_LOST_STATUS,
            terminal_statuses=lambda: _TERMINAL_STATUSES,
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
            logger=lambda: logger,
        )
    )


from ae3lite.greenhouse_climate.climate_tick_planning import ClimateTickPlanning, ClimateTickPlanningPorts


def _climate_tick_planning() -> ClimateTickPlanning:
    return ClimateTickPlanning(
        ClimateTickPlanningPorts(
            greenhouse_climate_rain_clamp_total=lambda: GREENHOUSE_CLIMATE_RAIN_CLAMP_TOTAL,
            greenhouse_climate_sensor_stale_total=lambda: GREENHOUSE_CLIMATE_SENSOR_STALE_TOTAL,
            greenhouse_climate_wind_clamp_total=lambda: GREENHOUSE_CLIMATE_WIND_CLAMP_TOTAL,
            load_greenhouse_timezone=lambda *args, **kwargs: _load_greenhouse_timezone(*args, **kwargs),
            load_manual_override=lambda *args, **kwargs: _load_manual_override(*args, **kwargs),
            load_vents=lambda *args, **kwargs: _load_vents(*args, **kwargs),
            resolve_target_policy=lambda *args, **kwargs: _resolve_target_policy(*args, **kwargs),
            schedule_day_for_greenhouse=lambda *args, **kwargs: _schedule_day_for_greenhouse(*args, **kwargs),
            sensor_snapshot=lambda *args, **kwargs: _sensor_snapshot(*args, **kwargs),
            spread_alerts=lambda *args, **kwargs: _spread_alerts(*args, **kwargs),
            unique_alert_codes=lambda *args, **kwargs: _unique_alert_codes(*args, **kwargs),
            compute_climate_decision=lambda *args, **kwargs: compute_climate_decision(*args, **kwargs),
            record_greenhouse_climate_crop_metrics=lambda *args, **kwargs: record_greenhouse_climate_crop_metrics(
                *args, **kwargs
            ),
        )
    )


from ae3lite.greenhouse_climate.climate_tick_commands import ClimateTickCommands, ClimateTickCommandsPorts


def _climate_tick_commands() -> ClimateTickCommands:
    return ClimateTickCommands(
        ClimateTickCommandsPorts(
            greenhouse_climate_command_failed_total=lambda: GREENHOUSE_CLIMATE_COMMAND_FAILED_TOTAL,
            greenhouse_climate_command_total=lambda: GREENHOUSE_CLIMATE_COMMAND_TOTAL,
            lease_lost_status=lambda: _LEASE_LOST_STATUS,
            lease_renew_transient_budget=lambda: _LEASE_RENEW_TRANSIENT_BUDGET,
            success_status=lambda: _SUCCESS_STATUS,
            renew_greenhouse_lease=lambda *args, **kwargs: _renew_greenhouse_lease(*args, **kwargs),
            wait_command_terminal=lambda *args, **kwargs: _wait_command_terminal(*args, **kwargs),
            logger=lambda: logger,
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
        )
    )


from ae3lite.greenhouse_climate.climate_tick_completion import ClimateTickCompletion, ClimateTickCompletionPorts


def _climate_tick_completion() -> ClimateTickCompletion:
    return ClimateTickCompletion(
        ClimateTickCompletionPorts(
            lease_lost_status=lambda: _LEASE_LOST_STATUS,
            load_manual_override=lambda *args, **kwargs: _load_manual_override(*args, **kwargs),
            lock_owned_greenhouse_lease=lambda *args, **kwargs: _lock_owned_greenhouse_lease(*args, **kwargs),
            publish_greenhouse_alert_lifecycle=lambda *args, **kwargs: _publish_greenhouse_alert_lifecycle(
                *args, **kwargs
            ),
            record_tick_metric=lambda *args, **kwargs: _record_tick_metric(*args, **kwargs),
            unique_alert_codes=lambda *args, **kwargs: _unique_alert_codes(*args, **kwargs),
            get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            logger=lambda: logger,
        )
    )


def resolve_greenhouse_lease_owner(*, worker_owner: str | None = None) -> str:
    return _climate_tick_lease().resolve_greenhouse_lease_owner(worker_owner=worker_owner)


_TERMINAL_STATUSES = {"DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"}
_SUCCESS_STATUS = "DONE"
_LEASE_LOST_STATUS = "LEASE_LOST"
# Одна транспортная ошибка renew не отменяет текущую команду. Следующая — стоп.
_LEASE_RENEW_TRANSIENT_BUDGET = 1


_ALERT_PUBLISHER = AlertPublisher(default_source="biz")
_GREENHOUSE_ALERT_CODES = {
    "GREENHOUSE_WEATHER_STATION_STALE",
    "GREENHOUSE_INSIDE_CLIMATE_STALE",
    "GREENHOUSE_CLIMATE_SENSOR_SPREAD_HIGH",
    "GREENHOUSE_TARGET_CONFLICT",
    "GREENHOUSE_TARGET_POLICY_INVALID",
    "GREENHOUSE_OVERHEAT_EMERGENCY",
    "GREENHOUSE_WIND_CLAMP_ACTIVE",
    "GREENHOUSE_RAIN_CLAMP_ACTIVE",
    "GREENHOUSE_VENT_COMMAND_FAILED",
}


def _parse_bundle(config: Mapping[str, Any] | None) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
    return _climate_tick_configuration().parse_bundle(config=config)


async def _ensure_state_row(greenhouse_id: int) -> None:
    return await _climate_tick_state_queries().ensure_state_row(greenhouse_id=greenhouse_id)


async def _load_manual_override(greenhouse_id: int) -> dict[str, Any] | None:
    return await _climate_tick_state_queries().load_manual_override(greenhouse_id=greenhouse_id)


async def _expired_manual_override_return_mode(greenhouse_id: int, state: Mapping[str, Any]) -> str | None:
    return await _climate_tick_state_queries().expired_manual_override_return_mode(
        greenhouse_id=greenhouse_id, state=state
    )


async def _claim_greenhouse_lease(
    greenhouse_id: int,
    *,
    owner: str,
    ttl_sec: int = _DEFAULT_LEASE_TTL_SEC,
) -> bool:
    return await _climate_tick_lease().claim_greenhouse_lease(greenhouse_id=greenhouse_id, owner=owner, ttl_sec=ttl_sec)


async def _renew_greenhouse_lease(
    greenhouse_id: int,
    *,
    owner: str,
    ttl_sec: int = _DEFAULT_LEASE_TTL_SEC,
) -> bool:
    return await _climate_tick_lease().renew_greenhouse_lease(greenhouse_id=greenhouse_id, owner=owner, ttl_sec=ttl_sec)


async def _release_greenhouse_lease(greenhouse_id: int, *, owner: str) -> None:
    return await _climate_tick_lease().release_greenhouse_lease(greenhouse_id=greenhouse_id, owner=owner)


async def _lock_owned_greenhouse_lease(conn: Any, *, greenhouse_id: int, owner: str) -> bool:
    return await _climate_tick_lease().lock_owned_greenhouse_lease(conn=conn, greenhouse_id=greenhouse_id, owner=owner)


def _as_float(value: Any) -> float | None:
    return _climate_tick_configuration().as_float(value=value)


def _is_truthy_sensor_value(value: float) -> bool:
    return _climate_tick_configuration().is_truthy_sensor_value(value=value)


def _alert_severity(code: str) -> str:
    return _climate_tick_alerts().alert_severity(code=code)


def _unique_alert_codes(codes: list[str]) -> list[str]:
    return _climate_tick_alerts().unique_alert_codes(codes=codes)


async def _publish_greenhouse_alert_lifecycle(
    *,
    greenhouse_id: int,
    active_codes: list[str],
    details: Mapping[str, Any],
    alert_publisher: Any,
) -> None:
    return await _climate_tick_alerts().publish_greenhouse_alert_lifecycle(
        greenhouse_id=greenhouse_id, active_codes=active_codes, details=details, alert_publisher=alert_publisher
    )


def _record_tick_metric(start_monotonic: float, status: str) -> None:
    return _climate_tick_alerts().record_tick_metric(start_monotonic=start_monotonic, status=status)


def _spread_alerts(snapshot: Mapping[str, Any], execution: Mapping[str, Any]) -> list[str]:
    return _climate_tick_alerts().spread_alerts(snapshot=snapshot, execution=execution)


_CORE_OUTSIDE_WEATHER_KEYS = (
    "outside_temp",
    "outside_humidity",
    "wind_speed",
)


def _weather_station_fresh(outside_fresh: Mapping[str, bool]) -> bool:
    return _climate_tick_sensors().weather_station_fresh(outside_fresh=outside_fresh)


async def _load_shared_weather_station_node_id(greenhouse_id: int) -> int | None:
    return await _climate_tick_sensors().load_shared_weather_station_node_id(greenhouse_id=greenhouse_id)


def _accumulate_sensor_row(
    row: Mapping[str, Any],
    *,
    freshness_sec: int,
    now: datetime,
    inside_temps: list[float],
    inside_rhs: list[float],
    inside_pressures: list[float],
    outside_fresh: dict[str, bool],
    outdoor_state: dict[str, Any],
    allow_inside: bool,
    allow_outside: bool,
) -> bool:
    return _climate_tick_sensors().accumulate_sensor_row(
        row=row,
        freshness_sec=freshness_sec,
        now=now,
        inside_temps=inside_temps,
        inside_rhs=inside_rhs,
        inside_pressures=inside_pressures,
        outside_fresh=outside_fresh,
        outdoor_state=outdoor_state,
        allow_inside=allow_inside,
        allow_outside=allow_outside,
    )


_OUTSIDE_SENSOR_TYPES = frozenset(
    {
        "OUTSIDE_TEMP",
        "OUTSIDE_HUMIDITY",
        "OUTSIDE_PRESSURE",
        "OUTSIDE_LIGHT",
        "WIND_SPEED",
        "WIND_DIRECTION",
        "RAIN_DETECTED",
    }
)

_OUTSIDE_CHANNEL_HINTS = frozenset(
    {
        "outside_temp",
        "outside_humidity",
        "outside_pressure",
        "outside_light",
        "outdoor_temp",
        "outdoor_humidity",
        "wind_speed",
        "wind_direction",
        "rain_detected",
        "rain",
    }
)


async def _sensor_snapshot(greenhouse_id: int, freshness_sec: int) -> dict[str, Any]:
    return await _climate_tick_sensors().sensor_snapshot(greenhouse_id=greenhouse_id, freshness_sec=freshness_sec)


async def _load_vents(greenhouse_id: int) -> dict[str, dict[str, Any]]:
    return await _climate_tick_state_queries().load_vents(greenhouse_id=greenhouse_id)


async def _load_greenhouse_timezone(greenhouse_id: int) -> str:
    return await _climate_tick_targets().load_greenhouse_timezone(greenhouse_id=greenhouse_id)


def _schedule_day_for_greenhouse(*, greenhouse_tz: str, execution: Mapping[str, Any]) -> bool:
    return _climate_tick_targets().schedule_day_for_greenhouse(greenhouse_tz=greenhouse_tz, execution=execution)


def _greenhouse_targets(execution: Mapping[str, Any]) -> dict[str, float]:
    return _climate_tick_targets().greenhouse_targets(execution=execution)


async def _resolve_target_policy(
    greenhouse_id: int,
    execution: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    return await _climate_tick_targets().resolve_target_policy(greenhouse_id=greenhouse_id, execution=execution)


async def _wait_command_terminal(
    cmd_id: str,
    *,
    timeout_sec: float,
    poll_sec: float = 1.0,
    lease_renew: Any | None = None,
    renew_interval_sec: float | None = None,
) -> str:
    return await _climate_tick_command_wait().wait_command_terminal(
        cmd_id=cmd_id,
        timeout_sec=timeout_sec,
        poll_sec=poll_sec,
        lease_renew=lease_renew,
        renew_interval_sec=renew_interval_sec,
    )


async def _complete_missing_bundle(
    *, greenhouse_id: int, lease_owner: str, intent_id: int, task_id: int | None, tick_started: float
) -> Any:
    return await _climate_tick_completion().complete_missing_bundle(
        greenhouse_id=greenhouse_id,
        lease_owner=lease_owner,
        intent_id=intent_id,
        task_id=task_id,
        tick_started=tick_started,
    )


async def _complete_disabled_tick(
    *,
    greenhouse_id: int,
    lease_owner: str,
    intent_id: int,
    task_id: int | None,
    tick_started: float,
    state: Mapping[str, Any],
    control_mode: str,
    alert_publisher: Any,
) -> Any:
    return await _climate_tick_completion().complete_disabled_tick(
        greenhouse_id=greenhouse_id,
        lease_owner=lease_owner,
        intent_id=intent_id,
        task_id=task_id,
        tick_started=tick_started,
        state=state,
        control_mode=control_mode,
        alert_publisher=alert_publisher,
    )


async def _plan_active_tick(
    *, greenhouse_id: int, execution: Mapping[str, Any], state: Mapping[str, Any], control_mode: str
) -> Any:
    return await _climate_tick_planning().plan_active_tick(
        greenhouse_id=greenhouse_id, execution=execution, state=state, control_mode=control_mode
    )


async def _execute_vent_commands(
    *,
    greenhouse_id: int,
    execution: Mapping[str, Any],
    state: Mapping[str, Any],
    decision: ClimateDecision,
    vents: Mapping[str, Mapping[str, Any]],
    lease_owner: str,
    lease_ttl_sec: int,
    idempotency_key: str,
    history_logger_client: HistoryLoggerClient,
) -> Any:
    return await _climate_tick_commands().execute_vent_commands(
        greenhouse_id=greenhouse_id,
        execution=execution,
        state=state,
        decision=decision,
        vents=vents,
        lease_owner=lease_owner,
        lease_ttl_sec=lease_ttl_sec,
        idempotency_key=idempotency_key,
        history_logger_client=history_logger_client,
    )


async def _complete_active_tick(
    *,
    greenhouse_id: int,
    lease_owner: str,
    intent_id: int,
    task_id: int | None,
    tick_started: float,
    state: Mapping[str, Any],
    decision: ClimateDecision,
    left_cmd_id: str | None,
    right_cmd_id: str | None,
    left_done: bool,
    right_done: bool,
    command_failures: list[str],
    control_mode: str,
    snap: Mapping[str, Any],
    next_tick_active: datetime,
    active_override_id: int | None,
    active_alerts: list[str],
    alert_publisher: Any,
) -> Any:
    return await _climate_tick_completion().complete_active_tick(
        greenhouse_id=greenhouse_id,
        lease_owner=lease_owner,
        intent_id=intent_id,
        task_id=task_id,
        tick_started=tick_started,
        state=state,
        decision=decision,
        left_cmd_id=left_cmd_id,
        right_cmd_id=right_cmd_id,
        left_done=left_done,
        right_done=right_done,
        command_failures=command_failures,
        control_mode=control_mode,
        snap=snap,
        next_tick_active=next_tick_active,
        active_override_id=active_override_id,
        active_alerts=active_alerts,
        alert_publisher=alert_publisher,
    )


async def _persist_tick_exception(
    *, greenhouse_id: int, lease_owner: str, intent_id: int, task_id: int | None, exc: Exception
) -> Any:
    return await _climate_tick_completion().persist_tick_exception(
        greenhouse_id=greenhouse_id, lease_owner=lease_owner, intent_id=intent_id, task_id=task_id, exc=exc
    )


async def run_greenhouse_climate_tick(
    *,
    greenhouse_id: int,
    idempotency_key: str,
    history_logger_client: HistoryLoggerClient,
    alert_publisher: Any = _ALERT_PUBLISHER,
    worker_owner: str | None = None,
    lease_ttl_sec: int = _DEFAULT_LEASE_TTL_SEC,
) -> dict[str, Any]:
    return await _climate_tick_coordination().run_greenhouse_climate_tick(
        greenhouse_id=greenhouse_id,
        idempotency_key=idempotency_key,
        history_logger_client=history_logger_client,
        alert_publisher=alert_publisher,
        worker_owner=worker_owner,
        lease_ttl_sec=lease_ttl_sec,
    )


__all__ = ["run_greenhouse_climate_tick"]
