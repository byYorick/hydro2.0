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

    def test_workflow_suite_contains_ec_ph_chain(self) -> None:
        scenarios = self.suite._get_suite_scenarios("workflow")
        for suffix in [
            "scenarios/workflow/E83_clean_water_fill.yaml",
            "scenarios/workflow/E86_ec_ph_correction.yaml",
            "scenarios/workflow/E87_ec_ph_correction_during_fill.yaml",
            "scenarios/workflow/E89_correction_state_machine_and_duration_aware.yaml",
        ]:
            self.assert_contains_scenario(scenarios, suffix)

    def test_realhw_automation_suite_contains_full_prod_path(self) -> None:
        scenarios = self.suite._get_suite_scenarios("automation_engine_realhw")
        for suffix in [
            "scenarios/automation_engine/E66_full_prod_path_zone_recipe_bind_and_run.yaml",
            "scenarios/automation_engine/E68_full_prod_path_strict_ec_ph_corrections.yaml",
        ]:
            self.assert_contains_scenario(scenarios, suffix)

    def test_prod_readiness_realhw_suite_contains_required_chain(self) -> None:
        scenarios = self.suite._get_suite_scenarios("prod_readiness_realhw")
        for suffix in [
            "scenarios/scheduler/E93_start_cycle_intent_executor_path.yaml",
            "scenarios/automation_engine/E66_full_prod_path_zone_recipe_bind_and_run.yaml",
            "scenarios/automation_engine/E68_full_prod_path_strict_ec_ph_corrections.yaml",
            "scenarios/workflow/E89_correction_state_machine_and_duration_aware.yaml",
        ]:
            self.assert_contains_scenario(scenarios, suffix)

    def test_discover_by_suite_alias_supports_new_suites(self) -> None:
        discovered = self.suite.discover_scenarios(["scheduler", "workflow", "prod_readiness_realhw"])
        self.assert_contains_scenario(
            discovered,
            "scenarios/scheduler/E93_start_cycle_intent_executor_path.yaml",
        )
        self.assert_contains_scenario(
            discovered,
            "scenarios/workflow/E89_correction_state_machine_and_duration_aware.yaml",
        )

    def test_cli_parser_includes_new_suites(self) -> None:
        parser = TestSuite.create_cli_parser()
        suite_option = next(action for action in parser._actions if action.dest == "suite")
        choices = set(suite_option.choices or [])

        for suite_name in [
            "scheduler",
            "workflow",
            "automation_engine_realhw",
            "prod_readiness_realhw",
        ]:
            self.assertIn(suite_name, choices)

    def test_scheduler_tags_are_inferred_from_path(self) -> None:
        scenario_path = E2E_ROOT / "scenarios" / "scheduler" / "E93_start_cycle_intent_executor_path.yaml"
        tags = self.suite._get_scenario_tags(str(scenario_path))
        self.assertIn("scheduler", tags)
        self.assertIn("start_cycle", tags)


if __name__ == "__main__":
    unittest.main()
