#!/usr/bin/env python3
"""Contract checks for live-short E119 prepare pipeline sequence realhw."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E119_ae3_prepare_pipeline_sequence_realhw.yaml"
)
STUB_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E119_ae3_prepare_pipeline_sequence_test_node.yaml"
)


class TestAe3LitePipelineSequenceRealhwContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCENARIO_PATH.read_text(encoding="utf-8")
        with SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def test_is_live_realhw_not_stub(self) -> None:
        self.assertEqual(self.scenario.get("name"), "E119_ae3_prepare_pipeline_sequence_realhw")
        self.assertNotEqual(self.scenario.get("status"), "stub")
        self.assertNotIn("skip_live: true", self.text)
        self.assertIn("realhw", self.scenario.get("tags") or [])
        self.assertTrue(STUB_PATH.exists(), msg="stub companion must remain")

    def test_ratio_ec_pid_nutrient_mix(self) -> None:
        self.assertIn("ratio_ec_pid", self.text)
        self.assertIn("nutrient_calcium_ratio_pct", self.text)
        self.assertIn("44.00", self.text)
        self.assertIn("36.00", self.text)
        self.assertIn("12.00", self.text)
        self.assertIn("8.00", self.text)
        self.assertNotIn("ec_component_ratios:", self.text)

    def test_fill_baseline_then_solution_max_true(self) -> None:
        hold = self._find_step("actions", "hold_solution_tank_filling_for_ca_dose")
        seed_fill = self._find_step("actions", "seed_solution_fill_sensor_baseline")
        complete = self._find_step("actions", "complete_solution_fill_after_ec_correction")
        hold_params = ((hold.get("command") or {}).get("params") or {})
        seed_params = ((seed_fill.get("command") or {}).get("params") or {})
        complete_params = ((complete.get("command") or {}).get("params") or {})
        self.assertIs(hold_params.get("level_solution_max_override"), False)
        self.assertIs(seed_params.get("level_solution_max_override"), False)
        self.assertIs(complete_params.get("level_solution_max_override"), True)

        action_names = [item.get("step") for item in self.scenario.get("actions", [])]
        self.assertLess(
            action_names.index("wait_water_baseline_captured_event"),
            action_names.index("complete_solution_fill_after_ec_correction"),
        )
        self.assertLess(
            action_names.index("wait_fill_ec_correction_command"),
            action_names.index("complete_solution_fill_after_ec_correction"),
        )

    def test_waits_water_baseline_and_fill_ca_pump_b(self) -> None:
        baseline = self._find_step("actions", "wait_water_baseline_captured_event")
        fill_dose = self._find_step("actions", "wait_fill_ec_correction_command")
        self.assertIn("type = 'WATER_BASELINE_CAPTURED'", str(baseline.get("query") or ""))
        self.assertIn("channel = 'pump_b'", str(fill_dose.get("query") or ""))
        assertion_names = {item.get("name") for item in self.scenario.get("assertions") or []}
        self.assertIn("water_baseline_captured_event", assertion_names)
        self.assertIn("fill_calcium_dose_on_pump_b", assertion_names)

    def test_enters_prepare_recirculation(self) -> None:
        stage = self._find_step("actions", "wait_prepare_recirculation_stage")
        query = str(stage.get("query") or "")
        self.assertIn("current_stage = 'prepare_recirculation_check'", query)
        assertion_names = {item.get("name") for item in self.scenario.get("assertions") or []}
        self.assertIn("prepare_recirculation_stage_reached", assertion_names)

    def test_recirc_seed_ec_below_t_ca_not_t_full(self) -> None:
        seed = self._find_step("actions", "seed_recirculation_sensor_values")
        seed_params = ((seed.get("command") or {}).get("params") or {})
        ec_value = float(seed_params.get("ec_value"))
        self.assertEqual(ec_value, 0.70)
        self.assertNotIn("level_solution_max_override", seed_params)

        reseed = self._find_step("actions", "reseed_recirculation_sensor_values_for_stability")
        reseed_params = ((reseed.get("command") or {}).get("params") or {})
        self.assertEqual(float(reseed_params.get("ec_value")), 0.70)

        action_names = [item.get("step") for item in self.scenario.get("actions", [])]
        self.assertNotIn("wait_ready_after_task_run", action_names)
        self.assertNotIn("force_near_target_band_after_sequential_loop", action_names)
        assertion_names = {item.get("name") for item in self.scenario.get("assertions") or []}
        self.assertIn("recirc_seed_ec_below_t_ca", assertion_names)
        # Must not sit T_full while calcium is the active step.
        self.assertNotIn("ec_value: 2.33", self.text.split("wait_recirculation_calcium_correction_command")[0])

    def test_waits_pipeline_step_changed_and_ca_then_mg(self) -> None:
        ca_dose = self._find_step("actions", "wait_recirculation_calcium_correction_command")
        ph_dose = self._find_step("actions", "wait_recirculation_ph_correction_command")
        mg_dose = self._find_step("actions", "wait_recirculation_magnesium_correction_command")
        ca_to_ph = self._find_step("actions", "wait_pipeline_step_changed_ca_to_ph")
        ph_to_mg = self._find_step("actions", "wait_pipeline_step_changed_ph_to_mg")
        t_mg_seed = self._find_step("actions", "seed_recirculation_ec_below_t_mg")

        self.assertIn("channel = 'pump_b'", str(ca_dose.get("query") or ""))
        self.assertIn("channel IN ('pump_acid', 'pump_base')", str(ph_dose.get("query") or ""))
        self.assertIn("channel = 'pump_c'", str(mg_dose.get("query") or ""))
        self.assertIn("PIPELINE_STEP_CHANGED", str(ca_to_ph.get("query") or ""))
        self.assertIn("recirc_ca", str(ca_to_ph.get("query") or ""))
        self.assertIn("recirc_ph_after_ca", str(ca_to_ph.get("query") or ""))
        self.assertIn("PIPELINE_STEP_CHANGED", str(ph_to_mg.get("query") or ""))
        self.assertIn("recirc_mg", str(ph_to_mg.get("query") or ""))

        t_mg_ec = float(((t_mg_seed.get("command") or {}).get("params") or {}).get("ec_value"))
        self.assertGreater(t_mg_ec, 0.70)
        self.assertLess(t_mg_ec, 2.33)
        self.assertLess(t_mg_ec, 1.15)

        action_names = [item.get("step") for item in self.scenario.get("actions", [])]
        self.assertLess(
            action_names.index("wait_recirculation_calcium_correction_command"),
            action_names.index("wait_recirculation_ph_correction_command"),
        )
        self.assertLess(
            action_names.index("wait_recirculation_ph_correction_command"),
            action_names.index("wait_recirculation_magnesium_correction_command"),
        )
        self.assertLess(
            action_names.index("wait_pipeline_step_changed_ca_to_ph"),
            action_names.index("wait_pipeline_step_changed_ph_to_mg"),
        )
        assertion_names = {item.get("name") for item in self.scenario.get("assertions") or []}
        self.assertIn("recirc_calcium_dose_on_pump_b", assertion_names)
        self.assertIn("recirc_ph_dose_after_calcium", assertion_names)
        self.assertIn("recirc_magnesium_dose_on_pump_c", assertion_names)
        self.assertIn("pipeline_step_changed_ca_to_ph", assertion_names)
        self.assertIn("pipeline_step_changed_ph_to_mg", assertion_names)
        self.assertIn("pump_c_calibration_is_magnesium", assertion_names)

    def test_recirc_dilute_pct_is_15_not_100(self) -> None:
        self.assertIn("ec_overshoot_dilute_pct: 15", self.text)
        self.assertNotIn("ec_overshoot_dilute_pct: 100", self.text)

    def test_short_path_forbids_irrig_recirc_and_full_ready(self) -> None:
        action_names = [item.get("step") for item in self.scenario.get("actions", [])]
        self.assertNotIn("wait_ready_after_task_run", action_names)
        text_lower = self.text.lower()
        self.assertNotIn("irrig_recirc", text_lower)
        self.assertNotIn("irrigation_recovery", text_lower)
        self.assertIn("wait_prepare_recirculation_stage", action_names)
        self.assertIn("cleanup_zone_prepare_baselines", action_names)


if __name__ == "__main__":
    unittest.main()
