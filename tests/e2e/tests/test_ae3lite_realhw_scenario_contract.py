#!/usr/bin/env python3
"""
Regression tests for AE3-Lite real-hardware scenario contract.
"""

import sys
import unittest
from pathlib import Path

import yaml


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

SCENARIO_PATH = E2E_ROOT / "scenarios" / "ae3lite" / "E100_ae3_two_tank_realhw_smoke.yaml"
SETUP_READY_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E101_ae3_two_tank_realhw_setup_ready.yaml"
)
RETRY_LIMIT_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E102_ae3_recirculation_retry_limit_alert_reset_realhw.yaml"
)
RETRY_LIMIT_RESOLVE_READY_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E103_ae3_recirculation_retry_limit_alert_resolve_ready_realhw.yaml"
)


class TestAe3LiteRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def test_waits_for_expected_startup_commands(self) -> None:
        step = self._find_step("actions", "wait_expected_ae_commands_published")

        self.assertEqual(step.get("type"), "db.wait")
        query = str(step.get("query") or "")
        for fragment in [
            "channel = 'storage_state'",
            "payload->>'cmd' = 'state'",
            "channel = 'valve_clean_fill'",
            "payload->>'cmd' = 'set_relay'",
            "payload->'params'->>'state'",
        ]:
            self.assertIn(fragment, query)

    def test_asserts_expected_startup_commands_logged(self) -> None:
        assertion_names = {item.get("name") for item in self.scenario.get("assertions", [])}

        self.assertIn("irr_state_probe_logged", assertion_names)
        self.assertIn("clean_fill_start_logged", assertion_names)

    def test_runtime_progress_step_uses_v2_task_columns(self) -> None:
        step = self._find_step("actions", "wait_task_requeued_clean_fill_check")
        assertion = next(
            item
            for item in self.scenario.get("assertions", [])
            if item.get("name") == "runtime_task_pending_clean_fill_check"
        )

        query = str(step.get("query") or "")
        self.assertIn("topology AS mode", query)
        self.assertIn("current_stage AS stage", query)
        self.assertNotIn("payload->>'ae3_cycle_start_mode'", query)
        self.assertNotIn("payload->>'ae3_cycle_start_stage'", query)

        condition = str(assertion.get("condition") or "")
        self.assertIn("two_tank_drip_substrate_trays", condition)
        self.assertNotIn("== 'two_tank'", condition)

    def test_restores_previous_zone_runtime_in_cleanup(self) -> None:
        set_zone_context = self._find_step("actions", "set_zone_context")
        restore_runtime = self._find_step("cleanup", "restore_previous_zone_runtime")

        self.assertEqual(
            set_zone_context.get("previous_automation_runtime"),
            "${zone_ctx.0.automation_runtime}",
        )
        self.assertEqual(
            restore_runtime.get("params", {}).get("automation_runtime"),
            "${previous_automation_runtime}",
        )
        self.assertNotIn("'ae2'", str(restore_runtime.get("query") or ""))

    def test_cleans_zone_workflow_state_in_cleanup(self) -> None:
        step = self._find_step("cleanup", "cleanup_zone_workflow_state_after_run")

        self.assertEqual(step.get("type"), "database_execute")
        query = str(step.get("query") or "")
        self.assertIn("DELETE FROM zone_workflow_state", query)
        self.assertIn("WHERE zone_id = :zone_id", query)

class TestAe3LiteRetryLimitRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with RETRY_LIMIT_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def test_cleans_stale_runtime_intents_before_start_cycle(self) -> None:
        step = self._find_step("actions", "cleanup_zone_runtime_intents")

        self.assertEqual(step.get("type"), "database_execute")
        query = str(step.get("query") or "")
        self.assertIn("DELETE FROM zone_automation_intents", query)
        self.assertIn("WHERE zone_id = :zone_id", query)

    def test_second_run_primes_fresh_irr_snapshot_after_reset(self) -> None:
        probe_step = self._find_step("actions", "probe_state_after_reset_second_run")
        wait_probe_step = self._find_step("actions", "wait_probe_state_after_reset_second_run_done")
        snapshot_step = self._find_step("actions", "wait_runtime_irr_state_snapshot_after_reset_second_run")

        self.assertEqual(probe_step.get("type"), "ae_test_hook")
        command = probe_step.get("command") or {}
        self.assertEqual(command.get("channel"), "storage_state")
        self.assertEqual(command.get("cmd"), "state")

        self.assertEqual(wait_probe_step.get("type"), "db.wait")
        wait_probe_query = str(wait_probe_step.get("query") or "")
        self.assertIn("status = 'DONE'", wait_probe_query)

        self.assertEqual(snapshot_step.get("type"), "db.wait")
        snapshot_query = str(snapshot_step.get("query") or "")
        self.assertIn("type = 'IRR_STATE_SNAPSHOT'", snapshot_query)
        self.assertIn("created_at >= :probe_created_at", snapshot_query)
        for fragment in [
            "snapshot'->>'pump_main",
            "snapshot'->>'valve_clean_fill",
            "snapshot'->>'valve_clean_supply",
            "snapshot'->>'valve_solution_fill",
            "snapshot'->>'valve_solution_supply",
            "snapshot'->>'valve_irrigation",
        ]:
            self.assertIn(fragment, snapshot_query)


class TestAe3LiteRetryLimitResolveReadyRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with RETRY_LIMIT_RESOLVE_READY_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def test_second_run_primes_fresh_irr_snapshot_after_reset(self) -> None:
        probe_step = self._find_step("actions", "probe_state_after_reset_second_run")
        wait_probe_step = self._find_step("actions", "wait_probe_state_after_reset_second_run_done")
        snapshot_step = self._find_step("actions", "wait_runtime_irr_state_snapshot_after_reset_second_run")

        self.assertEqual(probe_step.get("type"), "ae_test_hook")
        command = probe_step.get("command") or {}
        self.assertEqual(command.get("channel"), "storage_state")
        self.assertEqual(command.get("cmd"), "state")

        self.assertEqual(wait_probe_step.get("type"), "db.wait")
        wait_probe_query = str(wait_probe_step.get("query") or "")
        self.assertIn("status = 'DONE'", wait_probe_query)

        self.assertEqual(snapshot_step.get("type"), "db.wait")
        snapshot_query = str(snapshot_step.get("query") or "")
        self.assertIn("type = 'IRR_STATE_SNAPSHOT'", snapshot_query)
        self.assertIn("created_at >= :probe_created_at", snapshot_query)
        for fragment in [
            "snapshot'->>'pump_main",
            "snapshot'->>'valve_clean_fill",
            "snapshot'->>'valve_clean_supply",
            "snapshot'->>'valve_solution_fill",
            "snapshot'->>'valve_solution_supply",
            "snapshot'->>'valve_irrigation",
        ]:
            self.assertIn(fragment, snapshot_query)


class TestAe3LiteSetupReadyRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SETUP_READY_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def test_ready_targets_wait_uses_phase_windows(self) -> None:
        step = self._find_step("actions", "wait_targets_reached_on_node")

        self.assertEqual(step.get("type"), "db.wait")
        query = str(step.get("query") or "")
        self.assertIn("ph.last_value BETWEEN 4.80 AND 5.20", query)
        self.assertIn("ec.last_value BETWEEN 2.20 AND 2.60", query)
        self.assertNotIn("ABS(ph.last_value - 5.0)", query)
        self.assertNotIn("ABS(ec.last_value - 2.4)", query)


if __name__ == "__main__":
    unittest.main()
