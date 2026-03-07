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

    def test_scheduler_suite_contains_start_cycle_intent_path(self) -> None:
        scenarios = self.suite._get_suite_scenarios("scheduler")
        self.assert_contains_scenario(
            scenarios,
            "scenarios/scheduler/E93_start_cycle_intent_executor_path.yaml",
        )

    def test_ae3lite_suite_contains_contract_and_realhw_paths(self) -> None:
        scenarios = self.suite._get_suite_scenarios("ae3lite")
        for suffix in [
            "scenarios/ae3lite/E95_ae3_start_cycle_done_completed.yaml",
            "scenarios/ae3lite/E99_ae3_double_execution_guard.yaml",
            "scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml",
        ]:
            self.assert_contains_scenario(scenarios, suffix)

    def test_ae3lite_realhw_suite_contains_two_tank_smoke(self) -> None:
        scenarios = self.suite._get_suite_scenarios("ae3lite_realhw")
        self.assert_contains_scenario(
            scenarios,
            "scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml",
        )

    def test_automation_engine_suite_contains_legacy_entrypoints(self) -> None:
        scenarios = self.suite._get_suite_scenarios("automation_engine")
        for suffix in [
            "scenarios/automation_engine/E61_fail_closed_corrections.yaml",
            "scenarios/automation_engine/E65_phase_transition_api.yaml",
            "scenarios/automation_engine/E74_node_zone_mismatch_guard.yaml",
        ]:
            self.assert_contains_scenario(scenarios, suffix)

    def test_workflow_suite_contains_legacy_entrypoints(self) -> None:
        scenarios = self.suite._get_suite_scenarios("workflow")
        for suffix in [
            "scenarios/workflow/E83_clean_water_fill.yaml",
            "scenarios/workflow/E89_correction_state_machine_and_duration_aware.yaml",
            "scenarios/workflow/E94_startup_to_ready_smoke.yaml",
        ]:
            self.assert_contains_scenario(scenarios, suffix)

    def test_discover_by_suite_alias_supports_ae3_suites(self) -> None:
        discovered = self.suite.discover_scenarios(["ae3lite_v1", "ae3lite_realhw"])
        self.assert_contains_scenario(
            discovered,
            "scenarios/ae3lite/E95_ae3_start_cycle_done_completed.yaml",
        )
        self.assert_contains_scenario(
            discovered,
            "scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml",
        )

    def test_cli_parser_includes_ae3_suites(self) -> None:
        parser = TestSuite.create_cli_parser()
        suite_option = next(action for action in parser._actions if action.dest == "suite")
        choices = set(suite_option.choices or [])

        for suite_name in [
            "ae3lite",
            "ae3lite_v1",
            "ae3lite_realhw",
            "scheduler",
            "automation_engine",
            "workflow",
        ]:
            self.assertIn(suite_name, choices)

    def test_full_suite_includes_legacy_and_ae3_scenarios(self) -> None:
        scenarios = self.suite._get_suite_scenarios("full")
        self.assert_contains_scenario(
            scenarios,
            "scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml",
        )
        self.assert_contains_scenario(
            scenarios,
            "scenarios/automation_engine/E61_fail_closed_corrections.yaml",
        )
        self.assert_contains_scenario(
            scenarios,
            "scenarios/workflow/E94_startup_to_ready_smoke.yaml",
        )

    def test_scheduler_tags_are_inferred_from_path(self) -> None:
        scenario_path = E2E_ROOT / "scenarios" / "scheduler" / "E93_start_cycle_intent_executor_path.yaml"
        tags = self.suite._get_scenario_tags(str(scenario_path))
        self.assertIn("scheduler", tags)
        self.assertIn("start_cycle", tags)

    def test_ae3lite_realhw_tags_are_inferred_from_path(self) -> None:
        scenario_path = E2E_ROOT / "scenarios" / "ae3lite" / "E100_ae3_two_tank_realhw_smoke.yaml"
        tags = self.suite._get_scenario_tags(str(scenario_path))
        self.assertIn("ae3lite", tags)
        self.assertIn("realhw", tags)
        self.assertIn("two_tank", tags)
        self.assertIn("smoke", tags)


if __name__ == "__main__":
    unittest.main()
