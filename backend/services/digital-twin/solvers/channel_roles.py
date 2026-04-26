"""Классификатор каналов узлов в семантические роли DT.

В реальной системе каналы (`node_channels.channel`) именуются свободно:
`pump_acid`, `pump_in_a`, `valve_clean_fill`, `dose_npk_a`. Чтобы DT понимал,
что делать с командой `dose` или `set_relay`, нужно знать роль канала.

Поддерживается:
1. Карта переопределений из `params_by_group['actuator']['channel_roles']`
   (опциональный override per zone, заполняется калибратором или вручную).
2. Эвристика по имени канала (regex по нормализованному lower-case).

Роли:
- `valve_clean_fill`         — клапан притока чистой воды в clean tank
- `valve_clean_supply`       — клапан подачи чистой воды в solution tank
- `valve_solution_fill`      — клапан заполнения solution tank
- `valve_solution_supply`    — клапан подачи раствора (recirc/irrigation)
- `valve_irrigation`         — клапан полива
- `pump_main`                — основной насос (fill/recirc/irrigation)
- `pump_ph_up` / `pump_ph_down` — pH-дозаторы (база/кислота)
- `pump_ec_a` / `pump_ec_b` / `pump_ec_c` / `pump_ec_d` — нутриенты
- `unknown`                  — нераспознанный
"""
from typing import Dict, Optional


KNOWN_ROLES = (
    "valve_clean_fill",
    "valve_clean_supply",
    "valve_solution_fill",
    "valve_solution_supply",
    "valve_irrigation",
    "pump_main",
    "pump_ph_up",
    "pump_ph_down",
    "pump_ec_a",
    "pump_ec_b",
    "pump_ec_c",
    "pump_ec_d",
)


def _heuristic_role(channel: str) -> str:
    name = channel.strip().lower()

    if "valve" in name or name.startswith("vlv_"):
        if "irrig" in name:
            return "valve_irrigation"
        if "clean" in name and ("supply" in name or "feed" in name):
            return "valve_clean_supply"
        if "clean" in name and ("fill" in name or "in" in name):
            return "valve_clean_fill"
        if "solution" in name and ("supply" in name or "feed" in name or "recirc" in name):
            return "valve_solution_supply"
        if "solution" in name and "fill" in name:
            return "valve_solution_fill"
        return "unknown"

    if "pump" in name or name.startswith("dose_") or name.startswith("dosing_"):
        if "main" in name or "circulation" in name or "circ" in name:
            return "pump_main"
        if "ph_up" in name or name.endswith("_up") or "base" in name or "alkali" in name:
            return "pump_ph_up"
        if "ph_down" in name or name.endswith("_down") or "acid" in name:
            return "pump_ph_down"
        if "ec_a" in name or name.endswith("_a") or "npk_a" in name:
            return "pump_ec_a"
        if "ec_b" in name or name.endswith("_b") or "npk_b" in name:
            return "pump_ec_b"
        if "ec_c" in name or name.endswith("_c") or "npk_c" in name:
            return "pump_ec_c"
        if "ec_d" in name or name.endswith("_d") or "npk_d" in name:
            return "pump_ec_d"
        return "unknown"

    return "unknown"


def resolve_channel_role(
    channel: str,
    overrides: Optional[Dict[str, str]] = None,
) -> str:
    """Вернуть семантическую роль канала.

    `overrides` — точная карта `{channel: role}` из `zone_dt_params.actuator.channel_roles`.
    Имеет приоритет над эвристикой.
    """
    if not channel:
        return "unknown"

    overrides = overrides or {}
    if channel in overrides:
        role = str(overrides[channel] or "").strip()
        if role in KNOWN_ROLES:
            return role
        return "unknown"

    return _heuristic_role(channel)
