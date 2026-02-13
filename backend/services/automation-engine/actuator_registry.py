"""
Actuator Registry — нормализация исполнительных устройств по ролям.
Позволяет отвязаться от node.type и каналов, выбирая actuator по заданной роли.
"""
from typing import Dict, Any, Optional, List


class ActuatorRegistry:
    """Строгий резолвер исполнительных устройств только по role-binding."""

    # Основные роли и алиасы, которые могут приходить из channel_bindings.role
    ROLE_ALIASES: Dict[str, List[str]] = {
        "irrigation_pump": ["irrigation_pump", "main_pump", "pump_irrigation", "pump", "irrig"],
        "recirculation_pump": ["recirculation_pump", "recirculation", "recirc"],
        "ph_acid_pump": ["ph_acid_pump"],
        "ph_base_pump": ["ph_base_pump"],
        "ec_npk_pump": ["ec_npk_pump"],
        "ec_calcium_pump": ["ec_calcium_pump"],
        "ec_magnesium_pump": ["ec_magnesium_pump"],
        "ec_micro_pump": ["ec_micro_pump"],
        "fan": ["vent", "fan", "ventilation"],
        "heater": ["heater", "heating"],
        "white_light": ["white_light", "light_white"],
        "uv_light": ["uv_light", "light_uv"],
        "flow_sensor": ["flow_sensor", "flow"],
        "soil_moisture_sensor": ["soil_moisture_sensor", "soil_moisture"],
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
            nodes: не используется (оставлен для совместимости сигнатуры)
            hardware_profile: зарезервировано для будущей привязки
        """
        resolved: Dict[str, Dict[str, Any]] = {}

        for role, aliases in self.ROLE_ALIASES.items():
            binding = self._pick_from_bindings(aliases, bindings)
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
                    "node_channel_id": info.get("node_channel_id"),
                    "channel": info.get("channel") or "default",
                    "asset_type": info.get("asset_type"),
                    "direction": info.get("direction"),
                    "role": alias,
                    "ml_per_sec": info.get("ml_per_sec"),
                    "k_ms_per_ml_l": info.get("k_ms_per_ml_l"),
                    "pump_calibration": info.get("pump_calibration"),
                }
        return None
