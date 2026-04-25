"""Состояния зоны для Digital Twin.

Каждый solver принимает свой подсостояние и возвращает обновлённое.
ZoneState агрегирует подсостояния для удобного pass-through между шагами.
"""
from dataclasses import dataclass, field


@dataclass
class TankState:
    """Состояние резервуаров (clean/solution баки)."""

    clean_volume_l: float = 100.0
    solution_volume_l: float = 100.0
    clean_capacity_l: float = 200.0
    solution_capacity_l: float = 200.0
    level_clean_min: bool = True
    level_clean_max: bool = False
    level_solution_min: bool = True
    level_solution_max: bool = False
    water_temp_c: float = 20.0


@dataclass
class ChemState:
    """Состояние химии раствора (pH, EC)."""

    ph: float = 6.0
    ec: float = 1.2  # mS/cm


@dataclass
class ClimateState:
    """Состояние климата (воздух)."""

    temp_air_c: float = 22.0
    humidity_air_pct: float = 60.0
    co2_ppm: float = 400.0


@dataclass
class SubstrateState:
    """Состояние субстрата."""

    water_content_pct: float = 60.0


@dataclass
class ZoneState:
    """Полное состояние зоны для DT."""

    tank: TankState = field(default_factory=TankState)
    chem: ChemState = field(default_factory=ChemState)
    climate: ClimateState = field(default_factory=ClimateState)
    substrate: SubstrateState = field(default_factory=SubstrateState)
