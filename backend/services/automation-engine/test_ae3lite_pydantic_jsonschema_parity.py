"""Parity test: AE3 Pydantic models ↔ canonical JSON Schemas (Phase 2 / B3 audit fix).

Цель — поймать drift между:
  - `schemas/zone_correction.v1.json` (canonical source of truth)
  - `ae3lite/config/schema/zone_correction.py` (Pydantic mirror)

Стратегия: для каждого ключевого поля сверяем (type, bounds, required) из обоих
источников. Не сравниваем JSON Schemas «байт-в-байт» — Pydantic-сгенерированная
JSON Schema имеет вспомогательные `$defs`, `discriminator` и т.п., которые
просто шумят. Сравниваем семантику.

Когда добавляется новое поле — добавлять и в JSON Schema, и в Pydantic, и
в `EXPECTED_FIELDS` ниже. Failure теста сразу сигнализирует о drift.

Audit refs: `doc_ai/04_BACKEND_CORE/AE3_CONFIG_REFACTORING_AUDIT_PHASE_0_2.md` §M-3.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ae3lite.config.schema.zone_correction import ZoneCorrection


# ─── Constants ─────────────────────────────────────────────────────────────

def _resolve_schemas_dir() -> Path | None:
    """Find canonical schemas dir.

    Priority:
      1. AUTOMATION_SCHEMAS_ROOT env override
      2. /schemas (docker bind mount — see docker-compose.dev.yml)
      3. ../../../../schemas relative to this test file (repo-root layout)
    """
    env = os.environ.get("AUTOMATION_SCHEMAS_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    if Path("/schemas").is_dir():
        return Path("/schemas")
    here = Path(__file__).resolve()
    for parents_idx in range(2, 6):
        try:
            candidate = here.parents[parents_idx] / "schemas"
        except IndexError:
            continue
        if candidate.is_dir():
            return candidate
    return None


SCHEMAS_DIR = _resolve_schemas_dir()
SCHEMA_PATH = SCHEMAS_DIR / "zone_correction.v1.json" if SCHEMAS_DIR else None

pytestmark = pytest.mark.skipif(
    SCHEMA_PATH is None or not SCHEMA_PATH.is_file(),
    reason="canonical schemas/ dir not found; mount ../schemas into container or set AUTOMATION_SCHEMAS_ROOT",
)


# ─── Helpers ───────────────────────────────────────────────────────────────

def _resolve_ref(schema: dict, ref: str) -> dict:
    """Resolve `#/$defs/Name` ref against root schema."""
    assert ref.startswith("#/"), f"non-local ref: {ref}"
    node = schema
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _walk_to(schema: dict, dotted_path: str) -> dict:
    """Walk JSON Schema following `properties.X.properties.Y` for `X.Y` path.

    Resolves `$ref` as we go. Returns the leaf schema dict.
    """
    node = schema
    for segment in dotted_path.split("."):
        if "$ref" in node:
            node = _resolve_ref(schema, node["$ref"])
        props = node.get("properties", {})
        if segment not in props:
            raise KeyError(f"path {dotted_path!r} missing at {segment!r}")
        node = props[segment]
    if "$ref" in node:
        node = _resolve_ref(schema, node["$ref"])
    return node


def _pydantic_field(path: str) -> dict:
    """Generate JSON Schema from Pydantic, then walk same dotted path."""
    schema = ZoneCorrection.model_json_schema()
    return _walk_to(schema, path)


def _json_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _bounds(field_schema: dict) -> dict:
    """Extract numeric bound keywords (works for both inclusive and exclusive)."""
    keys = (
        "minimum", "maximum",
        "exclusiveMinimum", "exclusiveMaximum",
        "minLength", "maxLength",
    )
    return {k: field_schema[k] for k in keys if k in field_schema}


# Field paths to verify. Keep in sync with schema/zone_correction.v1.json.
# Format: dotted path → expected JSON keyword set on the leaf node.
EXPECTED_FIELDS: list[tuple[str, str]] = [
    # (path, expected JSON Schema "type")
    ("controllers.ph.kp", "number"),
    ("controllers.ph.ki", "number"),
    ("controllers.ph.kd", "number"),
    ("controllers.ph.deadband", "number"),
    ("controllers.ph.max_dose_ml", "number"),
    ("controllers.ph.min_interval_sec", "integer"),
    ("controllers.ph.max_integral", "number"),
    ("controllers.ph.derivative_filter_alpha", "number"),
    ("controllers.ec.kp", "number"),
    ("controllers.ec.deadband", "number"),
    ("controllers.ec.max_dose_ml", "number"),
    ("runtime.clean_fill_timeout_sec", "integer"),
    ("runtime.solution_fill_timeout_sec", "integer"),
    ("runtime.clean_fill_retry_cycles", "integer"),
    ("runtime.level_switch_on_threshold", "number"),
    ("timing.sensor_mode_stabilization_time_sec", "integer"),
    ("timing.telemetry_max_age_sec", "integer"),
    ("timing.irr_state_max_age_sec", "integer"),
    ("dosing.solution_volume_l", "number"),
    ("dosing.max_ec_dose_ml", "number"),
    ("dosing.max_ph_dose_ml", "number"),
    ("retry.max_ec_correction_attempts", "integer"),
    ("retry.max_ph_correction_attempts", "integer"),
    ("retry.prepare_recirculation_timeout_sec", "integer"),
    ("retry.prepare_recirculation_correction_slack_sec", "integer"),
    ("retry.prepare_recirculation_max_attempts", "integer"),
    ("retry.telemetry_stale_retry_sec", "integer"),
    ("retry.decision_window_retry_sec", "integer"),
    ("retry.low_water_retry_sec", "integer"),
    ("tolerance.prepare_tolerance.ph_pct", "number"),
    ("tolerance.prepare_tolerance.ec_pct", "number"),
]


# ─── Tests ─────────────────────────────────────────────────────────────────

def test_canonical_schema_file_exists() -> None:
    assert SCHEMA_PATH.is_file(), f"canonical schema missing: {SCHEMA_PATH}"


def test_pydantic_top_level_required_matches_json_schema() -> None:
    canonical = _json_schema()
    pyd = ZoneCorrection.model_json_schema()
    expected = set(canonical.get("required", []))
    actual = set(pyd.get("required", []))
    assert actual == expected, (
        f"Top-level required drift:\n"
        f"  canonical: {sorted(expected)}\n"
        f"  pydantic:  {sorted(actual)}"
    )


def test_pydantic_top_level_additional_properties_forbidden() -> None:
    pyd = ZoneCorrection.model_json_schema()
    # Pydantic v2 with extra="forbid" sets additionalProperties=false
    assert pyd.get("additionalProperties") is False, (
        "ZoneCorrection model_config must have extra='forbid' to match "
        "canonical schema's additionalProperties: false"
    )


@pytest.mark.parametrize(("path", "expected_type"), EXPECTED_FIELDS)
def test_field_type_matches(path: str, expected_type: str) -> None:
    canonical = _walk_to(_json_schema(), path)
    pyd = _pydantic_field(path)
    canonical_type = canonical.get("type")
    pyd_type = pyd.get("type")
    assert canonical_type == expected_type, (
        f"canonical type drift at {path}: expected {expected_type}, got {canonical_type}"
    )
    assert pyd_type == expected_type, (
        f"pydantic type drift at {path}: expected {expected_type}, got {pyd_type}"
    )


@pytest.mark.parametrize(("path", "expected_type"), EXPECTED_FIELDS)
def test_field_bounds_match(path: str, expected_type: str) -> None:
    """Bound keywords must match exactly (audit C-1 found Percent drift here)."""
    canonical = _bounds(_walk_to(_json_schema(), path))
    pyd = _bounds(_pydantic_field(path))
    assert canonical == pyd, (
        f"Bound drift at {path}:\n"
        f"  canonical: {canonical}\n"
        f"  pydantic:  {pyd}"
    )


def test_dosing_ec_dosing_mode_enum_matches() -> None:
    canonical = _walk_to(_json_schema(), "dosing.ec_dosing_mode")
    pyd = _pydantic_field("dosing.ec_dosing_mode")
    assert set(canonical.get("enum", [])) == set(pyd.get("enum", [])), (
        f"ec_dosing_mode enum drift:\n"
        f"  canonical: {sorted(canonical.get('enum', []))}\n"
        f"  pydantic:  {sorted(pyd.get('enum', []))}"
    )


def test_ph_controller_mode_const_matches() -> None:
    canonical = _walk_to(_json_schema(), "controllers.ph.mode")
    pyd = _pydantic_field("controllers.ph.mode")
    # Canonical uses `const`, Pydantic Literal generates `enum: [value]`.
    canonical_value = canonical.get("const") or (canonical.get("enum") or [None])[0]
    pyd_value = pyd.get("const") or (pyd.get("enum") or [None])[0]
    assert canonical_value == pyd_value == "cross_coupled_pi_d"


def test_ec_controller_mode_const_matches() -> None:
    canonical = _walk_to(_json_schema(), "controllers.ec.mode")
    pyd = _pydantic_field("controllers.ec.mode")
    canonical_value = canonical.get("const") or (canonical.get("enum") or [None])[0]
    pyd_value = pyd.get("const") or (pyd.get("enum") or [None])[0]
    assert canonical_value == pyd_value == "supervisory_allocator"
