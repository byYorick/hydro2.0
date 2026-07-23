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
            "scenarios/ae3lite/E110_ae3_node_runtime_event_contract.yaml",
            "scenarios/ae3lite/E107_ae3_irrigation_runtime_test_node.yaml",
            "scenarios/ae3lite/E108_ae3_soil_moisture_telemetry_contract.yaml",
            "scenarios/ae3lite/E109_ae3_irrigation_inline_correction_test_node.yaml",
            "scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml",
            "scenarios/ae3lite/E112_ae3_per_phase_ec_target_realhw.yaml",
            "scenarios/ae3lite/E113_ae3_prepare_recirc_solution_low_to_setup_realhw.yaml",
        ]:
            self.assert_contains_scenario(scenarios, suffix)

    def test_ae3lite_realhw_suite_contains_two_tank_smoke(self) -> None:
        scenarios = self.suite._get_suite_scenarios("ae3lite_realhw")
        for suffix in [
            "scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml",
            "scenarios/ae3lite/E107_ae3_irrigation_runtime_test_node.yaml",
            "scenarios/ae3lite/E108_ae3_soil_moisture_telemetry_contract.yaml",
            "scenarios/ae3lite/E109_ae3_irrigation_inline_correction_test_node.yaml",
        ]:
            self.assert_contains_scenario(scenarios, suffix)
        self.assert_missing_scenario(
            scenarios,
            "scenarios/ae3lite/E102_ae3_two_tank_realhw_ready_during_recirculation.yaml",
        )

    def test_ae3lite_decomposed_suites_match_new_taxonomy(self) -> None:
        contract = self.suite._get_suite_scenarios("ae3lite_contract")
        realhw_core = self.suite._get_suite_scenarios("ae3lite_testnode_realhw_core")
        realhw_irrigation = self.suite._get_suite_scenarios("ae3lite_testnode_realhw_irrigation")

        self.assert_contains_scenario(contract, "scenarios/ae3lite/E95_ae3_start_cycle_done_completed.yaml")
        self.assert_contains_scenario(contract, "scenarios/ae3lite/E99_ae3_double_execution_guard.yaml")
        self.assert_contains_scenario(contract, "scenarios/ae3lite/E110_ae3_node_runtime_event_contract.yaml")
        self.assert_contains_scenario(realhw_core, "scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml")
        self.assert_contains_scenario(
            realhw_core,
            "scenarios/ae3lite/E113_ae3_prepare_recirc_solution_low_to_setup_realhw.yaml",
        )
        self.assert_contains_scenario(
            realhw_core,
            "scenarios/ae3lite/E114_ae3_reactive_solution_topup_level_switch_realhw.yaml",
        )
        self.assert_contains_scenario(
            realhw_core,
            "scenarios/ae3lite/E115_ae3_solution_change_operator_gate_realhw.yaml",
        )
        self.assert_contains_scenario(
            realhw_core,
            "scenarios/ae3lite/E116_ae3_estop_failsafe_events_realhw.yaml",
        )
        self.assert_contains_scenario(
            realhw_core,
            "scenarios/ae3lite/E118_ae3_water_baseline_and_ca_fill_realhw.yaml",
        )
        self.assert_contains_scenario(
            realhw_core,
            "scenarios/ae3lite/E120_ae3_recirc_dilute_overshoot_realhw.yaml",
        )
        self.assertEqual(len(realhw_core), 14)
        self.assert_contains_scenario(
            realhw_irrigation,
            "scenarios/ae3lite/E107_ae3_irrigation_runtime_test_node.yaml",
        )
        self.assert_contains_scenario(
            realhw_irrigation,
            "scenarios/ae3lite/E109_ae3_irrigation_inline_correction_test_node.yaml",
        )

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

    def test_prod_readiness_realhw_maps_to_canonical_ae3_set(self) -> None:
        scenarios = self.suite._get_suite_scenarios("prod_readiness_realhw")
        self.assert_contains_scenario(scenarios, "scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml")
        self.assert_contains_scenario(
            scenarios,
            "scenarios/calibration/E110_sensor_calibration_realhw_create_cancel.yaml",
        )
        self.assert_contains_scenario(
            scenarios,
            "scenarios/calibration/E117_sensor_calibration_realhw_happy_path.yaml",
        )
        # ae3lite realhw (+E118/E120) ∪ smart_irrigation ∪ calibration
        self.assertEqual(len(scenarios), 20)
        self.assert_contains_scenario(
            scenarios,
            "scenarios/ae3lite/E118_ae3_water_baseline_and_ca_fill_realhw.yaml",
        )
        self.assert_contains_scenario(
            scenarios,
            "scenarios/ae3lite/E120_ae3_recirc_dilute_overshoot_realhw.yaml",
        )

    def test_discover_by_suite_alias_supports_ae3_suites(self) -> None:
        discovered = self.suite.discover_scenarios(["ae3lite_v1", "ae3lite_realhw"])
        self.assert_contains_scenario(
            discovered,
            "scenarios/ae3lite/E95_ae3_start_cycle_done_completed.yaml",
        )
        self.assert_contains_scenario(
            discovered,
            "scenarios/ae3lite/E110_ae3_node_runtime_event_contract.yaml",
        )
        self.assert_contains_scenario(
            discovered,
            "scenarios/ae3lite/E108_ae3_soil_moisture_telemetry_contract.yaml",
        )
        self.assert_contains_scenario(
            discovered,
            "scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml",
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
            "ae3lite",
            "ae3lite_contract",
            "ae3lite_v1",
            "ae3lite_realhw",
            "ae3lite_testnode_realhw_core",
            "ae3lite_testnode_realhw_irrigation",
            "calibration_realhw",
            "scheduler",
            "automation_engine",
            "workflow",
            "prod_readiness_realhw",
        ]:
            self.assertIn(suite_name, choices)

    def test_full_suite_includes_canonical_ae3_and_sim_scenarios(self) -> None:
        scenarios = self.suite._get_suite_scenarios("full")
        self.assert_contains_scenario(
            scenarios,
            "scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml",
        )
        self.assert_contains_scenario(
            scenarios,
            "scenarios/ae3lite/E108_ae3_soil_moisture_telemetry_contract.yaml",
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
            any(
                Path(item).as_posix().endswith(
                    "scenarios/ae3lite/E106_debug_no_cleanup.yaml"
                )
                for item in scenarios
            ),
            msg=f"Debug scenario leaked into full suite: {scenarios}",
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
