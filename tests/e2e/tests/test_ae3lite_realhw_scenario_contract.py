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


if __name__ == "__main__":
    unittest.main()
