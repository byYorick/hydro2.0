#!/usr/bin/env python3
"""Unit tests for named E2E step-sequence includes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from runner.scenario_loader import expand_include_sequences, load_scenario_file

HELPER = E2E_ROOT / "scenarios" / "ae3lite" / "_two_tank_fill_helper.yaml"
E101 = E2E_ROOT / "scenarios" / "ae3lite" / "E101_ae3_two_tank_realhw_setup_ready.yaml"


class TestAe3LiteStepSequenceLoader(unittest.TestCase):
    def test_helper_defines_two_tank_fill_ca(self) -> None:
        self.assertTrue(HELPER.is_file())
        helper = load_scenario_file(HELPER)
        # Helper itself has no include_sequence; sequences stay on the document.
        self.assertEqual(helper.get("kind"), "step_sequences")

    def test_e101_expands_fill_helper_before_recirc(self) -> None:
        scenario = load_scenario_file(E101)
        names = [item.get("step") for item in scenario.get("actions") or []]
        self.assertNotIn("include_sequence", names)
        recirc_at = names.index("wait_prepare_recirculation_stage")
        fill_names = [
            "hold_solution_tank_filling_for_ca_dose",
            "seed_solution_fill_sensor_baseline",
            "wait_water_baseline_captured_event",
            "wait_fill_ec_correction_command",
            "load_fill_ph_correction_commands_if_any",
            "complete_solution_fill_after_ec_correction",
        ]
        for name in fill_names:
            self.assertIn(name, names)
            self.assertLess(names.index(name), recirc_at)

    def test_aliases_rename_contract_step(self) -> None:
        scenario = {
            "actions": [
                {
                    "include_sequence": "two_tank_fill_ca",
                    "helper": str(HELPER),
                    "aliases": {
                        "hold_solution_tank_filling_for_ca_dose": "force_solution_tank_filling",
                    },
                }
            ]
        }
        expanded = expand_include_sequences(scenario, HELPER.parent)
        names = [item.get("step") for item in expanded["actions"]]
        self.assertIn("force_solution_tank_filling", names)
        self.assertNotIn("hold_solution_tank_filling_for_ca_dose", names)
        wait = next(
            item
            for item in expanded["actions"]
            if item.get("step") == "wait_hold_solution_tank_filling_for_ca_dose_done"
        )
        cmd_id = ((wait.get("params") or {}).get("cmd_id") or "")
        self.assertIn("force_solution_tank_filling_response", cmd_id)


if __name__ == "__main__":
    unittest.main()
