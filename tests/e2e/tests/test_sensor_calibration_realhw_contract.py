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
FORCE_INVALID_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "calibration" / "E111_sensor_calibration_realhw_force_invalid.yaml"
)
HAPPY_PATH_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "calibration" / "E117_sensor_calibration_realhw_happy_path.yaml"
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


class TestSensorCalibrationForceInvalidRealHwContract(_ScenarioMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with FORCE_INVALID_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def test_publishes_calibrate_via_ae_test_hook_with_force_invalid(self) -> None:
        ph_step = self._find_step("actions", "publish_ph_force_invalid_calibrate")
        ec_step = self._find_step("actions", "publish_ec_force_invalid_calibrate")

        for step, channel, value_key in (
            (ph_step, "ph_sensor", "known_ph"),
            (ec_step, "ec_sensor", "tds_value"),
        ):
            self.assertEqual(step.get("type"), "ae_test_hook")
            self.assertEqual(step.get("action"), "publish_command")
            command = step.get("command") or {}
            self.assertEqual(command.get("channel"), channel)
            self.assertEqual(command.get("cmd"), "calibrate")
            params = command.get("params") or {}
            self.assertTrue(params.get("force_invalid") is True)
            self.assertIn(value_key, params)

    def test_does_not_create_laravel_calibration_session(self) -> None:
        action_types = [item.get("type") for item in self.scenario.get("actions", [])]
        self.assertNotIn("api_post", action_types)

        for item in self.scenario.get("actions", []):
            endpoint = str(item.get("endpoint") or "")
            self.assertNotIn("sensor-calibrations", endpoint)

    def test_waits_for_terminal_invalid_commands(self) -> None:
        ph_step = self._find_step("actions", "wait_ph_command_invalid")
        ec_step = self._find_step("actions", "wait_ec_command_invalid")

        for step in (ph_step, ec_step):
            self.assertEqual(step.get("type"), "db.wait")
            query = str(step.get("query") or "")
            self.assertIn("FROM commands", query)
            self.assertIn("status = 'INVALID'", query)

    def test_asserts_invalid_terminal_for_both_sensors(self) -> None:
        assertion_names = {item.get("name") for item in self.scenario.get("assertions", [])}

        self.assertIn("ph_command_terminal_invalid_on_ph_sensor", assertion_names)
        self.assertIn("ec_command_terminal_invalid_on_ec_sensor", assertion_names)


class TestSensorCalibrationHappyPathRealHwContract(_ScenarioMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with HAPPY_PATH_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def test_submits_ph_points_via_calibration_api(self) -> None:
        create_step = self._find_step("actions", "create_ph_calibration")
        point_1 = self._find_step("actions", "submit_ph_point_1")
        point_2 = self._find_step("actions", "submit_ph_point_2")

        self.assertEqual(create_step.get("type"), "api_post")
        self.assertIn("/sensor-calibrations", str(create_step.get("endpoint") or ""))

        self.assertEqual(point_1.get("type"), "api_post")
        self.assertEqual((point_1.get("payload") or {}).get("stage"), 1)
        self.assertEqual((point_1.get("payload") or {}).get("reference_value"), 4.01)

        self.assertEqual(point_2.get("type"), "api_post")
        self.assertEqual((point_2.get("payload") or {}).get("stage"), 2)
        self.assertEqual((point_2.get("payload") or {}).get("reference_value"), 7.0)

    def test_waits_for_point_command_done(self) -> None:
        for step_name in ("wait_ph_point_1_command_done", "wait_ph_point_2_command_done"):
            step = self._find_step("actions", step_name)
            self.assertEqual(step.get("type"), "db.wait")
            query = str(step.get("query") or "")
            self.assertIn("FROM commands", query)
            self.assertIn("status = 'DONE'", query)

    def test_waits_for_completed_after_config_report(self) -> None:
        awaiting_step = self._find_step("actions", "wait_ph_point_2_awaiting_or_completed")
        completed_step = self._find_step("actions", "wait_ph_calibration_completed")

        awaiting_query = str(awaiting_step.get("query") or "")
        self.assertIn("point_2_pending", awaiting_query)
        self.assertIn("awaiting_config_report", awaiting_query)
        self.assertIn("completed", awaiting_query)

        self.assertEqual(completed_step.get("type"), "db.wait")
        completed_query = str(completed_step.get("query") or "")
        self.assertIn("status = 'completed'", completed_query)
        self.assertEqual(int(completed_step.get("timeout") or 0), 90)

    def test_asserts_status_api_last_calibrated(self) -> None:
        assertion_names = {item.get("name") for item in self.scenario.get("assertions", [])}
        self.assertIn("calibration_reaches_completed", assertion_names)
        self.assertIn("status_api_shows_last_calibrated_for_ph", assertion_names)

    def test_cleanup_cancels_non_terminal_sessions(self) -> None:
        cleanup_step = self._find_step("cleanup", "cancel_non_terminal_sensor_calibrations")
        self.assertEqual(cleanup_step.get("type"), "database_execute")
        query = str(cleanup_step.get("query") or "")
        self.assertIn("UPDATE sensor_calibrations", query)
        self.assertIn("status NOT IN ('completed', 'failed', 'cancelled')", query)


if __name__ == "__main__":
    unittest.main()
