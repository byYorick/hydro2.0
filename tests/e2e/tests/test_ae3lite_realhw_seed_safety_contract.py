#!/usr/bin/env python3
"""Линтер сидов/fill-path для live realhw two-tank сценариев AE3.

Инварианты:
1. two-tank realhw со start-cycle и fill/recirc: create_phase задаёт
   nutrient_mode=ratio_ec_pid, 4 ratio pct и nutrient_solution_volume_l.
2. Запрет: в одном set_fault_mode одновременно ec_value >= 2.0 и
   level_solution_max_override true, пока сценарий не в post-complete live-band.
   Исключение: force_near_target_band_after_sequential_loop (E106/E112) —
   live-band после Ca→pH, hang на Mg; T_full сидится без ожидания completed.
3. Fill path до recirc: seed ec≈0.45 и solution_max false, либо
   wait WATER_BASELINE / wait_fill_ec pump_b.
4. recirc.ec_overshoot_dilute_pct=100 запрещён вне E120 (dilute — цель теста).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from runner.scenario_loader import load_scenario_file

SCENARIOS_DIR = E2E_ROOT / "scenarios" / "ae3lite"

FILL_HELPER_SCENARIOS = (
    "E101_ae3_two_tank_realhw_setup_ready.yaml",
    "E104_ae3_two_tank_realhw_hot_reload_correction_config.yaml",
    "E106_ae3_two_tank_realhw_piggyback_ec_ph_cycle.yaml",
    "E113_ae3_prepare_recirc_solution_low_to_setup_realhw.yaml",
)

RATIO_COLUMNS = (
    "nutrient_npk_ratio_pct",
    "nutrient_calcium_ratio_pct",
    "nutrient_magnesium_ratio_pct",
    "nutrient_micro_ratio_pct",
)

# Product T_full band starts around 2.0 mS/cm. Same-step max ON hides water
# baseline / trips recirc_dilute_blocked_solution_max during calcium.
T_FULL_EC_MIN = 2.0

# E106/E112: live-band after sequential Ca→pH. Pipeline may still hang on Mg;
# DoD is telemetry window, not ae_tasks.status=completed.
LIVE_BAND_T_FULL_EXCEPTION_STEPS = {
    "force_near_target_band_after_sequential_loop",
}


def _is_live_realhw(path: Path, doc: dict) -> bool:
    if path.name.startswith("_"):
        return False
    if doc.get("status") in {"stub", "helper"}:
        return False
    if doc.get("kind") == "step_sequences":
        return False
    name = str(doc.get("name") or path.stem)
    tags = doc.get("tags") or []
    tagged = "realhw" in tags if isinstance(tags, list) else False
    return "realhw" in path.name.lower() or "realhw" in name.lower() or tagged


def _iter_live_realhw() -> list[tuple[Path, dict]]:
    found: list[tuple[Path, dict]] = []
    for path in sorted(SCENARIOS_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict) or not _is_live_realhw(path, raw):
            continue
        found.append((path, load_scenario_file(path)))
    return found


def _iter_steps(doc: dict) -> list[dict]:
    steps: list[dict] = []
    for section in ("actions", "cleanup", "assertions"):
        for item in doc.get(section) or []:
            if isinstance(item, dict):
                steps.append(item)
    return steps


def _step_names(doc: dict) -> list[str]:
    return [str(item.get("step") or "") for item in _iter_steps(doc)]


def _has_start_cycle(path: Path, doc: dict) -> bool:
    names = set(_step_names(doc))
    if "start_cycle_http" in names or any(name.startswith("start_cycle") for name in names):
        return True
    text = path.read_text(encoding="utf-8")
    return "/start-cycle" in text


def _has_fill_or_recirc_flow(doc: dict) -> bool:
    names = set(_step_names(doc))
    return bool(
        names
        & {
            "wait_prepare_recirculation_stage",
            "wait_prepare_recirculation_stage_second",
            "seed_solution_fill_sensor_baseline",
            "seed_solution_fill_sensor_baseline_second",
            "wait_fill_ec_correction_command",
            "wait_water_baseline_captured_event",
        }
    )


def _create_phase_steps(doc: dict) -> list[dict]:
    found: list[dict] = []
    for item in _iter_steps(doc):
        name = str(item.get("step") or "")
        if name == "create_phase" or name.startswith("create_phase"):
            found.append(item)
    return found


def _command_params(step: dict) -> dict:
    command = step.get("command") or {}
    if not isinstance(command, dict):
        return {}
    params = command.get("params") or {}
    return params if isinstance(params, dict) else {}


def _is_set_fault_mode(step: dict) -> bool:
    command = step.get("command") or {}
    if not isinstance(command, dict):
        return False
    return command.get("cmd") == "set_fault_mode"


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_true(value: object) -> bool:
    return value is True or value == 1 or str(value).lower() == "true"


def _is_false(value: object) -> bool:
    return value is False or value == 0 or str(value).lower() == "false"


class TestAe3LiteRealhwSeedSafetyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenarios = _iter_live_realhw()
        if not cls.scenarios:
            raise AssertionError(f"no live realhw YAML found in {SCENARIOS_DIR}")

    def test_start_cycle_fill_recirc_create_phase_uses_ratio_ec_pid(self) -> None:
        checked = 0
        for path, doc in self.scenarios:
            if not _has_start_cycle(path, doc) or not _has_fill_or_recirc_flow(doc):
                continue
            phases = _create_phase_steps(doc)
            self.assertTrue(
                phases,
                msg=f"{path.name}: start-cycle fill/recirc is missing create_phase",
            )
            for step in phases:
                query = str(step.get("query") or "")
                self.assertIn(
                    "nutrient_mode",
                    query,
                    msg=f"{path.name} step {step.get('step')}: create_phase must set nutrient_mode",
                )
                self.assertIn(
                    "ratio_ec_pid",
                    query,
                    msg=f"{path.name} step {step.get('step')}: create_phase must use nutrient_mode=ratio_ec_pid",
                )
                self.assertIn(
                    "nutrient_solution_volume_l",
                    query,
                    msg=f"{path.name} step {step.get('step')}: create_phase missing nutrient_solution_volume_l",
                )
                for column in RATIO_COLUMNS:
                    self.assertIn(
                        column,
                        query,
                        msg=f"{path.name} step {step.get('step')}: create_phase missing {column}",
                    )
                checked += 1
        self.assertGreater(checked, 0)

    def test_forbids_t_full_seed_with_solution_max_on_same_step(self) -> None:
        """Ban T_full + max ON in one set_fault_mode outside live-band exception.

        Exception (documented): E106/E112 ``force_near_target_band_after_sequential_loop``
        is post-Ca live-band (hang on Mg). Do not treat that as fill/calcium seed.
        E120 dilute is a separate positive test and must keep solution_max false.
        """
        violations: list[str] = []
        for path, doc in self.scenarios:
            for step in _iter_steps(doc):
                name = str(step.get("step") or "")
                if name in LIVE_BAND_T_FULL_EXCEPTION_STEPS:
                    continue
                if not _is_set_fault_mode(step):
                    continue
                params = _command_params(step)
                ec_value = _as_float(params.get("ec_value"))
                if ec_value is None or ec_value < T_FULL_EC_MIN:
                    continue
                if _is_true(params.get("level_solution_max_override")):
                    violations.append(
                        f"{path.name} step {name}: "
                        f"ec_value={ec_value} with level_solution_max_override true"
                    )
        self.assertEqual(violations, [])

    def test_fill_path_before_recirc_has_water_baseline_or_ca_dose(self) -> None:
        checked = 0
        for path, doc in self.scenarios:
            actions = [item for item in (doc.get("actions") or []) if isinstance(item, dict)]
            recirc_indexes = [
                idx
                for idx, item in enumerate(actions)
                if item.get("step") == "wait_prepare_recirculation_stage"
            ]
            if not recirc_indexes:
                continue
            prefix = actions[: recirc_indexes[0]]
            has_water_seed = False
            has_water_baseline_wait = False
            has_fill_ca_dose = False
            for step in prefix:
                name = str(step.get("step") or "")
                if name == "wait_water_baseline_captured_event":
                    has_water_baseline_wait = True
                query = str(step.get("query") or "")
                if name.startswith("wait_fill_ec") and "pump_b" in query:
                    has_fill_ca_dose = True
                params = _command_params(step)
                ec_value = _as_float(params.get("ec_value"))
                if (
                    name.startswith("seed_solution_fill")
                    and ec_value is not None
                    and abs(ec_value - 0.45) <= 0.06
                    and _is_false(params.get("level_solution_max_override"))
                ):
                    has_water_seed = True
            self.assertTrue(
                has_water_seed or has_water_baseline_wait or has_fill_ca_dose,
                msg=(
                    f"{path.name}: fill path before recirc must seed ec≈0.45 with "
                    "solution_max false, or wait WATER_BASELINE / wait_fill_ec pump_b"
                ),
            )
            checked += 1
        self.assertGreater(checked, 0)

    def test_canonical_fill_scenarios_include_helper_sequence(self) -> None:
        helper = SCENARIOS_DIR / "_two_tank_fill_helper.yaml"
        self.assertTrue(helper.is_file(), msg="missing _two_tank_fill_helper.yaml")
        helper_doc = yaml.safe_load(helper.read_text(encoding="utf-8")) or {}
        sequences = helper_doc.get("sequences") or {}
        self.assertIn("two_tank_fill_ca", sequences)

        for filename in FILL_HELPER_SCENARIOS:
            path = SCENARIOS_DIR / filename
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "include_sequence: two_tank_fill_ca",
                text,
                msg=f"{filename} must include two_tank_fill_ca helper sequence",
            )
            self.assertNotIn(
                "  - step: hold_solution_tank_filling_for_ca_dose\n",
                text,
                msg=f"{filename} still inlines hold_solution_tank_filling_for_ca_dose",
            )
            expanded = load_scenario_file(path)
            names = _step_names(expanded)
            self.assertIn("hold_solution_tank_filling_for_ca_dose", names)
            self.assertIn("seed_solution_fill_sensor_baseline", names)
            self.assertIn("wait_water_baseline_captured_event", names)
            self.assertIn("wait_fill_ec_correction_command", names)
            self.assertIn("complete_solution_fill_after_ec_correction", names)
            recirc_at = names.index("wait_prepare_recirculation_stage")
            self.assertLess(names.index("complete_solution_fill_after_ec_correction"), recirc_at)

    def test_non_e120_realhw_does_not_use_dilute_pct_100(self) -> None:
        violations: list[str] = []
        for path, doc in self.scenarios:
            if "E120" in path.name:
                continue
            for step in _iter_steps(doc):
                payload = step.get("payload")
                blobs: list[object] = [payload, step]
                for blob in blobs:
                    text = yaml.dump(blob, default_flow_style=False) if blob is not None else ""
                    if "ec_overshoot_dilute_pct: 100" in text or "ec_overshoot_dilute_pct: 100.0" in text:
                        violations.append(f"{path.name} step {step.get('step')}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
