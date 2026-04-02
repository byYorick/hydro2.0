#!/usr/bin/env python3
"""
Regression tests for sensor calibration real-hardware scenario contracts.
"""

import sys
import unittest
from pathlib import Path

import yaml


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

CREATE_CANCEL_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "calibration" / "E110_sensor_calibration_realhw_create_cancel.yaml"
)
UNSUPPORTED_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "calibration" / "E111_sensor_calibration_realhw_unsupported_command.yaml"
)


class _ScenarioMixin:
    scenario: dict

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")


class TestSensorCalibrationCreateCancelRealHwContract(_ScenarioMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with CREATE_CANCEL_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def test_uses_realhw_calibration_api_surface(self) -> None:
        create_step = self._find_step("actions", "create_ph_calibration")
        status_step = self._find_step("actions", "fetch_status_with_active_session")
        cancel_step = self._find_step("actions", "cancel_ph_calibration")

        self.assertEqual(create_step.get("type"), "api_post")
        self.assertIn("/api/zones/${zone_id}/sensor-calibrations", str(create_step.get("endpoint") or ""))

        self.assertEqual(status_step.get("type"), "api_get")
        self.assertIn("/sensor-calibrations/status", str(status_step.get("endpoint") or ""))

        self.assertEqual(cancel_step.get("type"), "api_post")
        self.assertIn("/cancel", str(cancel_step.get("endpoint") or ""))

    def test_waits_for_cancelled_terminal_state_in_db(self) -> None:
        wait_step = self._find_step("actions", "wait_ph_calibration_cancelled")

        self.assertEqual(wait_step.get("type"), "db.wait")
        query = str(wait_step.get("query") or "")
        self.assertIn("status = 'cancelled'", query)
        self.assertIn("completed_at IS NOT NULL", query)

    def test_cleanup_cancels_non_terminal_sessions(self) -> None:
        cleanup_step = self._find_step("cleanup", "cancel_non_terminal_sensor_calibrations")

        self.assertEqual(cleanup_step.get("type"), "database_execute")
        query = str(cleanup_step.get("query") or "")
        self.assertIn("UPDATE sensor_calibrations", query)
        self.assertIn("status NOT IN ('completed', 'failed', 'cancelled')", query)


class TestSensorCalibrationPointSubmissionRealHwContract(_ScenarioMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with UNSUPPORTED_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def test_waits_for_terminal_invalid_commands(self) -> None:
        ph_step = self._find_step("actions", "wait_ph_command_terminal")
        ec_step = self._find_step("actions", "wait_ec_command_terminal")

        for step in (ph_step, ec_step):
            self.assertEqual(step.get("type"), "db.wait")
            query = str(step.get("query") or "")
            self.assertIn("FROM commands", query)
            self.assertIn("status = 'INVALID'", query)

    def test_waits_for_failed_calibration_sessions_after_invalid_terminal(self) -> None:
        ph_step = self._find_step("actions", "wait_ph_calibration_failed")
        ec_step = self._find_step("actions", "wait_ec_calibration_failed")

        for step in (ph_step, ec_step):
            self.assertEqual(step.get("type"), "db.wait")
            query = str(step.get("query") or "")
            self.assertIn("FROM sensor_calibrations", query)
            self.assertIn("status = 'failed'", query)
            self.assertIn("point_1_result = 'INVALID'", query)
            self.assertIn("completed_at IS NOT NULL", query)

    def test_asserts_calibrate_command_contract_for_both_sensors(self) -> None:
        assertion_names = {item.get("name") for item in self.scenario.get("assertions", [])}

        self.assertIn("ph_command_terminal_uses_calibrate_on_ph_sensor", assertion_names)
        self.assertIn("ec_command_terminal_uses_calibrate_on_ec_sensor", assertion_names)
        self.assertIn("ph_history_contains_failed_session", assertion_names)
        self.assertIn("ec_history_contains_failed_session", assertion_names)


if __name__ == "__main__":
    unittest.main()
