"""climate tick commands: explicit dependencies and invocation data."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from ae3lite.greenhouse_climate.climate_tick_records import ClimateCommandResult, _GreenhouseLeaseStop
from ae3lite.greenhouse_climate.decision_engine import ClimateDecision
from ae3lite.infrastructure.clients import HistoryLoggerClient


@dataclass(frozen=True)
class ClimateTickCommandsPorts:
    greenhouse_climate_command_failed_total: Callable[..., Any]
    greenhouse_climate_command_total: Callable[..., Any]
    lease_lost_status: Callable[..., Any]
    lease_renew_transient_budget: Callable[..., Any]
    success_status: Callable[..., Any]
    renew_greenhouse_lease: Callable[..., Any]
    wait_command_terminal: Callable[..., Any]
    logger: Callable[..., Any]
    fetch: Callable[..., Any]


class ClimateTickCommands:
    def __init__(self, ports: ClimateTickCommandsPorts) -> None:
        self._ports = ports

    async def execute_vent_commands(
        self,
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
    ) -> ClimateCommandResult:
        left_cmd_id = None
        right_cmd_id = None
        left_done = False
        right_done = False
        command_failures: list[str] = []
        lease_renew_failures = 0
        stop_ordinary_commands = False

        async def _climate_lease_renew() -> bool | None:
            nonlocal lease_renew_failures
            try:
                renewed = await self._ports.renew_greenhouse_lease(
                    greenhouse_id,
                    owner=lease_owner,
                    ttl_sec=lease_ttl_sec,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                lease_renew_failures += 1
                self._ports.logger().warning(
                    "greenhouse_climate_tick lease renew transport error gh=%s failures=%s",
                    greenhouse_id,
                    lease_renew_failures,
                    exc_info=True,
                )
                if lease_renew_failures > self._ports.lease_renew_transient_budget():
                    raise _GreenhouseLeaseStop()
                return None
            if renewed is False:
                raise _GreenhouseLeaseStop()
            return True

        renew_interval_raw = execution.get("lease_renew_interval_sec")
        renew_interval_sec = float(renew_interval_raw) if renew_interval_raw is not None else None
        if not decision.suppress_commands:
            for side, channel in (("left", "roof_vent_left"), ("right", "roof_vent_right")):
                if stop_ordinary_commands:
                    break
                if side not in decision.command_sides:
                    continue
                target = decision.left_target_pct if side == "left" else decision.right_target_pct
                cur = (
                    int(state.get("left_position_pct") or 0)
                    if side == "left"
                    else int(state.get("right_position_pct") or 0)
                )
                if target == cur:
                    continue
                vent = vents.get(channel)
                if not vent or not vent.get("node_uid") or int(vent.get("zone_id") or 0) <= 0:
                    self._ports.logger().warning(
                        "greenhouse_climate_tick missing vent binding channel=%s gh=%s", channel, greenhouse_id
                    )
                    command_failures.append(f"{channel}:MISSING_BINDING")
                    self._ports.greenhouse_climate_command_failed_total().labels(
                        side=side, failure="MISSING_BINDING"
                    ).inc()
                    continue
                try:
                    renewed = await _climate_lease_renew()
                    if renewed is None:
                        # One transport error is tolerated for an in-flight
                        # command, but a new command needs confirmed ownership.
                        if await _climate_lease_renew() is not True:
                            raise _GreenhouseLeaseStop()
                except asyncio.CancelledError:
                    raise
                except _GreenhouseLeaseStop:
                    command_failures.append(f"{channel}:{self._ports.lease_lost_status()}")
                    self._ports.greenhouse_climate_command_failed_total().labels(
                        side=side, failure=self._ports.lease_lost_status()
                    ).inc()
                    stop_ordinary_commands = True
                    break
                params = {
                    "position_pct": int(target),
                    "max_step_pct": int(float(execution.get("max_step_pct") or 25)),
                    "reason": decision.decision_reason,
                }
                cmd_id = f"ghc-{greenhouse_id}-{idempotency_key}-{side}-{target}"
                try:
                    hl_id = await history_logger_client.publish(
                        greenhouse_uid=str(vent["greenhouse_uid"]),
                        zone_id=int(vent["zone_id"]),
                        node_uid=str(vent["node_uid"]),
                        channel=channel,
                        cmd="set_position",
                        params=params,
                        cmd_id=cmd_id,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._ports.logger().warning(
                        "greenhouse_climate_tick command publish failed gh=%s channel=%s",
                        greenhouse_id,
                        channel,
                        exc_info=True,
                    )
                    command_failures.append(f"{channel}:SEND_FAILED")
                    self._ports.greenhouse_climate_command_total().labels(side=side, status="SEND_FAILED").inc()
                    self._ports.greenhouse_climate_command_failed_total().labels(side=side, failure="SEND_FAILED").inc()
                    continue
                if side == "left":
                    left_cmd_id = hl_id
                else:
                    right_cmd_id = hl_id

                terminal = await self._ports.wait_command_terminal(
                    hl_id,
                    timeout_sec=float(execution.get("command_terminal_timeout_sec") or 120),
                    poll_sec=float(execution.get("command_poll_sec") or 1),
                    lease_renew=_climate_lease_renew,
                    renew_interval_sec=renew_interval_sec,
                )
                if terminal == self._ports.lease_lost_status():
                    command_failures.append(f"{channel}:{self._ports.lease_lost_status()}")
                    stop_ordinary_commands = True
                    self._ports.greenhouse_climate_command_total().labels(side=side, status=terminal).inc()
                    self._ports.greenhouse_climate_command_failed_total().labels(side=side, failure=terminal).inc()
                    break
                if terminal == self._ports.success_status():
                    if side == "left":
                        left_done = True
                    else:
                        right_done = True
                else:
                    command_failures.append(f"{channel}:{terminal}")
                self._ports.greenhouse_climate_command_total().labels(side=side, status=terminal).inc()
                if terminal != self._ports.success_status():
                    self._ports.greenhouse_climate_command_failed_total().labels(side=side, failure=terminal).inc()
                if stop_ordinary_commands:
                    break
                try:
                    await _climate_lease_renew()
                except asyncio.CancelledError:
                    raise
                except _GreenhouseLeaseStop:
                    command_failures.append(f"{channel}:{self._ports.lease_lost_status()}")
                    stop_ordinary_commands = True
                    break
        await self._publish_exhaust_if_changed(
            greenhouse_id=greenhouse_id,
            state=state,
            decision=decision,
            idempotency_key=idempotency_key,
            history_logger_client=history_logger_client,
            stop_ordinary_commands=stop_ordinary_commands,
            lease_renew=_climate_lease_renew, execution=execution, command_failures=command_failures,
        )
        return ClimateCommandResult(left_cmd_id, right_cmd_id, left_done, right_done, command_failures)

    async def _publish_exhaust_if_changed(
        self,
        *,
        greenhouse_id: int,
        state: Mapping[str, Any],
        decision: ClimateDecision,
        idempotency_key: str,
        history_logger_client: HistoryLoggerClient,
        stop_ordinary_commands: bool,
        lease_renew: Callable[..., Any],
        execution: Mapping[str, Any],
        command_failures: list[str],
    ) -> None:
        control_mode = str(state.get("control_mode") or "auto").strip().lower()
        desired = bool((decision.factors or {}).get("exhaust_on"))
        previous = _previous_exhaust_on(state)
        if control_mode != "auto" or decision.suppress_commands or stop_ordinary_commands or desired == previous:
            return
        try:
            rows = await self._ports.fetch(
                """
                SELECT nc.channel AS channel,
                       n.uid AS node_uid,
                       n.zone_id AS zone_id,
                       g.uid AS greenhouse_uid
                FROM channel_bindings cb
                JOIN infrastructure_instances ii ON ii.id = cb.infrastructure_instance_id
                JOIN node_channels nc ON nc.id = cb.node_channel_id
                JOIN nodes n ON n.id = nc.node_id
                JOIN zones z ON z.id = n.zone_id
                JOIN greenhouses g ON g.id = ii.owner_id
                WHERE ii.owner_type = 'greenhouse'
                  AND ii.owner_id = $1
                  AND z.greenhouse_id = ii.owner_id
                  AND cb.direction = 'actuator'
                  AND cb.role = 'fan_actuator'
                  AND nc.is_active IS TRUE
                """,
                greenhouse_id,
            )
        except Exception:
            self._ports.logger().warning(
                "greenhouse_climate_tick exhaust bindings failed gh=%s", greenhouse_id, exc_info=True
            )
            return
        for row in rows or []:
            channel = str(row.get("channel") or "")
            node_uid = str(row.get("node_uid") or "")
            zone_id = int(row.get("zone_id") or 0)
            if not channel or not node_uid or zone_id <= 0:
                continue
            try:
                if await lease_renew() is not True and await lease_renew() is not True:
                    raise _GreenhouseLeaseStop()
            except _GreenhouseLeaseStop:
                command_failures.append(f"{channel}:{self._ports.lease_lost_status()}")
                break
            try:
                hl_id = await history_logger_client.publish(
                    greenhouse_uid=str(row.get("greenhouse_uid") or ""),
                    zone_id=zone_id,
                    node_uid=node_uid,
                    channel=channel,
                    cmd="set_relay",
                    params={"state": desired, "reason": "exhaust_hysteresis"},
                    cmd_id=f"ghc-{greenhouse_id}-{idempotency_key}-fan-{channel}-{int(desired)}",
                )
                terminal = await self._ports.wait_command_terminal(
                    hl_id,
                    timeout_sec=float(execution.get("command_terminal_timeout_sec") or 120),
                    poll_sec=float(execution.get("command_poll_sec") or 1),
                    lease_renew=lease_renew,
                    renew_interval_sec=execution.get("lease_renew_interval_sec"),
                )
                self._ports.greenhouse_climate_command_total().labels(side="fan", status=terminal).inc()
                if terminal != self._ports.success_status():
                    command_failures.append(f"{channel}:{terminal}")
                    self._ports.greenhouse_climate_command_failed_total().labels(side="fan", failure=terminal).inc()
                if terminal == self._ports.lease_lost_status():
                    break
            except asyncio.CancelledError:
                raise
            except Exception:
                self._ports.logger().warning(
                    "greenhouse_climate_tick exhaust command failed gh=%s channel=%s",
                    greenhouse_id,
                    channel,
                    exc_info=True,
                )


def _previous_exhaust_on(state: Mapping[str, Any]) -> bool:
    raw = state.get("decision_factors")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return False
    if isinstance(raw, dict):
        return bool(raw.get("exhaust_on"))
    return False
