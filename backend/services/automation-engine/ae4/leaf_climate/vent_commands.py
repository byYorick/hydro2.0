"""Список команд форточек из решения. Пустой список — E211 или suppress."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ae4.leaf_climate.decision import ClimateDecision


@dataclass(frozen=True)
class VentCommand:
    side: str
    channel: str
    position_pct: int
    node_uid: str
    zone_id: int
    greenhouse_uid: str
    max_step_pct: int
    reason: str


_SIDE_CHANNEL = (("left", "roof_vent_left"), ("right", "roof_vent_right"))


def list_vent_commands(
    *,
    decision: ClimateDecision,
    vents: Mapping[str, Mapping[str, Any]],
    current_left_pct: int,
    current_right_pct: int,
    max_step_pct: int,
) -> list[VentCommand]:
    """Команды set_position. suppress / пустые стороны / нет свежего воздуха → []."""
    if decision.suppress_commands or not decision.command_sides:
        return []
    out: list[VentCommand] = []
    for side, channel in _SIDE_CHANNEL:
        if side not in decision.command_sides:
            continue
        target = (
            decision.left_target_pct if side == "left" else decision.right_target_pct
        )
        cur = int(current_left_pct if side == "left" else current_right_pct)
        if int(target) == cur:
            continue
        vent = vents.get(channel)
        if not isinstance(vent, Mapping):
            continue
        node_uid = str(vent.get("node_uid") or "").strip()
        zone_id = int(vent.get("zone_id") or 0)
        greenhouse_uid = str(vent.get("greenhouse_uid") or "").strip()
        if not node_uid or zone_id <= 0 or not greenhouse_uid:
            continue
        out.append(
            VentCommand(
                side=side,
                channel=channel,
                position_pct=int(target),
                node_uid=node_uid,
                zone_id=zone_id,
                greenhouse_uid=greenhouse_uid,
                max_step_pct=int(max_step_pct),
                reason=str(decision.decision_reason or ""),
            )
        )
    return out


__all__ = ["VentCommand", "list_vent_commands"]
