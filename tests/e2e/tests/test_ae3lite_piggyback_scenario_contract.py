#!/usr/bin/env python3
"""
Regression tests for AE3-Lite piggyback real-hardware scenario contract.
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
        ec_step = self._find_step("actions", "wait_recirculation_ec_correction_command")
        ph_step = self._find_step("actions", "wait_recirculation_ph_correction_command")

        stage_query = str(stage_step.get("query") or "")
        self.assertIn("updated_at AS stage_started_at", stage_query)

        ec_query = str(ec_step.get("query") or "")
        self.assertIn("created_at >= CAST(:after_stage_started_at AS timestamptz)", ec_query)
        self.assertEqual(
            ec_step.get("params", {}).get("after_stage_started_at"),
            "${prepare_recirc_stage_row.0.stage_started_at}",
        )

        ph_query = str(ph_step.get("query") or "")
        self.assertIn("created_at >= CAST(:after_stage_started_at AS timestamptz)", ph_query)
        self.assertEqual(
            ph_step.get("params", {}).get("after_command_id"),
            "${recirc_ec_correction_row.0.id}",
        )

    def test_post_piggyback_checks_require_live_targets_not_just_status(self) -> None:
        task_step = self._find_step("actions", "wait_task_not_failed_after_piggyback")
        targets_step = self._find_step("actions", "wait_targets_reached_on_node_after_piggyback")
        internal_assert = self._find_assertion("internal_task_not_failed")
        targets_assert = self._find_assertion("targets_reached_after_piggyback")

        task_query = str(task_step.get("query") or "")
        self.assertIn("status IN ('pending', 'completed')", task_query)
        self.assertNotIn("current_stage = 'prepare_recirculation_check'", task_query)

        targets_query = str(targets_step.get("query") or "")
        self.assertIn("ph.last_value BETWEEN 5.00 AND 5.15", targets_query)
        self.assertIn("ec.last_value BETWEEN 2.30 AND 2.38", targets_query)
        self.assertIn("ph.last_ts >= NOW() - INTERVAL '30 seconds'", targets_query)
        self.assertNotIn("OR EXISTS", targets_query)

        condition = str(internal_assert.get("condition") or "")
        self.assertIn("in ('pending', 'completed')", condition)

        targets_condition = str(targets_assert.get("condition") or "")
        self.assertIn("len(context.get('targets_reached_after_piggyback_row', [])) == 1", targets_condition)

    def test_fixture_profile_does_not_embed_legacy_startup_or_correction_runtime(self) -> None:
        profile_step = self._find_step("actions", "insert_ae3_profile")
        query = str(profile_step.get("query") or "")

        self.assertNotIn("'startup', jsonb_build_object(", query)
        self.assertNotIn("'correction', jsonb_build_object(", query)
        self.assertIn("'two_tank_commands', jsonb_build_object(", query)


if __name__ == "__main__":
    unittest.main()
