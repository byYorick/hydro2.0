#!/usr/bin/env python3
"""
Regression tests for cleanup condition handling in E2E runner.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from runner.e2e_runner import E2ERunner  # noqa: E402
from runner.schema.variables import VariableResolver  # noqa: E402


class TestE2ERunnerCleanupConditions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runner = E2ERunner()
        self.runner.context["zone_id"] = 1
        self.runner.variable_resolver = VariableResolver(self.runner.context)
        self.runner._ensure_test_zone_and_node = AsyncMock()
        self.runner.reporter.add_artifacts = lambda *args, **kwargs: None
        self.runner.reporter.generate_all = lambda: {}

    async def test_cleanup_step_skipped_when_condition_false(self) -> None:
        self.runner._execute_action_step = AsyncMock()
        self.runner.context["missing_flag"] = 0

        scenario = {
            "actions": [],
            "assertions": [],
            "cleanup": [
                {
                    "step": "dangerous_cleanup",
                    "type": "database_execute",
                    "query": "DELETE FROM zones WHERE id = :zone_id",
                    "params": {"zone_id": "${zone_id}"},
                    "condition": "${missing_flag == 1}",
                }
            ],
        }

        result = await self.runner._run_actions_scenario(scenario, "cleanup_condition_false")

        self.assertTrue(result)
        self.runner._execute_action_step.assert_not_awaited()

    async def test_cleanup_unknown_condition_variable_raises(self) -> None:
        scenario = {
            "actions": [],
            "assertions": [],
            "cleanup": [
                {
                    "step": "dangerous_cleanup",
                    "type": "database_execute",
                    "query": "DELETE FROM zones WHERE id = :zone_id",
                    "params": {"zone_id": "${zone_id}"},
                    "condition": "${undefined_flag == 1}",
                }
            ],
        }

        with self.assertRaises(ValueError):
            await self.runner._run_actions_scenario(scenario, "cleanup_condition_unknown_variable")

    async def test_cleanup_step_runs_and_strips_meta_fields(self) -> None:
        self.runner.context["run_cleanup"] = 1
        captured = {}

        async def fake_execute(step_type, cfg, raw):
            captured["step_type"] = step_type
            captured["cfg"] = cfg
            captured["raw"] = raw

        self.runner._execute_action_step = AsyncMock(side_effect=fake_execute)

        scenario = {
            "actions": [],
            "assertions": [],
            "cleanup": [
                {
                    "step": "safe_cleanup",
                    "type": "set",
                    "value": "ok",
                    "optional": True,
                    "condition": "${run_cleanup == 1}",
                }
            ],
        }

        result = await self.runner._run_actions_scenario(scenario, "cleanup_condition_true")

        self.assertTrue(result)
        self.runner._execute_action_step.assert_awaited_once()
        self.assertEqual(captured["step_type"], "set")
        self.assertEqual(captured["cfg"].get("value"), "ok")
        self.assertNotIn("optional", captured["cfg"])
        self.assertNotIn("condition", captured["cfg"])


if __name__ == "__main__":
    unittest.main()
