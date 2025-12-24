"""
Actuator Registry — нормализация исполнительных устройств по ролям.
Позволяет отвязаться от node.type и каналов, выбирая actuator по заданной роли.
"""
from typing import Dict, Any, Optional, List


class ActuatorRegistry:
    """Резолвер исполнительных устройств по ролям с fallback по каналам."""

    # Основные роли и алиасы, которые могут приходить из zone_channel_bindings.role
    ROLE_ALIASES: Dict[str, List[str]] = {
        "irrigation_pump": ["irrigation_pump", "main_pump", "pump_irrigation", "pump", "irrig"],
        "recirculation_pump": ["recirculation_pump", "recirculation", "recirc"],
        "ph_acid_pump": ["ph_acid_pump", "pump_acid", "acid_pump", "ph_acid", "acid"],
        "ph_base_pump": ["ph_base_pump", "pump_base", "base_pump", "ph_base", "base"],
        "ec_nutrient_pump": ["ec_nutrient_pump", "pump_nutrient", "nutrient_pump", "ec_pump", "ec"],
        "fan": ["vent", "fan", "ventilation"],
        "heater": ["heater", "heating"],
        "white_light": ["white_light", "light_white"],
        "uv_light": ["uv_light", "light_uv"],
        "flow_sensor": ["flow_sensor", "flow"],
        "soil_moisture_sensor": ["soil_moisture_sensor", "soil_moisture"],
    }

    # Fallback по именам каналов, если bindings по роли нет
    CHANNEL_HINTS: Dict[str, List[str]] = {
        "irrigation_pump": ["pump_irrigation", "irrigation", "main"],
        "recirculation_pump": ["recirculation", "recirc"],
        "ph_acid_pump": ["pump_acid", "acid"],
        "ph_base_pump": ["pump_base", "base"],
        "ec_nutrient_pump": ["pump_nutrient", "nutrient"],
        "fan": ["fan", "vent"],
        "heater": ["heater"],
        "white_light": ["white_light"],
        "uv_light": ["uv_light"],
    }

    def resolve(
        self,
        zone_id: int,
        bindings: Dict[str, Dict[str, Any]],
        nodes: Optional[Dict[str, Dict[str, Any]]] = None,
        hardware_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Построить карту ролей -> actuator binding.

        Args:
            zone_id: ID зоны (для логирования — пока не используется)
            bindings: полученные из InfrastructureRepository bindings по роли
            nodes: опционально узлы зоны (type/channel) для эвристик
            hardware_profile: зарезервировано для будущей привязки
        """
        resolved: Dict[str, Dict[str, Any]] = {}

        for role, aliases in self.ROLE_ALIASES.items():
            binding = self._pick_from_bindings(aliases, bindings)
            if not binding and nodes:
                binding = self._pick_from_nodes(role, nodes)

            if binding:
                resolved[role] = binding

        return resolved

    def _pick_from_bindings(
        self,
        aliases: List[str],
        bindings: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Ищем binding по алиасам роли."""
        for alias in aliases:
            if alias in bindings:
                info = bindings[alias]
                return {
                    "node_id": info.get("node_id"),
                    "node_uid": info.get("node_uid"),
                    "channel": info.get("channel") or "default",
                    "asset_type": info.get("asset_type"),
                    "direction": info.get("direction"),
                    "role": alias,
                }
        return None

    def _pick_from_nodes(
        self,
        role: str,
        nodes: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Fallback по именам каналов/типов узла, если role binding не найден."""
        hints = self.CHANNEL_HINTS.get(role, [])
        for node in nodes.values():
            channel = (node.get("channel") or "default").lower()
            node_type = (node.get("type") or "").lower()
            if channel in hints or node_type in hints:
                return {
                    "node_id": node.get("node_id"),
                    "node_uid": node.get("node_uid"),
                    "channel": node.get("channel") or "default",
                    "asset_type": node.get("type"),
                    "direction": "actuator",
                    "role": role,
                }
        return None
