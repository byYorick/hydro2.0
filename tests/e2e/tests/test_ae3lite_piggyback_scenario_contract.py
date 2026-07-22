#!/usr/bin/env python3
"""
Regression tests for AE3-Lite sequential nutrient pipeline real-hardware scenario contract.
(Legacy filename: piggyback — scenario now asserts Ca→pH pipeline, not EC→pH batch.)
"""

import sys
import unittest
from pathlib import Path

import yaml


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

SCENARIO_PATH = E2E_ROOT / "scenarios" / "ae3lite" / "E106_ae3_two_tank_realhw_piggyback_ec_ph_cycle.yaml"


class TestAe3LitePiggybackScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def _find_assertion(self, name: str) -> dict:
        for item in self.scenario.get("assertions", []):
            if item.get("name") == name:
                return item
        self.fail(f"Assertion '{name}' is missing")

    def test_recirculation_commands_are_anchored_to_stage_start(self) -> None:
        stage_step = self._find_step("actions", "wait_prepare_recirculation_stage")
        ca_step = self._find_step("actions", "wait_recirculation_calcium_correction_command")
        ph_step = self._find_step("actions", "wait_recirculation_ph_correction_command")

        stage_query = str(stage_step.get("query") or "")
        self.assertIn("updated_at AS stage_started_at", stage_query)

        ca_query = str(ca_step.get("query") or "")
        self.assertIn("created_at >= CAST(:after_seeded_at AS timestamptz)", ca_query)
        self.assertEqual(
            ca_step.get("params", {}).get("after_seeded_at"),
            "${reseed_recirculation_command_row.0.created_at}",
        )
        self.assertIn("channel = 'pump_b'", ca_query)
        self.assertIn("payload->>'cmd' = 'dose'", ca_query)

        ph_query = str(ph_step.get("query") or "")
        self.assertIn("created_at >= CAST(:after_seeded_at AS timestamptz)", ph_query)
        self.assertEqual(
            ph_step.get("params", {}).get("after_command_id"),
            "${recirc_ec_correction_row.0.id}",
        )
        self.assertEqual(
            ph_step.get("params", {}).get("after_seeded_at"),
            "${reseed_recirculation_command_row.0.created_at}",
        )
        self.assertIn("payload->>'cmd' = 'dose'", ph_query)

    def test_post_pipeline_checks_require_live_targets_not_just_status(self) -> None:
        task_step = self._find_step("actions", "wait_task_not_failed_after_sequential_loop")
        force_step = self._find_step("actions", "force_near_target_band_after_sequential_loop")
        targets_step = self._find_step("actions", "wait_targets_reached_on_node_after_sequential_loop")
        internal_assert = self._find_assertion("internal_task_not_failed")
        targets_assert = self._find_assertion("targets_reached_after_sequential_loop")

        task_query = str(task_step.get("query") or "")
        self.assertIn("status IN ('pending', 'claimed', 'running', 'waiting_command', 'completed')", task_query)
        self.assertNotIn("current_stage = 'prepare_recirculation_check'", task_query)

        action_names = [item.get("step") for item in self.scenario.get("actions", [])]
        self.assertLess(
            action_names.index("force_near_target_band_after_sequential_loop"),
            action_names.index("wait_targets_reached_on_node_after_sequential_loop"),
        )
        force_params = ((force_step.get("command") or {}).get("params") or {})
        self.assertEqual(force_params.get("ph_value"), 5.10)
        self.assertEqual(force_params.get("ec_value"), 2.33)

        targets_query = str(targets_step.get("query") or "")
        self.assertIn("ph.last_value BETWEEN 5.00 AND 5.15", targets_query)
        self.assertIn("ec.last_value BETWEEN 2.30 AND 2.38", targets_query)
        self.assertIn("ph.last_ts >= NOW() - INTERVAL '30 seconds'", targets_query)
        self.assertNotIn("OR EXISTS", targets_query)
        self.assertLessEqual(float(targets_step.get("timeout") or 999), 90.0)

        condition = str(internal_assert.get("condition") or "")
        self.assertIn("in ('pending', 'claimed', 'running', 'waiting_command', 'completed')", condition)

        targets_condition = str(targets_assert.get("condition") or "")
        self.assertIn("len(context.get('targets_reached_after_sequential_loop_row', [])) == 1", targets_condition)

    def test_fixture_profile_uses_calcium_fill_and_recirc_dilute(self) -> None:
        profile_step = self._find_step("actions", "apply_test_node_correction_preset")
        payload = (profile_step.get("payload") or {}).get("payload") or {}
        phase_overrides = payload.get("phase_overrides") or {}
        solution_fill = phase_overrides.get("solution_fill") or {}
        tank_recirc = phase_overrides.get("tank_recirc") or {}

        fill_dosing = solution_fill.get("dosing") or {}
        self.assertEqual(fill_dosing.get("dose_ec_channel"), "pump_b")
        self.assertEqual(fill_dosing.get("dose_ph_up_channel"), "pump_base")
        self.assertEqual(fill_dosing.get("dose_ph_down_channel"), "pump_acid")

        recirc = tank_recirc.get("recirc") or {}
        self.assertEqual(recirc.get("ec_overshoot_dilute_pct"), 15)
        self.assertEqual(recirc.get("dilute_pulse_sec"), 10)
        self.assertEqual(recirc.get("dilute_max_attempts"), 3)
        self.assertEqual(recirc.get("dilute_settle_sec"), 30)

        text = SCENARIO_PATH.read_text(encoding="utf-8")
        self.assertNotIn("irrig_recirc", text)
        self.assertNotIn("irrigation_recovery", text)
        self.assertNotIn("target_ec_prepare", text)
        self.assertNotIn("npk_ec_share", text)
        # Sequential nutrient stubs stay contract-only; live coverage remains E106/E104.
        for stub_id in ("E118", "E119", "E120", "E121"):
            self.assertNotIn(f"{stub_id}_", text)

    def test_fill_ca_dose_requires_tank_not_full(self) -> None:
        """In-flow fill Ca (pump_b) needs solution_max=false; max=true skips to prepare."""
        hold_step = self._find_step("actions", "hold_solution_tank_filling_for_ca_dose")
        seed_step = self._find_step("actions", "seed_solution_fill_sensor_baseline")
        wait_dose = self._find_step("actions", "wait_fill_ec_correction_command")
        complete_step = self._find_step("actions", "complete_solution_fill_after_ec_correction")

        hold_params = ((hold_step.get("command") or {}).get("params") or {})
        self.assertIs(hold_params.get("level_solution_max_override"), False)
        self.assertIs(hold_params.get("level_solution_min_override"), True)

        seed_params = ((seed_step.get("command") or {}).get("params") or {})
        self.assertIs(seed_params.get("level_solution_max_override"), False)
        self.assertEqual(seed_params.get("ec_value"), 0.45)

        dose_query = str(wait_dose.get("query") or "")
        self.assertIn("channel = 'pump_b'", dose_query)

        complete_params = ((complete_step.get("command") or {}).get("params") or {})
        self.assertIs(complete_params.get("level_solution_max_override"), True)

        action_names = [item.get("step") for item in self.scenario.get("actions", [])]
        self.assertLess(
            action_names.index("hold_solution_tank_filling_for_ca_dose"),
            action_names.index("wait_fill_ec_correction_command"),
        )
        self.assertLess(
            action_names.index("wait_fill_ec_correction_command"),
            action_names.index("complete_solution_fill_after_ec_correction"),
        )


if __name__ == "__main__":
    unittest.main()
