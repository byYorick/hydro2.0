#!/usr/bin/env python3
"""
Regression tests for E2E suite catalog coverage.
"""

import sys
import unittest
from pathlib import Path


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from runner.suite import TestSuite  # noqa: E402


class TestSuiteCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.suite = TestSuite()

    def assert_contains_scenario(self, scenarios, relative_suffix: str) -> None:
        self.assertTrue(
            any(Path(item).as_posix().endswith(relative_suffix) for item in scenarios),
            msg=f"Scenario '{relative_suffix}' is missing in suite: {scenarios}",
        )

    def assert_missing_scenario(self, scenarios, relative_suffix: str) -> None:
        self.assertFalse(
            any(Path(item).as_posix().endswith(relative_suffix) for item in scenarios),
            msg=f"Scenario '{relative_suffix}' should not be in suite: {scenarios}",
        )

    def test_scheduler_suite_does_not_call_removed_ae3_ingress(self) -> None:
        scenarios = self.suite._get_suite_scenarios("scheduler")
        self.assert_contains_scenario(
            scenarios,
            "scenarios/scheduler/E80_irrigation_schedule_happy.yaml",
        )
        self.assertFalse(any("E93_start_cycle" in item or "E94_start_lighting" in item for item in scenarios))

    def test_ae4_suite_contains_node_sim_scenarios(self) -> None:
        scenarios = self.suite._get_suite_scenarios("ae4")
        self.assertEqual(len(scenarios), 2)
        self.assert_contains_scenario(
            scenarios,
            "scenarios/ae4/AE4_SIM_01_node_sim_planned_shot.yaml",
        )
        self.assert_contains_scenario(
            scenarios,
            "scenarios/ae4/AE4_SIM_02_node_sim_both_tanks_empty.yaml",
        )

    def test_removed_ae3_suites_are_unknown(self) -> None:
        for suite_name in (
            "ae3lite",
            "ae3lite_contract",
            "ae3lite_v1",
            "ae3lite_realhw",
            "ae3lite_testnode_realhw_core",
            "ae3lite_testnode_realhw_irrigation",
        ):
            self.assertEqual(self.suite._get_suite_scenarios(suite_name), [])

    def test_calibration_realhw_suite_contains_sensor_calibration_scenarios(self) -> None:
        scenarios = self.suite._get_suite_scenarios("calibration_realhw")
        for suffix in [
            "scenarios/calibration/E110_sensor_calibration_realhw_create_cancel.yaml",
            "scenarios/calibration/E111_sensor_calibration_realhw_force_invalid.yaml",
            "scenarios/calibration/E117_sensor_calibration_realhw_happy_path.yaml",
        ]:
            self.assert_contains_scenario(scenarios, suffix)

    def test_automation_engine_suite_keeps_unique_sim_scenarios_only(self) -> None:
        scenarios = self.suite._get_suite_scenarios("automation_engine")
        for suffix in [
            "scenarios/automation_engine/E64_effective_targets_only.yaml",
            "scenarios/automation_engine/E65_phase_transition_api.yaml",
            "scenarios/automation_engine/E74_node_zone_mismatch_guard.yaml",
        ]:
            self.assert_contains_scenario(scenarios, suffix)
        self.assertEqual(len(scenarios), 3)

    def test_workflow_suite_keeps_unique_sim_scenarios_only(self) -> None:
        scenarios = self.suite._get_suite_scenarios("workflow")
        for suffix in [
            "scenarios/workflow/E96_reactive_solution_topup_level_switch.yaml",
            "scenarios/workflow/E97_solution_change_operator_gate.yaml",
        ]:
            self.assert_contains_scenario(scenarios, suffix)
        self.assertEqual(len(scenarios), 2)

    def test_prod_readiness_realhw_is_calibration_only(self) -> None:
        scenarios = self.suite._get_suite_scenarios("prod_readiness_realhw")
        self.assertEqual(len(scenarios), 3)
        self.assert_contains_scenario(
            scenarios,
            "scenarios/calibration/E110_sensor_calibration_realhw_create_cancel.yaml",
        )
        self.assert_contains_scenario(
            scenarios,
            "scenarios/calibration/E117_sensor_calibration_realhw_happy_path.yaml",
        )
        self.assertFalse(any("ae3lite" in item for item in scenarios))

    def test_discover_by_suite_alias_supports_ae4(self) -> None:
        discovered = self.suite.discover_scenarios(["ae4"])
        self.assert_contains_scenario(
            discovered,
            "scenarios/ae4/AE4_SIM_01_node_sim_planned_shot.yaml",
        )
        self.assert_contains_scenario(
            discovered,
            "scenarios/ae4/AE4_SIM_02_node_sim_both_tanks_empty.yaml",
        )

    def test_discover_by_suite_alias_supports_calibration_realhw_suite(self) -> None:
        discovered = self.suite.discover_scenarios(["calibration_realhw"])
        self.assert_contains_scenario(
            discovered,
            "scenarios/calibration/E110_sensor_calibration_realhw_create_cancel.yaml",
        )
        self.assert_contains_scenario(
            discovered,
            "scenarios/calibration/E111_sensor_calibration_realhw_force_invalid.yaml",
        )
        self.assert_contains_scenario(
            discovered,
            "scenarios/calibration/E117_sensor_calibration_realhw_happy_path.yaml",
        )

    def test_cli_parser_includes_ae3_suites(self) -> None:
        parser = TestSuite.create_cli_parser()
        suite_option = next(action for action in parser._actions if action.dest == "suite")
        choices = set(suite_option.choices or [])

        for suite_name in [
            "ae4",
            "calibration_realhw",
            "scheduler",
            "automation_engine",
            "workflow",
            "prod_readiness_realhw",
        ]:
            self.assertIn(suite_name, choices)
        for removed in (
            "ae3lite",
            "ae3lite_contract",
            "ae3lite_v1",
            "ae3lite_realhw",
        ):
            self.assertNotIn(removed, choices)

    def test_full_suite_includes_sim_scenarios_without_ae3(self) -> None:
        scenarios = self.suite._get_suite_scenarios("full")
        self.assertFalse(any("ae3lite" in item for item in scenarios))
        self.assert_contains_scenario(
            scenarios,
            "scenarios/ae4/AE4_SIM_01_node_sim_planned_shot.yaml",
        )
        self.assert_contains_scenario(
            scenarios,
            "scenarios/automation_engine/E64_effective_targets_only.yaml",
        )
        self.assert_contains_scenario(
            scenarios,
            "scenarios/workflow/E96_reactive_solution_topup_level_switch.yaml",
        )
        self.assert_contains_scenario(
            scenarios,
            "scenarios/calibration/E110_sensor_calibration_realhw_create_cancel.yaml",
        )

    def test_full_suite_excludes_debug_scenarios(self) -> None:
        scenarios = self.suite._get_suite_scenarios("full")
        self.assertFalse(
            any("debug" in Path(item).stem.lower() for item in scenarios),
            msg=f"Debug scenario leaked into full suite: {scenarios}",
        )

    def test_scheduler_tags_are_inferred_from_path(self) -> None:
        scenario_path = E2E_ROOT / "scenarios" / "scheduler" / "E80_irrigation_schedule_happy.yaml"
        tags = self.suite._get_scenario_tags(str(scenario_path))
        self.assertIn("scheduler", tags)

    def test_ae4_tags_are_inferred_from_path(self) -> None:
        scenario_path = E2E_ROOT / "scenarios" / "ae4" / "AE4_SIM_01_node_sim_planned_shot.yaml"
        tags = self.suite._get_scenario_tags(str(scenario_path))
        self.assertIn("ae4", tags)
        self.assertIn("mqtt", tags)

    def test_calibration_realhw_tags_are_inferred_from_path(self) -> None:
        scenario_path = (
            E2E_ROOT
            / "scenarios"
            / "calibration"
            / "E110_sensor_calibration_realhw_create_cancel.yaml"
        )
        tags = self.suite._get_scenario_tags(str(scenario_path))
        self.assertIn("calibration", tags)
        self.assertIn("realhw", tags)
        self.assertIn("smoke", tags)


if __name__ == "__main__":
    unittest.main()
