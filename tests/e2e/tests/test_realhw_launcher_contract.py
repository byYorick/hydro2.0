#!/usr/bin/env python3
"""
Contract tests for the real-hardware E2E launcher.
"""

import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "run_automation_engine_real_hardware.sh"
)


class TestRealHardwareLauncherContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_real_hardware_launcher_disables_node_sim_sessions(self) -> None:
        self.assertIn(': "${REAL_HW_USE_NODE_SIM_SESSION:=0}"', self.script)
        self.assertIn("REAL_HW_USE_NODE_SIM_SESSION=0", self.script)
        self.assertIn(
            "real-hardware harness работает только с реальной test_node без node-sim",
            self.script,
        )

    def test_real_hardware_launcher_stops_node_sim_noise_services(self) -> None:
        self.assertIn("for service in node-sim-workflow node-sim-manager; do", self.script)
        self.assertIn("real-hardware harness видел только реальную test_node", self.script)

    def test_real_hardware_launcher_exposes_calibration_suite(self) -> None:
        self.assertIn('CALIBRATION_SCENARIOS=(', self.script)
        self.assertIn(
            '"scenarios/calibration/E110_sensor_calibration_realhw_create_cancel.yaml"',
            self.script,
        )
        self.assertIn(
            '"scenarios/calibration/E111_sensor_calibration_realhw_unsupported_command.yaml"',
            self.script,
        )
        self.assertIn("--set=<automation|workflow|ae3lite|calibration|full>", self.script)


if __name__ == "__main__":
    unittest.main()
