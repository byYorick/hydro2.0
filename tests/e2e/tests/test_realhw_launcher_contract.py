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
        self.assertIn('AE4_REALHW_SCENARIOS=(', self.script)
        self.assertIn(
            '"scenarios/ae4/AE4_HW_01_test_node_planned_shot.yaml"',
            self.script,
        )
        self.assertIn(
            '"scenarios/ae4/AE4_HW_02_test_node_both_tanks_empty.yaml"',
            self.script,
        )
        self.assertNotIn("AE3LITE_SCENARIOS=(", self.script)
        self.assertNotIn("scenarios/ae3lite/", self.script)
        self.assertNotIn("SMART_IRRIGATION_SCENARIOS=(", self.script)
        self.assertNotIn("INLINE_IRRIGATION_SCENARIOS=(", self.script)
        self.assertNotIn("AUTOMATION_SCENARIOS=(", self.script)
        self.assertNotIn("WORKFLOW_SCENARIOS=(", self.script)
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
        self.assertIn("--set=<ae4|calibration|full>", self.script)

    def test_real_hardware_launcher_cleans_stale_blocking_ae3_alerts(self) -> None:
        self.assertIn("Удаляю stale AE3 blocking alerts для тестовой зоны", self.script)
        self.assertIn("DELETE FROM alerts", self.script)
        self.assertIn("'biz_zone_correction_config_missing'", self.script)
        self.assertIn("'biz_zone_dosing_calibration_missing'", self.script)

    def test_real_hardware_launcher_cleans_harness_noise_alerts_between_scenarios(self) -> None:
        self.assertIn("cleanup_zone_harness_noise_alerts()", self.script)
        helper = self.script.split("cleanup_zone_harness_noise_alerts() {")[1].split(
            "echo \"🚀 Запуск E2E на реальном железе"
        )[0]
        for code in (
            "infra_telemetry_invalid_timestamp",
            "infra_telemetry_zone_not_found",
            "infra_telemetry_node_not_found",
            "ae3_api_http_5xx",
            "biz_flow_stop_failed_hardware_may_be_active",
            "biz_ae3_task_failed",
        ):
            self.assertIn(f"'{code}'", helper)
        self.assertIn("zone_id IN (SELECT id FROM z)", helper)
        self.assertIn("zone_id IS NULL", helper)
        self.assertIn("UPPER(COALESCE(status, '')) = 'ACTIVE'", helper)
        null_zone_block = helper.split("zone_id IS NULL")[1]
        self.assertNotIn("'biz_ae3_task_failed'", null_zone_block)
        self.assertNotIn("'biz_flow_stop_failed_hardware_may_be_active'", null_zone_block)

        prepare_fn = self.script.split("prepare_real_hardware_node() {")[1].split(
            "cleanup_zone_harness_noise_alerts() {"
        )[0]
        self.assertIn("Удаляю ложные infra alerts после controlled node re-registration", prepare_fn)
        self.assertIn("cleanup_zone_harness_noise_alerts", prepare_fn)
        self.assertNotIn(
            "DELETE FROM alerts\n    WHERE code IN (\n      'infra_telemetry_node_not_found'",
            prepare_fn,
        )

        force_fn = self.script.split("force_cleanup_zone_ae_runtime() {")[1].split(
            "for scenario in"
        )[0]
        self.assertIn("cleanup_zone_harness_noise_alerts", force_fn)

    def test_real_hardware_launcher_cleans_harness_alert_noise(self) -> None:
        self.assertIn("Удаляю ложные infra alerts после controlled node re-registration", self.script)
        self.assertIn("cleanup_zone_harness_noise_alerts()", self.script)
        self.assertIn("'infra_telemetry_invalid_timestamp'", self.script)
        self.assertIn("'infra_telemetry_zone_not_found'", self.script)
        self.assertIn("'infra_telemetry_node_not_found'", self.script)
        self.assertIn("'biz_flow_stop_failed_hardware_may_be_active'", self.script)
        self.assertIn("'biz_ae3_task_failed'", self.script)
        helper = self.script.split("cleanup_zone_harness_noise_alerts() {", 1)[1].split("\n}", 1)[0]
        self.assertIn("zone_id IN (SELECT id FROM z)", helper)
        self.assertIn("'biz_flow_stop_failed_hardware_may_be_active'", helper)
        self.assertIn("'biz_ae3_task_failed'", helper)
        self.assertNotIn("DELETE FROM alerts;", helper)

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
