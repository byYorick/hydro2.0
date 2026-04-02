#!/usr/bin/env python3
"""
Regression tests for named hardware harness steps in E2E runner.
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


class TestE2ERunnerHardwareSteps(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runner = E2ERunner()
        self.runner.context.update(
            {
                "zone_id": 42,
                "test_node_uid": "nd-test-irrig-1",
                "test_ph_node_uid": "nd-test-ph-1",
            }
        )
        self.runner.variable_resolver = VariableResolver(self.runner.context)

    async def test_hardware_reset_state_uses_storage_state_channel(self) -> None:
        self.runner._publish_history_logger_command = AsyncMock(return_value={"status": "ok"})

        await self.runner._execute_action_step(
            "hardware_reset_state",
            {
                "zone_id": "${zone_id}",
                "node_uid": "${test_node_uid}",
            },
            {},
        )

        self.runner._publish_history_logger_command.assert_awaited_once()
        _, payload = self.runner._publish_history_logger_command.await_args.args[:2]
        self.assertEqual(payload["node_uid"], "nd-test-irrig-1")
        self.assertEqual(payload["channel"], "storage_state")
        self.assertEqual(payload["cmd"], "reset_state")
        self.assertEqual(payload["params"], {})

    async def test_hardware_activate_sensor_mode_defaults_to_system_channel(self) -> None:
        self.runner._publish_history_logger_command = AsyncMock(return_value={"status": "ok"})

        await self.runner._execute_action_step(
            "hardware_activate_sensor_mode",
            {
                "zone_id": "${zone_id}",
                "node_uid": "${test_ph_node_uid}",
                "save": "sensor_mode_response",
            },
            {},
        )

        _, payload = self.runner._publish_history_logger_command.await_args.args[:2]
        self.assertEqual(payload["channel"], "system")
        self.assertEqual(payload["cmd"], "activate_sensor_mode")
        self.assertEqual(payload["params"], {})

    async def test_hardware_set_fault_mode_respects_channel_override_and_params(self) -> None:
        self.runner._publish_history_logger_command = AsyncMock(return_value={"status": "ok"})

        await self.runner._execute_action_step(
            "hardware_set_fault_mode",
            {
                "zone_id": "${zone_id}",
                "node_uid": "${test_node_uid}",
                "channel": "storage_state",
                "params": {
                    "ph_value": 6.9,
                    "ec_value": 0.6,
                },
            },
            {},
        )

        _, payload = self.runner._publish_history_logger_command.await_args.args[:2]
        self.assertEqual(payload["channel"], "storage_state")
        self.assertEqual(payload["cmd"], "set_fault_mode")
        self.assertEqual(payload["params"]["ph_value"], 6.9)
        self.assertEqual(payload["params"]["ec_value"], 0.6)


if __name__ == "__main__":
    unittest.main()
