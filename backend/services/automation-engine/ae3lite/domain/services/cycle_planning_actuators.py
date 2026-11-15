"""CycleStartPlanner actuators: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Sequence

from ae3lite.application.dto import ZoneActuatorRef
from ae3lite.domain.errors import PlannerConfigurationError


@dataclass(frozen=True)
class CyclePlanningActuatorsPorts:
    pass


class CyclePlanningActuators:
    def __init__(self, ports: CyclePlanningActuatorsPorts) -> None:
        self._ports = ports

    def resolve_correction_actuators(
        self,
        *,
        actuators: Sequence[ZoneActuatorRef],
        correction: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Разрешает ссылки на dosing actuator'ы для модуля коррекции.

        Возвращает dict с ключами `"ec"`, `"ec_actuators"`, `"ph_up"`, `"ph_down"`.
        Каждое значение — либо dict вида `{node_uid, channel, calibration}`, либо `None`
        (только если `dose_*_channel` пустой). Fail-closed:
        `dose_*_channel` обязан ссылаться на канонический физический канал
        (`pump_acid`/`pump_base`/`pump_a..d`) — legacy alias'ы больше не
        резолвятся (см. `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`).
        """

        def _resolve(channel_name: str, node_types: List[str]) -> Any:
            requested = str(channel_name or "").strip().lower()
            if not requested:
                return None
            try:
                actuator = self.resolve_actuator(
                    actuators=actuators,
                    requested_channel=requested,
                    node_types=node_types,
                )
            except PlannerConfigurationError as exc:
                # Ambiguous actuator resolution is always fatal — ошибка конфига.
                if "Неоднозначное разрешение actuator" in str(exc):
                    raise
                # Отсутствующий actuator на этапе планирования допустим:
                # correction-handler упадёт уже в момент дозирования (см. `_validate_required_correction_calibrations`).
                return None
            return {
                "node_uid": actuator.node_uid,
                "channel": actuator.channel,
                "calibration": dict(actuator.pump_calibration)
                if isinstance(actuator.pump_calibration, Mapping)
                else None,
            }

        ec_channel = str(correction.get("dose_ec_channel") or "").strip().lower()
        ph_up_channel = str(correction.get("dose_ph_up_channel") or "").strip().lower()
        ph_down_channel = str(correction.get("dose_ph_down_channel") or "").strip().lower()

        ec_actuators: dict[str, Any] = {}
        for actuator in actuators:
            node_type = str(actuator.node_type or "").strip().lower()
            if node_type != "ec":
                continue
            channel = str(actuator.channel or "").strip().lower()
            value = {
                "node_uid": actuator.node_uid,
                "channel": actuator.channel,
                "calibration": dict(actuator.pump_calibration)
                if isinstance(actuator.pump_calibration, Mapping)
                else None,
            }
            component = self.extract_ec_component(
                role=str(actuator.role or ""),
                pump_calibration=actuator.pump_calibration,
                channel=channel,
            )
            if component:
                ec_actuators.setdefault(component, value)
                # Also index by canonical pump channel so lookup calcium↔pump_b works both ways.
                from ae3lite.domain.services.nutrient_pipeline import COMPONENT_TO_CHANNEL

                canon_channel = COMPONENT_TO_CHANNEL.get(component)
                if canon_channel:
                    ec_actuators.setdefault(canon_channel, value)
            if channel:
                ec_actuators.setdefault(channel, value)

        return {
            "ec": _resolve(ec_channel, ["ec"]),
            "ec_actuators": ec_actuators,
            "ph_up": _resolve(ph_up_channel, ["ph"]),
            "ph_down": _resolve(ph_down_channel, ["ph"]),
        }

    def extract_ec_component(
        self,
        *,
        role: str,
        pump_calibration: Mapping[str, Any] | None,
        channel: str = "",
    ) -> str | None:
        from ae3lite.domain.services.nutrient_pipeline import resolve_component_from_role_or_channel

        calibration_component = None
        if isinstance(pump_calibration, Mapping):
            raw_component = str(pump_calibration.get("component") or "").strip().lower()
            if raw_component:
                calibration_component = raw_component
        return resolve_component_from_role_or_channel(
            role=role,
            channel=channel,
            calibration_component=calibration_component,
        )

    def resolve_actuator(
        self,
        *,
        actuators: Iterable[ZoneActuatorRef],
        requested_channel: str,
        node_types: Sequence[str],
    ) -> ZoneActuatorRef:
        normalized_types = {str(item).strip().lower() for item in node_types if str(item).strip()}
        candidates: List[tuple[tuple[int, int], ZoneActuatorRef]] = []
        for actuator in actuators:
            role = str(actuator.role or "").strip().lower()
            channel = str(actuator.channel or "").strip().lower()
            node_type = str(actuator.node_type or "").strip().lower()
            if normalized_types and node_type not in normalized_types:
                continue
            if requested_channel not in {role, channel}:
                continue
            candidates.append(
                (
                    (0 if role == requested_channel else 1, 0 if channel == requested_channel else 1),
                    actuator,
                )
            )
        if not candidates:
            raise PlannerConfigurationError(
                f"Не найден online actuator для requested_channel={requested_channel} node_types={sorted(normalized_types)}"
            )
        candidates.sort(key=lambda item: (item[0], item[1].node_uid, item[1].channel, item[1].node_channel_id))

        best_rank = candidates[0][0]
        equally_ranked = [item[1] for item in candidates if item[0] == best_rank]
        if len(equally_ranked) > 1:
            raise PlannerConfigurationError(
                f"Неоднозначное разрешение actuator для requested_channel={requested_channel}: "
                f"{[item.node_uid for item in equally_ranked]}"
            )
        return equally_ranked[0]
