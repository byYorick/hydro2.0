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

    def test_real_hardware_launcher_exposes_canonical_suites(self) -> None:
        self.assertIn('AE3LITE_SCENARIOS=(', self.script)
        self.assertIn(
            '"scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml"',
            self.script,
        )
        self.assertIn(
            '"scenarios/ae3lite/E101_ae3_two_tank_realhw_setup_ready.yaml"',
            self.script,
        )
        self.assertIn(
            '"scenarios/ae3lite/E103_ae3_recirculation_retry_limit_alert_resolve_ready_realhw.yaml"',
            self.script,
        )
        self.assertIn(
            '"scenarios/ae3lite/E114_ae3_reactive_solution_topup_level_switch_realhw.yaml"',
            self.script,
        )
        self.assertIn(
            '"scenarios/ae3lite/E115_ae3_solution_change_operator_gate_realhw.yaml"',
            self.script,
        )
        self.assertIn(
            '"scenarios/ae3lite/E116_ae3_estop_failsafe_events_realhw.yaml"',
            self.script,
        )
        self.assertNotIn("E102_ae3_two_tank_realhw_ready_during_recirculation", self.script)
        self.assertNotIn("E102_ae3_recirculation_retry_limit_alert_reset", self.script)
        self.assertNotIn("AUTOMATION_SCENARIOS=(", self.script)
        self.assertNotIn("WORKFLOW_SCENARIOS=(", self.script)

        self.assertIn('SMART_IRRIGATION_SCENARIOS=(', self.script)
        self.assertIn(
            '"scenarios/ae3lite/E107_ae3_irrigation_runtime_test_node.yaml"',
            self.script,
        )
        self.assertIn(
            '"scenarios/ae3lite/E108_ae3_soil_moisture_telemetry_contract.yaml"',
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
            '"scenarios/calibration/E111_sensor_calibration_realhw_force_invalid.yaml"',
            self.script,
        )
        self.assertIn(
            '"scenarios/calibration/E117_sensor_calibration_realhw_happy_path.yaml"',
            self.script,
        )
        self.assertIn('INLINE_IRRIGATION_SCENARIOS=(', self.script)
        # Inline set is only the real inline-correction scenario (soil contract lives in smart_irrigation).
        inline_block = self.script.split("INLINE_IRRIGATION_SCENARIOS=(")[1].split(")")[0]
        self.assertIn(
            '"scenarios/ae3lite/E109_ae3_irrigation_inline_correction_test_node.yaml"',
            inline_block,
        )
        self.assertNotIn("E108_ae3_soil_moisture_telemetry_contract", inline_block)
        self.assertIn(
            "--set=<ae3lite|smart_irrigation|inline_irrigation|calibration|full>",
            self.script,
        )

    def test_real_hardware_launcher_cleans_stale_blocking_ae3_alerts(self) -> None:
        self.assertIn("Удаляю stale AE3 blocking alerts для тестовой зоны", self.script)
        self.assertIn("DELETE FROM alerts", self.script)
        self.assertIn("'biz_zone_correction_config_missing'", self.script)
        self.assertIn("'biz_zone_dosing_calibration_missing'", self.script)

    def test_real_hardware_launcher_suppresses_expected_psql_notice_noise(self) -> None:
        self.assertIn("client_min_messages=warning", self.script)
        self.assertIn("psql -qX", self.script)

    def test_real_hardware_launcher_prints_runtime_audit_summary(self) -> None:
        self.assertIn("runtime_event_counts_window=", self.script)
        self.assertIn("runtime_event_schema_version_missing_window=", self.script)
        self.assertIn("runtime_event_schema_versions_window=", self.script)
        self.assertIn("irrigation_snapshot_causality_gaps_window=", self.script)
        self.assertIn("alerts_new_window=", self.script)
        self.assertIn("alerts_new_codes_window=", self.script)
        self.assertIn("alerts_open_codes_total=", self.script)


if __name__ == "__main__":
    unittest.main()
