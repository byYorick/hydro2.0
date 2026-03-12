#!/usr/bin/env python3
"""
Regression tests for AE3-Lite real-hardware cleanup contract.
"""

import sys
import unittest
from pathlib import Path

import yaml


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

SCENARIO_DIR = E2E_ROOT / "scenarios" / "ae3lite"


class TestAe3LiteRealHwCleanupContract(unittest.TestCase):
    def _load_scenario(self, path: Path) -> dict:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def test_realhw_cleanup_keeps_reset_state_but_does_not_delete_commands(self) -> None:
        scenario_paths = sorted(SCENARIO_DIR.glob("E10*_realhw*.yaml"))
        self.assertTrue(scenario_paths, "No AE3-Lite real-hardware scenarios found")

        for path in scenario_paths:
            with self.subTest(path=path.name):
                scenario = self._load_scenario(path)
                cleanup_steps = scenario.get("cleanup", [])
                cleanup_names = {step.get("step") for step in cleanup_steps}

                self.assertIn("reset_test_node_after_run", cleanup_names)
                self.assertNotIn("cleanup_runtime_commands", cleanup_names)


if __name__ == "__main__":
    unittest.main()
