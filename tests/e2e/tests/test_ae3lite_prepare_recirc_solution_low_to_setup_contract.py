#!/usr/bin/env python3
"""Contract checks for E113 prepare_recirc solution_low → setup realhw scenario."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

SCENARIO_PATH = (
    E2E_ROOT
    / "scenarios"
    / "ae3lite"
    / "E113_ae3_prepare_recirc_solution_low_to_setup_realhw.yaml"
)


class TestAe3PrepareRecircSolutionLowToSetupContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SCENARIO_PATH.open(encoding="utf-8") as fh:
            cls.doc = yaml.safe_load(fh)

    def _steps(self) -> list[dict]:
        return list(self.doc.get("actions") or [])

    def _find_step(self, name: str) -> dict:
        for step in self._steps():
            if step.get("step") == name:
                return step
        self.fail(f"step '{name}' not found in {SCENARIO_PATH.name}")

    def test_scenario_name_and_path(self) -> None:
        self.assertEqual(self.doc.get("name"), "E113_ae3_prepare_recirc_solution_low_to_setup_realhw")
        self.assertTrue(SCENARIO_PATH.is_file())

    def test_reaches_prepare_then_triggers_solution_min_low(self) -> None:
        prepare = self._find_step("wait_prepare_recirculation_stage")
        self.assertIn("prepare_recirculation_check", prepare.get("query") or "")

        trigger = self._find_step("trigger_solution_min_depleted_during_prepare")
        self.assertEqual(trigger.get("type"), "ae_test_hook")
        params = ((trigger.get("command") or {}).get("params") or {})
        self.assertIs(params.get("level_solution_min_override"), False)

    def test_expects_setup_restart_not_terminal_fail(self) -> None:
        setup = self._find_step("wait_setup_restart_after_solution_low")
        query = setup.get("query") or ""
        self.assertIn("startup", query)
        self.assertIn("solution_fill", query)

        assertions = {a.get("name"): a for a in (self.doc.get("assertions") or [])}
        self.assertIn("task_did_not_terminal_fail_on_solution_low", assertions)
        fail_q = assertions["task_did_not_terminal_fail_on_solution_low"].get("query") or ""
        self.assertIn("recirculation_solution_low", fail_q)

    def test_clears_no_effect_block(self) -> None:
        step = self._find_step("assert_no_effect_block_cleared")
        self.assertIn("no_effect_count", step.get("query") or "")
        assertions = {a.get("name"): a for a in (self.doc.get("assertions") or [])}
        self.assertIn("no_effect_block_cleared_or_absent", assertions)


if __name__ == "__main__":
    unittest.main()
