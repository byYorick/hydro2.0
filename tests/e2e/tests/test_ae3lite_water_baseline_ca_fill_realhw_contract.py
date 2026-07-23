#!/usr/bin/env python3
"""Contract checks for live-short E118 water baseline + Ca-only fill realhw."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E118_ae3_water_baseline_and_ca_fill_realhw.yaml"
)


class TestAe3LiteWaterBaselineCaFillRealhwContract(unittest.TestCase):
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
        self.assertEqual(self.scenario.get("name"), "E118_ae3_water_baseline_and_ca_fill_realhw")
        self.assertNotEqual(self.scenario.get("status"), "stub")
        self.assertNotIn("skip_live: true", self.text)
        self.assertIn("realhw", self.scenario.get("tags") or [])

    def test_clears_stale_prepare_baselines_before_run(self) -> None:
        step = self._find_step("actions", "cleanup_zone_prepare_baselines")
        query = str(step.get("query") or "")
        self.assertIn("DELETE FROM zone_prepare_baselines", query)
        self.assertIn("tank_recirc", self.text)
        # Ratios come from grow_cycle_phases.nutrient_* (zone.correction rejects ec_component_ratios).
        self.assertNotIn("ec_component_ratios:", self.text)
        self.assertIn("nutrient_calcium_ratio_pct", self.text)
        self.assertIn("ratio_ec_pid", self.text)

    def test_waits_water_baseline_captured_event(self) -> None:
        step = self._find_step("actions", "wait_water_baseline_captured_event")
        query = str(step.get("query") or "")
        self.assertIn("type = 'WATER_BASELINE_CAPTURED'", query)
        self.assertIn("FROM zone_events", query)
        assertion_names = {item.get("name") for item in self.scenario.get("assertions") or []}
        self.assertIn("water_baseline_captured_event", assertion_names)

    def test_fill_ca_dose_hold_seed_force_near_pattern(self) -> None:
        hold = self._find_step("actions", "hold_solution_tank_filling_for_ca_dose")
        seed = self._find_step("actions", "seed_solution_fill_sensor_baseline")
        wait_dose = self._find_step("actions", "wait_fill_ec_correction_command")

        hold_params = ((hold.get("command") or {}).get("params") or {})
        self.assertIs(hold_params.get("level_solution_max_override"), False)

        seed_params = ((seed.get("command") or {}).get("params") or {})
        self.assertIs(seed_params.get("level_solution_max_override"), False)
        self.assertEqual(seed_params.get("ec_value"), 0.45)

        dose_query = str(wait_dose.get("query") or "")
        self.assertIn("channel = 'pump_b'", dose_query)
        self.assertIn("payload->>'cmd' = 'dose'", dose_query)

        action_names = [item.get("step") for item in self.scenario.get("actions", [])]
        self.assertLess(
            action_names.index("wait_water_baseline_captured_event"),
            action_names.index("wait_fill_ec_correction_command"),
        )

    def test_zero_ph_doses_in_fill_window(self) -> None:
        zero_step = self._find_step("actions", "assert_zero_fill_ph_doses_query")
        summary = self._find_step("actions", "load_fill_window_dose_summary")
        complete = self._find_step("actions", "complete_solution_fill_after_ec_correction")
        zero_q = str(zero_step.get("query") or "")
        summary_q = str(summary.get("query") or "")
        self.assertIn("channel IN ('pump_acid', 'pump_base')", zero_q)
        self.assertIn("channel IN ('pump_acid', 'pump_base')", summary_q)
        self.assertIn("channel = 'pump_b'", summary_q)
        # Fill-window snapshot must happen before max=true exit (prepare may dose pH).
        action_names = [item.get("step") for item in self.scenario.get("actions", [])]
        self.assertLess(
            action_names.index("load_fill_window_dose_summary"),
            action_names.index(complete.get("step")),
        )
        assertion_names = {item.get("name") for item in self.scenario.get("assertions") or []}
        self.assertIn("zero_ph_doses_in_fill_window", assertion_names)
        self.assertIn("fill_window_has_calcium_dose", assertion_names)

    def test_multi_pump_calibrations_calcium_on_pump_b(self) -> None:
        cal_insert = self._find_step("actions", "insert_correction_calibrations")
        insert_q = str(cal_insert.get("query") or "")
        self.assertIn("'calcium'", insert_q)
        self.assertIn("ec_pump_b_channel_id", insert_q)

        pump_b = self._find_step("actions", "load_calcium_pump_b_calibration")
        multi = self._find_step("actions", "load_multi_pump_component_calibrations")
        self.assertIn("component = 'calcium'", str(pump_b.get("query") or ""))
        multi_q = str(multi.get("query") or "")
        self.assertIn("'npk', 'calcium', 'magnesium', 'micro'", multi_q)
        assertion_names = {item.get("name") for item in self.scenario.get("assertions") or []}
        self.assertIn("pump_b_calibration_is_calcium", assertion_names)
        self.assertIn("multi_pump_component_calibrations_present", assertion_names)

    def test_short_path_skips_prepare_and_ready(self) -> None:
        action_names = [item.get("step") for item in self.scenario.get("actions", [])]
        self.assertNotIn("wait_prepare_recirculation_stage", action_names)
        self.assertNotIn("seed_recirculation_sensor_values", action_names)
        self.assertNotIn("wait_ready_after_task_run", action_names)
        self.assertIn("complete_solution_fill_after_ec_correction", action_names)
        text_lower = self.text.lower()
        self.assertNotIn("irrig_recirc", text_lower)
        self.assertNotIn("irrigation_recovery", text_lower)


if __name__ == "__main__":
    unittest.main()
