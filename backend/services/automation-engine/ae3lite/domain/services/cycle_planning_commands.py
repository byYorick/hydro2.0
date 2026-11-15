"""CycleStartPlanner commands: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Sequence

from ae3lite.application.dto import ZoneActuatorRef
from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import PlannerConfigurationError


@dataclass(frozen=True)
class CyclePlanningCommandsPorts:
    resolve_actuator: Callable[..., Any]


class CyclePlanningCommands:
    def __init__(self, ports: CyclePlanningCommandsPorts) -> None:
        self._ports = ports

    def build_named_step(
        self,
        *,
        raw_step: Mapping[str, Any],
        step_no: int,
        actuators: Sequence[ZoneActuatorRef],
    ) -> PlannedCommand:
        actuator = self._ports.resolve_actuator(
            actuators=actuators,
            requested_channel=str(raw_step.get("channel") or "").strip().lower(),
            node_types=self.normalize_node_types(raw_step.get("node_types")),
        )
        return PlannedCommand(
            step_no=step_no,
            node_uid=actuator.node_uid,
            channel=actuator.channel,
            payload={
                "cmd": str(raw_step["cmd"]),
                "params": dict(raw_step["params"]),
                "complete_on_ack": bool(raw_step.get("complete_on_ack")),
            },
        )

    def resolve_service_commands(
        self,
        *,
        actuators: Sequence[ZoneActuatorRef],
        cmd: str,
        params: Mapping[str, Any],
    ) -> list[PlannedCommand]:
        steps: list[PlannedCommand] = []
        for node_type in ("ph", "ec"):
            candidates = [
                actuator
                for actuator in actuators
                if str(actuator.node_type).strip().lower() == node_type
                and str(actuator.channel).strip().lower() == "system"
            ]
            if len(candidates) > 1:
                raise PlannerConfigurationError(f"Неоднозначное разрешение system channel для node_type={node_type}")
            if len(candidates) == 1:
                steps.append(
                    PlannedCommand(
                        step_no=len(steps) + 1,
                        node_uid=candidates[0].node_uid,
                        channel="system",
                        payload={"cmd": cmd, "params": dict(params)},
                    )
                )
        return steps

    def resolve_single_node_uid(
        self,
        *,
        actuators: Sequence[ZoneActuatorRef],
        node_types: Sequence[str],
    ) -> str:
        normalized_types = {str(item or "").strip().lower() for item in node_types if str(item or "").strip()}
        candidates = sorted(
            {
                str(actuator.node_uid).strip()
                for actuator in actuators
                if str(actuator.node_uid).strip()
                and (not normalized_types or str(actuator.node_type).strip().lower() in normalized_types)
            }
        )
        if len(candidates) != 1:
            raise PlannerConfigurationError(
                f"Ожидался ровно один runtime node для node_types={sorted(normalized_types)}"
            )
        return candidates[0]

    def normalize_node_types(self, raw_value: Any) -> List[str]:
        if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
            return []
        result: List[str] = []
        for item in raw_value:
            normalized = str(item or "").strip().lower()
            if normalized:
                result.append(normalized)
        return result
