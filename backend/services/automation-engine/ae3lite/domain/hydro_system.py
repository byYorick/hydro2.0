"""Канон hydro_system (ADR-0001). Снимок — schemas/hydro_system.enum.json.

Пустой тип не отказ: зона без явного типа остаётся каплей.
Явный тип без графа, неизвестная строка и корзина substrate/aeroponics
запрещают капельный граф.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError

_logger = logging.getLogger(__name__)

_HYDRAULIC_TASK_TYPES = frozenset({"irrigation_start", "solution_topup", "solution_change"})


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    path = _catalog_path()
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Каталог hydro_system не объект: {path}")
    return payload


def implemented_types() -> tuple[str, ...]:
    return tuple(_string_list("implemented"))


def canonical_types() -> tuple[str, ...]:
    return tuple(_string_list("canonical"))


def needs_review_types() -> tuple[str, ...]:
    return tuple(_string_list("needs_review"))


def canonicalize(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    token = raw.strip().lower().replace(" ", "_")
    if not token:
        return None
    aliases = load_catalog().get("aliases")
    if isinstance(aliases, dict):
        mapped = aliases.get(token)
        if isinstance(mapped, str) and mapped.strip():
            return mapped.strip().lower()
    return token


def refusal_code(raw: Any, environment: str | None = None) -> str | None:
    canonical = canonicalize(raw)
    if canonical is None:
        return None
    if canonical in needs_review_types():
        return ErrorCodes.HYDRO_SYSTEM_NEEDS_REVIEW
    if canonical not in canonical_types():
        return ErrorCodes.HYDRO_SYSTEM_UNKNOWN
    if _environment_forbids(canonical, environment):
        return ErrorCodes.HYDRO_SYSTEM_ENVIRONMENT_FORBIDDEN
    if canonical not in implemented_types():
        return ErrorCodes.HYDRO_SYSTEM_NOT_IMPLEMENTED
    return None


def rejection_message(code: str, requested: str, environment: str | None = None) -> str:
    messages = load_catalog().get("messages")
    template = ""
    if isinstance(messages, dict) and isinstance(messages.get(code), str):
        template = messages[code]
    if not template:
        template = "Тип гидропонной системы «{requested}» нельзя запустить."
    return (
        template.replace("{requested}", requested)
        .replace("{supported}", ", ".join(implemented_types()))
        .replace("{canonical}", ", ".join(canonical_types()))
        .replace("{environment}", environment or "")
    )


def explicit_system_types(snapshot: Any) -> list[str]:
    found: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            found.append(value.strip())

    for item in getattr(snapshot, "configured_hydroponic_system_types", ()) or ():
        add(item)

    for payload in (
        getattr(snapshot, "targets", None),
        getattr(snapshot, "phase_targets", None),
    ):
        if not isinstance(payload, Mapping):
            continue
        irrigation = payload.get("irrigation")
        if isinstance(irrigation, Mapping):
            add(irrigation.get("system_type"))
        extensions = payload.get("extensions")
        if isinstance(extensions, Mapping):
            subsystems = extensions.get("subsystems")
            if isinstance(subsystems, Mapping):
                subsystem = subsystems.get("irrigation")
                if isinstance(subsystem, Mapping):
                    for bucket in ("targets", "execution"):
                        section = subsystem.get(bucket)
                        if isinstance(section, Mapping):
                            add(section.get("system_type"))
    return found


def refuse_drip_execution_for_unsupported_system(*, snapshot: Any, task_type: str, topology: str) -> None:
    """Fail-closed перед капельным графом. generic_cycle_start и свет не трогает."""
    normalized_task = str(task_type or "").strip().lower()
    normalized_topology = str(topology or "").strip().lower()
    if normalized_task == "lighting_tick" or normalized_topology in {"generic_cycle_start", "lighting_tick"}:
        return
    if normalized_task not in _HYDRAULIC_TASK_TYPES and normalized_task != "cycle_start":
        return
    if normalized_task == "cycle_start" and normalized_topology not in {"", *_hydraulic_topology_ids()}:
        # Неизвестный pack упадёт в TopologyRegistry, это не подмена каплей.
        if normalized_topology and normalized_topology not in _hydraulic_topology_ids():
            return

    for raw in explicit_system_types(snapshot):
        code = refusal_code(raw)
        if code is None:
            continue
        requested = canonicalize(raw) or raw.strip()
        message = rejection_message(code, requested)
        _logger.error(
            "AE3 отказывает в drip-исполнении: zone_id=%s task_type=%s topology=%s "
            "requested_type=%s supported_types=%s code=%s",
            getattr(snapshot, "zone_id", None),
            normalized_task,
            normalized_topology,
            requested,
            ",".join(implemented_types()),
            code,
        )
        raise PlannerConfigurationError(message, code=code)


def _hydraulic_topology_ids() -> frozenset[str]:
    return frozenset({"two_tank", "two_tank_drip_substrate_trays", "single_tank"})


def _environment_forbids(canonical: str, environment: str | None) -> bool:
    if not isinstance(environment, str) or environment.strip().lower() != "outdoor":
        return False
    environment_rules = load_catalog().get("environment")
    only = ["drip"]
    if isinstance(environment_rules, dict) and isinstance(environment_rules.get("outdoor_only"), list):
        only = [str(item).strip().lower() for item in environment_rules["outdoor_only"] if str(item).strip()]
    return canonical not in only


def _string_list(key: str) -> list[str]:
    values = load_catalog().get(key)
    if not isinstance(values, list):
        return []
    return [str(item).strip().lower() for item in values if str(item).strip()]


def _catalog_path() -> Path:
    candidates = [
        Path("/schemas/hydro_system.enum.json"),
        Path(__file__).resolve().parents[5] / "schemas" / "hydro_system.enum.json",
        Path(__file__).resolve().parents[4] / "schemas" / "hydro_system.enum.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Не найден schemas/hydro_system.enum.json")
