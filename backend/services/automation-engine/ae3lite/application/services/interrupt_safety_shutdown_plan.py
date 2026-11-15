"""interrupt safety shutdown plan: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ae3lite.domain.entities.planned_command import PlannedCommand


@dataclass(frozen=True)
class InterruptSafetyShutdownPlanPorts:
    fail_safe_shutdown_channels: Callable[..., Any]
    fetch: Callable[..., Any]


class InterruptSafetyShutdownPlan:
    def __init__(self, ports: InterruptSafetyShutdownPlanPorts) -> None:
        self._ports = ports

    async def load_irrig_fail_safe_actuators(self, *, zone_id: int) -> tuple[Mapping[str, Any], ...]:
        """Активные ACTUATOR/SERVICE каналы irrig-нод зоны для fail-safe OFF publish."""
        rows = await self._ports.fetch(
            """
            SELECT
                n.uid AS node_uid,
                LOWER(COALESCE(n.type, '')) AS node_type,
                LOWER(TRIM(COALESCE(nc.channel, ''))) AS channel
            FROM nodes n
            JOIN node_channels nc ON nc.node_id = n.id
            WHERE n.zone_id = $1
              AND LOWER(COALESCE(n.type, '')) = 'irrig'
              AND UPPER(TRIM(COALESCE(nc.type, ''))) IN ('ACTUATOR', 'SERVICE')
              AND COALESCE(nc.is_active, TRUE) = TRUE
            ORDER BY n.id ASC, nc.id ASC
            """,
            zone_id,
        )
        out: list[dict[str, Any]] = []
        for row in rows or ():
            node_uid = str(row.get("node_uid") or "").strip()
            channel = str(row.get("channel") or "").strip().lower()
            if not node_uid or not channel:
                continue
            if channel not in self._ports.fail_safe_shutdown_channels():
                continue
            out.append(
                {
                    "node_uid": node_uid,
                    "node_type": "irrig",
                    "channel": channel,
                }
            )
        return tuple(out)

    def build_fail_safe_shutdown_commands(
        self, *, actuators: Sequence[Mapping[str, Any]], planner_step_prefix: str
    ) -> tuple[PlannedCommand, ...]:
        """Строит OFF set_relay batch: pump_main строго первым, только irrig-каналы."""
        prefix = str(planner_step_prefix or "fail_safe_shutdown").strip() or "fail_safe_shutdown"
        pump: list[PlannedCommand] = []
        other: list[PlannedCommand] = []
        seen: set[tuple[str, str]] = set()
        for actuator in actuators:
            node_uid = str(actuator.get("node_uid") or "").strip()
            node_type = str(actuator.get("node_type") or "").strip().lower()
            channel = str(actuator.get("channel") or "").strip().lower()
            if not node_uid or node_type != "irrig" or channel not in self._ports.fail_safe_shutdown_channels():
                continue
            pair = (node_uid, channel)
            if pair in seen:
                continue
            seen.add(pair)
            cmd = PlannedCommand(
                step_no=0,
                node_uid=node_uid,
                channel=channel,
                payload={
                    "name": "fail_safe_shutdown",
                    "cmd": "set_relay",
                    "params": {"state": False},
                    "allow_no_effect": True,
                    "dedupe_bypass": True,
                    "_ae3_fail_safe": True,
                },
            )
            if channel == "pump_main":
                pump.append(cmd)
            else:
                other.append(cmd)
        ordered = [*pump, *other]
        return tuple(
            PlannedCommand(
                step_no=idx + 1,
                node_uid=item.node_uid,
                channel=item.channel,
                planner_step=f"{prefix}:{idx + 1}:{item.channel}"[:160],
                payload=item.payload,
            )
            for idx, item in enumerate(ordered)
        )

    def normalize_fail_safe_actuators(self, actuators: Sequence[Any]) -> tuple[Mapping[str, Any], ...]:
        out: list[Mapping[str, Any]] = []
        for actuator in actuators:
            if isinstance(actuator, Mapping):
                out.append(
                    {
                        "node_uid": str(actuator.get("node_uid") or "").strip(),
                        "node_type": str(actuator.get("node_type") or "").strip().lower(),
                        "channel": str(actuator.get("channel") or "").strip().lower(),
                    }
                )
                continue
            out.append(
                {
                    "node_uid": str(getattr(actuator, "node_uid", "") or "").strip(),
                    "node_type": str(getattr(actuator, "node_type", "") or "").strip().lower(),
                    "channel": str(getattr(actuator, "channel", "") or "").strip().lower(),
                }
            )
        return tuple(out)

    def topology_fail_safe_on_flow(self, topology: str) -> bool:
        from ae3lite.application.services.workflow_topology import TopologyRegistry

        pack = TopologyRegistry().try_pack(str(topology or "").strip().lower())
        return pack is not None and pack.fail_safe_on_flow
