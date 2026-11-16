"""app runtime zone events: explicit dependencies and invocation data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ae3lite.application.level_monitor import level_snapshot_aliases


@dataclass(frozen=True)
class AppRuntimeZoneEventsPorts:
    node_runtime_event_kick: Callable[..., Any]
    runtime_critical_node_event_types: Callable[..., Any]
    coerce_optional_bool: Callable[..., Any]
    is_runtime_zone_event_relevant: Callable[..., Any]
    zone_event_indicates_solution_min_depletion: Callable[..., Any]
    send_service_log: Callable[..., Any]


class AppRuntimeZoneEvents:
    def __init__(self, ports: AppRuntimeZoneEventsPorts) -> None:
        self._ports = ports

    def coerce_optional_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if float(value) == 1.0:
                return True
            if float(value) == 0.0:
                return False
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return None

    def is_runtime_zone_event_relevant(self, data: Mapping[str, Any]) -> bool:
        source = str(data.get("source") or "").strip().lower()
        if source == "operator":
            return str(data.get("event_type") or "").strip().upper() == "EMERGENCY_STOP_ACTIVATED"
        if source != "node_event":
            return False
        event_type = str(data.get("event_type") or "").strip().upper()
        channel = str(data.get("channel") or "").strip().lower()
        return event_type in self._ports.runtime_critical_node_event_types() or channel == "storage_state"

    def zone_event_indicates_solution_min_depletion(self, data: Mapping[str, Any]) -> bool:
        channel = str(data.get("channel") or "").strip().lower()
        state = self._ports.coerce_optional_bool(data.get("state"))
        if channel and channel in level_snapshot_aliases("level_solution_min") and state is False:
            return True

        snapshot = data.get("snapshot")
        if not isinstance(snapshot, Mapping):
            return False
        for alias in level_snapshot_aliases("level_solution_min"):
            if alias not in snapshot:
                continue
            if self._ports.coerce_optional_bool(snapshot.get(alias)) is False:
                return True
        return False

    def build_zone_event_listener_callback(
        self,
        *,
        worker: Any,
        solution_tank_startup_guard_use_case: Any | None,
        trigger_solution_topup_from_level_event_use_case: Any | None,
        now_fn: Any,
        logger: logging.Logger,
    ) -> Any:
        async def _on_zone_event(data: dict[str, Any]) -> None:
            if not self._ports.is_runtime_zone_event_relevant(data):
                return

            zone_id_raw = data.get("zone_id")
            try:
                zone_id = int(zone_id_raw)
            except (TypeError, ValueError):
                zone_id = 0
            event_type = str(data.get("event_type") or "").strip().upper()
            channel = str(data.get("channel") or "").strip().lower()

            if (
                zone_id > 0
                and solution_tank_startup_guard_use_case is not None
                and self._ports.zone_event_indicates_solution_min_depletion(data)
            ):
                try:
                    guard_result = await solution_tank_startup_guard_use_case.run(zone_id=zone_id, now=now_fn())
                    logger.info(
                        "ZoneEventListener: solution tank guard evaluated zone_id=%s reset=%s reason=%s",
                        zone_id,
                        bool(guard_result.get("reset")),
                        guard_result.get("reason"),
                    )
                except Exception as exc:
                    logger.warning(
                        "ZoneEventListener: startup guard failed for zone_id=%s event_type=%s channel=%s error=%s",
                        zone_id,
                        event_type,
                        channel,
                        exc,
                        exc_info=True,
                    )

            if zone_id > 0 and trigger_solution_topup_from_level_event_use_case is not None:
                try:
                    topup_result = await trigger_solution_topup_from_level_event_use_case.run(
                        zone_id=zone_id,
                        event_data=data,
                        now=now_fn(),
                    )
                    if bool(topup_result.get("triggered")):
                        logger.info(
                            "ZoneEventListener: reactive solution_topup started zone_id=%s task_id=%s",
                            zone_id,
                            topup_result.get("task_id"),
                        )
                    else:
                        skip_reason = str(topup_result.get("reason") or "")
                        if skip_reason not in {
                            "event_type_not_relevant",
                            "channel_not_solution_max",
                            "initial_event_skipped",
                            "not_topup_start_edge",
                        }:
                            logger.info(
                                "ZoneEventListener: reactive solution_topup skipped zone_id=%s channel=%s reason=%s",
                                zone_id,
                                channel or None,
                                skip_reason or None,
                            )
                except Exception as exc:
                    logger.warning(
                        "ZoneEventListener: reactive solution_topup failed zone_id=%s event_type=%s channel=%s error=%s",
                        zone_id,
                        event_type,
                        channel,
                        exc,
                        exc_info=True,
                    )

            logger.info(
                "ZoneEventListener: node runtime event received zone_id=%s event_type=%s channel=%s state=%s initial=%s; kicking worker",
                zone_id if zone_id > 0 else None,
                event_type,
                channel or None,
                data.get("state"),
                data.get("initial"),
            )
            self._ports.node_runtime_event_kick().labels(
                event_type=event_type or "UNKNOWN",
                channel=channel or "unknown",
            ).inc()
            self._ports.send_service_log(
                service="automation-engine",
                level="info",
                message="AE3 worker.kick by node runtime event",
                context={
                    "zone_id": zone_id if zone_id > 0 else None,
                    "event_type": event_type,
                    "channel": channel or None,
                    "state": data.get("state"),
                    "initial": data.get("initial"),
                },
            )
            worker.kick()

        return _on_zone_event
