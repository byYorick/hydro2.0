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
        self.assertIn(
            "for service in node-sim node-sim-workflow node-sim-test-node node-sim-manager; do",
            self.script,
        )
        self.assertIn("real-hardware harness видел только реальную test_node", self.script)

    def test_real_hardware_launcher_exposes_calibration_suite(self) -> None:
        self.assertIn('SMART_IRRIGATION_SCENARIOS=(', self.script)
        self.assertIn(
            '"scenarios/ae3lite/E107_ae3_irrigation_runtime_test_node.yaml"',
            self.script,
        )
        self.assertIn(
            '"scenarios/ae3lite/E109_ae3_irrigation_inline_correction_test_node.yaml"',
            self.script,
        )
        self.assertIn('CALIBRATION_SCENARIOS=(', self.script)
        self.assertIn(
            '"scenarios/calibration/E110_sensor_calibration_realhw_create_cancel.yaml"',
            self.script,
        )
        self.assertIn(
            '"scenarios/calibration/E111_sensor_calibration_realhw_unsupported_command.yaml"',
            self.script,
        )
        self.assertIn("--set=<automation|workflow|ae3lite|smart_irrigation|calibration|full>", self.script)

    def test_real_hardware_launcher_cleans_stale_blocking_ae3_alerts(self) -> None:
        self.assertIn("Удаляю stale AE3 blocking alerts для тестовой зоны", self.script)
        self.assertIn("DELETE FROM alerts", self.script)
        self.assertIn("'biz_zone_correction_config_missing'", self.script)
        self.assertIn("'biz_zone_dosing_calibration_missing'", self.script)

    def test_real_hardware_launcher_suppresses_expected_psql_notice_noise(self) -> None:
        self.assertIn("client_min_messages=warning", self.script)
        self.assertIn("psql -qX", self.script)


if __name__ == "__main__":
    unittest.main()
