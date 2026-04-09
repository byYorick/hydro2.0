#!/usr/bin/env python3
"""
Regression tests for AE3 node runtime event contract scenario.
"""

import sys
import unittest
from pathlib import Path

import yaml


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

SCENARIO_PATH = E2E_ROOT / "scenarios" / "ae3lite" / "E110_ae3_node_runtime_event_contract.yaml"


class TestAe3LiteNodeRuntimeEventScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def _find_assertion(self, assertion_name: str) -> dict:
        for item in self.scenario.get("assertions", []):
            if item.get("name") == assertion_name:
                return item
        self.fail(f"Assertion '{assertion_name}' is missing")

    def test_publishes_both_channel_and_storage_state_events(self) -> None:
        level_event = self._find_step("actions", "publish_level_switch_event")
        low_event = self._find_step("actions", "publish_irrigation_solution_low_event")

        self.assertEqual(level_event.get("type"), "mqtt_publish")
        self.assertIn("/level_solution_min/event", str(level_event.get("topic") or ""))
        self.assertEqual((level_event.get("payload") or {}).get("event_code"), "level_switch_changed")
        self.assertEqual((level_event.get("payload") or {}).get("channel"), "level_solution_min")

        self.assertEqual(low_event.get("type"), "mqtt_publish")
        self.assertIn("/storage_state/event", str(low_event.get("topic") or ""))
        self.assertEqual((low_event.get("payload") or {}).get("event_code"), "irrigation_solution_low")

    def test_waits_for_normalized_zone_events_in_database(self) -> None:
        level_wait = self._find_step("actions", "wait_level_switch_zone_event")
        low_wait = self._find_step("actions", "wait_irrigation_solution_low_zone_event")

        level_query = str(level_wait.get("query") or "")
        self.assertEqual(level_wait.get("type"), "db.wait")
        self.assertIn("type = 'LEVEL_SWITCH_CHANGED'", level_query)
        self.assertIn("payload_json->>'channel' = 'level_solution_min'", level_query)

        low_query = str(low_wait.get("query") or "")
        self.assertEqual(low_wait.get("type"), "db.wait")
        self.assertIn("type = 'IRRIGATION_SOLUTION_LOW'", low_query)
        self.assertIn("payload_json->'snapshot'->>'solution_level_min'", low_query)

    def test_checks_metrics_and_zone_state_timeline(self) -> None:
        metrics_step = self._find_step("actions", "fetch_ae_metrics")
        state_step = self._find_step("actions", "fetch_zone_state")
        metrics_assert = self._find_assertion("ae_metrics_include_node_runtime_kick_counter")
        level_assert = self._find_assertion("zone_state_timeline_contains_level_switch_event")
        low_assert = self._find_assertion("zone_state_timeline_contains_irrigation_low_event")

        self.assertEqual(metrics_step.get("type"), "http_request")
        self.assertEqual(str(metrics_step.get("method") or "").upper(), "GET")
        self.assertIn("/metrics/", str(metrics_step.get("url") or ""))

        self.assertEqual(state_step.get("type"), "api_get")
        self.assertIn("/api/zones/${zone_id}/state", str(state_step.get("endpoint") or ""))

        metrics_condition = str(metrics_assert.get("condition") or "")
        self.assertIn("ae3_node_runtime_event_kick_total", metrics_condition)
        self.assertIn("LEVEL_SWITCH_CHANGED", metrics_condition)
        self.assertIn("level_solution_min", metrics_condition)

        self.assertIn("LEVEL_SWITCH_CHANGED", str(level_assert.get("condition") or ""))
        self.assertIn("IRRIGATION_SOLUTION_LOW", str(low_assert.get("condition") or ""))

    def test_restores_zone_runtime_and_cleans_runtime_events(self) -> None:
        restore_runtime = self._find_step("cleanup", "restore_previous_zone_runtime")
        cleanup_events = self._find_step("cleanup", "cleanup_runtime_events")

        self.assertEqual(restore_runtime.get("type"), "database_execute")
        self.assertIn("SET automation_runtime = :automation_runtime", str(restore_runtime.get("query") or ""))
        self.assertEqual(restore_runtime.get("params", {}).get("automation_runtime"), "${previous_automation_runtime}")

        cleanup_query = str(cleanup_events.get("query") or "")
        self.assertEqual(cleanup_events.get("type"), "database_execute")
        self.assertIn("type IN ('LEVEL_SWITCH_CHANGED', 'IRRIGATION_SOLUTION_LOW')", cleanup_query)


if __name__ == "__main__":
    unittest.main()
