"""Sequential nutrient pipeline: water baseline, cumulative T_*, step order.

Canon (2026-07-22):
  solution_fill: calcium only → T_ca (no pH)
  prepare_recirc: Ca → pH → Mg → pH → NPK → pH → Micro → final pH
  irrigation: pH only (needs_ec=false)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError

# Canonical pump channel → nutrient component
CHANNEL_TO_COMPONENT: dict[str, str] = {
    "pump_a": "npk",
    "pump_b": "calcium",
    "pump_c": "magnesium",
    "pump_d": "micro",
    "a": "npk",
    "b": "calcium",
    "c": "magnesium",
    "d": "micro",
}

COMPONENT_TO_CHANNEL: dict[str, str] = {
    "npk": "pump_a",
    "calcium": "pump_b",
    "magnesium": "pump_c",
    "micro": "pump_d",
}

# Ordered EC components for cumulative target math
EC_COMPONENT_ORDER: tuple[str, ...] = ("calcium", "magnesium", "npk", "micro")

# Recirc interleaved pipeline: (kind, component_or_None, target_key_or_None)
# kind: "ec" | "ph"
RECIRC_PIPELINE_STEPS: tuple[tuple[str, Optional[str], Optional[str]], ...] = (
    ("ec", "calcium", "T_ca"),
    ("ph", None, None),
    ("ec", "magnesium", "T_ca_mg"),
    ("ph", None, None),
    ("ec", "npk", "T_ca_mg_npk"),
    ("ph", None, None),
    ("ec", "micro", "T_full"),
    ("ph", None, None),  # final pH
)

PIPELINE_PHASE_FILL_CA = "fill_ca"
PIPELINE_PHASE_RECIRC_PREFIX = "recirc_"


@dataclass(frozen=True)
class ComponentTargets:
    """Cumulative EC targets derived from water baseline + recipe ratios."""

    water_ec: float
    water_ph: float
    target_ec: float
    nutrient_budget: float
    ratios: Mapping[str, float]
    T_ca: float
    T_ca_mg: float
    T_ca_mg_npk: float
    T_full: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "water_ec": self.water_ec,
            "water_ph": self.water_ph,
            "target_ec": self.target_ec,
            "nutrient_budget": self.nutrient_budget,
            "ratios": dict(self.ratios),
            "T_ca": self.T_ca,
            "T_ca_mg": self.T_ca_mg,
            "T_ca_mg_npk": self.T_ca_mg_npk,
            "T_full": self.T_full,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ComponentTargets":
        ratios_raw = raw.get("ratios") if isinstance(raw.get("ratios"), Mapping) else {}
        ratios = {str(k).strip().lower(): float(v) for k, v in ratios_raw.items()}
        return cls(
            water_ec=float(raw["water_ec"]),
            water_ph=float(raw.get("water_ph") or 0.0),
            target_ec=float(raw["target_ec"]),
            nutrient_budget=float(raw["nutrient_budget"]),
            ratios=ratios,
            T_ca=float(raw["T_ca"]),
            T_ca_mg=float(raw["T_ca_mg"]),
            T_ca_mg_npk=float(raw["T_ca_mg_npk"]),
            T_full=float(raw["T_full"]),
        )

    @classmethod
    def from_json(cls, raw: str | None) -> "ComponentTargets | None":
        if not raw or not str(raw).strip():
            return None
        data = json.loads(raw)
        if not isinstance(data, Mapping):
            return None
        return cls.from_mapping(data)

    def target_for_key(self, key: str) -> float:
        mapping = {
            "T_ca": self.T_ca,
            "T_ca_mg": self.T_ca_mg,
            "T_ca_mg_npk": self.T_ca_mg_npk,
            "T_full": self.T_full,
        }
        if key not in mapping:
            raise KeyError(key)
        return mapping[key]


def normalize_ec_ratios(ratios: Mapping[str, Any] | None) -> dict[str, float]:
    """Normalize positive ratios for calcium/magnesium/npk/micro to sum=1.0."""
    active: dict[str, float] = {}
    for name in EC_COMPONENT_ORDER:
        if not isinstance(ratios, Mapping):
            continue
        raw = ratios.get(name)
        if raw is None:
            # accept legacy aliases
            alias = {"calcium": "b", "magnesium": "c", "npk": "a", "micro": "d"}.get(name)
            raw = ratios.get(alias) if alias else None
        try:
            weight = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            weight = 0.0
        if weight > 0:
            active[name] = weight
    total = sum(active.values())
    if total <= 0:
        raise PlannerConfigurationError(
            "ec_component_ratios пусты или невалидны для sequential nutrient pipeline",
            code=ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
        )
    return {k: round(v / total, 6) for k, v in active.items()}


def compute_component_targets(
    *,
    water_ec: float,
    water_ph: float,
    target_ec: float,
    ratios: Mapping[str, Any] | None,
) -> ComponentTargets:
    """Compute nutrient_budget and cumulative T_* from water baseline."""
    if water_ec >= target_ec:
        raise PlannerConfigurationError(
            f"water_ec={water_ec} >= target_ec={target_ec}; nutrient_budget must be > 0",
            code=ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
        )
    norm = normalize_ec_ratios(ratios)
    budget = round(float(target_ec) - float(water_ec), 6)
    r_ca = float(norm.get("calcium") or 0.0)
    r_mg = float(norm.get("magnesium") or 0.0)
    r_npk = float(norm.get("npk") or 0.0)
    # micro may be zero; T_full always = water + budget
    t_ca = round(water_ec + budget * r_ca, 4)
    t_ca_mg = round(water_ec + budget * (r_ca + r_mg), 4)
    t_ca_mg_npk = round(water_ec + budget * (r_ca + r_mg + r_npk), 4)
    t_full = round(water_ec + budget, 4)
    return ComponentTargets(
        water_ec=float(water_ec),
        water_ph=float(water_ph),
        target_ec=float(target_ec),
        nutrient_budget=budget,
        ratios=norm,
        T_ca=t_ca,
        T_ca_mg=t_ca_mg,
        T_ca_mg_npk=t_ca_mg_npk,
        T_full=t_full,
    )


def resolve_component_from_role_or_channel(*, role: str, channel: str, calibration_component: str | None) -> str | None:
    """Resolve nutrient component from calibration.component OR role/channel map."""
    if calibration_component:
        normalized = str(calibration_component).strip().lower()
        if normalized.startswith("ec_"):
            normalized = normalized.removeprefix("ec_").removesuffix("_pump")
        if normalized in COMPONENT_TO_CHANNEL or normalized in CHANNEL_TO_COMPONENT.values():
            return CHANNEL_TO_COMPONENT.get(normalized, normalized)
        return normalized or None
    for raw in (role, channel):
        key = str(raw or "").strip().lower()
        if not key:
            continue
        if key in CHANNEL_TO_COMPONENT:
            return CHANNEL_TO_COMPONENT[key]
        if key.startswith("pump_") and key in CHANNEL_TO_COMPONENT:
            return CHANNEL_TO_COMPONENT[key]
    return None


def recirc_step_index(pipeline_phase: str | None) -> int:
    """Map pipeline_phase string to index in RECIRC_PIPELINE_STEPS; -1 if unknown."""
    phase = str(pipeline_phase or "").strip().lower()
    if not phase.startswith("recirc_"):
        return -1
    # recirc_ca / recirc_ph_0 / recirc_mg / ...
    aliases = {
        "recirc_ca": 0,
        "recirc_calcium": 0,
        "recirc_ph_after_ca": 1,
        "recirc_ph_0": 1,
        "recirc_mg": 2,
        "recirc_magnesium": 2,
        "recirc_ph_after_mg": 3,
        "recirc_ph_1": 3,
        "recirc_npk": 4,
        "recirc_ph_after_npk": 5,
        "recirc_ph_2": 5,
        "recirc_micro": 6,
        "recirc_ph_final": 7,
        "recirc_ph_3": 7,
    }
    if phase in aliases:
        return aliases[phase]
    # numeric suffix: recirc_step_N
    if phase.startswith("recirc_step_"):
        try:
            return int(phase.rsplit("_", 1)[-1])
        except ValueError:
            return -1
    return -1


def pipeline_phase_for_index(index: int) -> str:
    if index < 0 or index >= len(RECIRC_PIPELINE_STEPS):
        raise IndexError(index)
    kind, component, _target_key = RECIRC_PIPELINE_STEPS[index]
    if kind == "ec" and component:
        short = {"calcium": "ca", "magnesium": "mg", "npk": "npk", "micro": "micro"}[component]
        return f"recirc_{short}"
    # pH gates
    ph_names = {
        1: "recirc_ph_after_ca",
        3: "recirc_ph_after_mg",
        5: "recirc_ph_after_npk",
        7: "recirc_ph_final",
    }
    return ph_names.get(index, f"recirc_step_{index}")


def active_ec_target_for_corr(
    *,
    pipeline_phase: str | None,
    active_component: str | None,
    targets: ComponentTargets | None,
    fallback_target_ec: float,
) -> float:
    """Resolve T_step for the active pipeline step."""
    if targets is None:
        return float(fallback_target_ec)
    phase = str(pipeline_phase or "").strip().lower()
    if phase in {PIPELINE_PHASE_FILL_CA, "fill_calcium", "recirc_ca", "recirc_calcium"}:
        return targets.T_ca
    idx = recirc_step_index(phase)
    if idx >= 0:
        kind, _comp, target_key = RECIRC_PIPELINE_STEPS[idx]
        if kind == "ec" and target_key:
            return targets.target_for_key(target_key)
    component = str(active_component or "").strip().lower()
    if component == "calcium":
        return targets.T_ca
    if component == "magnesium":
        return targets.T_ca_mg
    if component == "npk":
        return targets.T_ca_mg_npk
    if component == "micro":
        return targets.T_full
    return float(fallback_target_ec)


def is_ph_gate_phase(pipeline_phase: str | None) -> bool:
    phase = str(pipeline_phase or "").strip().lower()
    if "ph" in phase and phase.startswith("recirc_"):
        return True
    idx = recirc_step_index(phase)
    if idx < 0:
        return False
    return RECIRC_PIPELINE_STEPS[idx][0] == "ph"


def is_ec_step_phase(pipeline_phase: str | None) -> bool:
    phase = str(pipeline_phase or "").strip().lower()
    if phase in {PIPELINE_PHASE_FILL_CA, "fill_calcium"}:
        return True
    idx = recirc_step_index(phase)
    if idx < 0:
        return False
    return RECIRC_PIPELINE_STEPS[idx][0] == "ec"


def advance_pipeline_phase(pipeline_phase: str | None) -> str | None:
    """Return next recirc pipeline phase, or None if finished."""
    idx = recirc_step_index(pipeline_phase)
    if idx < 0:
        # starting recirc from fill
        return pipeline_phase_for_index(0)
    next_idx = idx + 1
    if next_idx >= len(RECIRC_PIPELINE_STEPS):
        return None
    return pipeline_phase_for_index(next_idx)


def component_for_phase(pipeline_phase: str | None) -> str | None:
    phase = str(pipeline_phase or "").strip().lower()
    if phase in {PIPELINE_PHASE_FILL_CA, "fill_calcium"}:
        return "calcium"
    idx = recirc_step_index(phase)
    if idx < 0:
        return None
    kind, component, _ = RECIRC_PIPELINE_STEPS[idx]
    return component if kind == "ec" else None


def ec_overshoot_requires_dilute(
    *,
    current_ec: float,
    t_step: float,
    overshoot_pct: float,
) -> bool:
    if t_step <= 0:
        return False
    threshold = t_step * (1.0 + max(0.0, float(overshoot_pct)) / 100.0)
    return float(current_ec) > threshold


__all__ = [
    "CHANNEL_TO_COMPONENT",
    "COMPONENT_TO_CHANNEL",
    "ComponentTargets",
    "EC_COMPONENT_ORDER",
    "PIPELINE_PHASE_FILL_CA",
    "RECIRC_PIPELINE_STEPS",
    "active_ec_target_for_corr",
    "advance_pipeline_phase",
    "component_for_phase",
    "compute_component_targets",
    "ec_overshoot_requires_dilute",
    "is_ec_step_phase",
    "is_ph_gate_phase",
    "normalize_ec_ratios",
    "pipeline_phase_for_index",
    "recirc_step_index",
    "resolve_component_from_role_or_channel",
]
