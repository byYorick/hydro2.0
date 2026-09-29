#!/usr/bin/env python3
"""Контракт формы YAML-сценариев AE4 (волны 2+)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from runner.scenario_loader import load_scenario_file

AE4_SCENARIO_DIR = E2E_ROOT / "scenarios" / "ae4"

REQUIRED_WAVE2 = {
    "E219": "E219_ae4_probe_command_not_done.yaml",
    "E238": "E238_ae4_exception_failure_report.yaml",
    "E239": "E239_ae4_non_done_zone_state_message.yaml",
    "E240": "E240_ae4_alert_publish_failure_keeps_text.yaml",
}

REQUIRED_WAVE3 = {
    "E218": "E218_ae4_estop_from_zone_events.yaml",
    "E221": "E221_ae4_feed_only_no_drain_return.yaml",
}

REQUIRED_WAVE4 = {
    "E205": "E205_ae4_stale_ec_no_dose.yaml",
}

NODE_SIM_SCENARIOS = {
    "AE4_SIM_01": "AE4_SIM_01_node_sim_planned_shot.yaml",
    "AE4_SIM_02": "AE4_SIM_02_node_sim_both_tanks_empty.yaml",
}


class Ae4ScenarioContractTest(unittest.TestCase):
    def _assert_scenario_form(self, scenario_id: str, filename: str, wave: int) -> None:
        path = AE4_SCENARIO_DIR / filename
        self.assertTrue(path.is_file(), f"нет файла {filename}")
        scenario = load_scenario_file(path)
        self.assertTrue(str(scenario.get("name") or "").strip())
        self.assertTrue(str(scenario.get("description") or "").strip())
        meta = scenario.get("meta") or {}
        self.assertIsInstance(meta, dict)
        self.assertEqual(str(meta.get("id")), scenario_id)
        self.assertEqual(int(meta.get("wave")), wave)
        self.assertEqual(str(meta.get("runtime")), "ae4")
        self.assertFalse(bool(meta.get("requires_physical_node")))
        self.assertTrue(str(meta.get("proves") or "").strip())
        actions = scenario.get("actions")
        self.assertIsInstance(actions, list)
        self.assertGreaterEqual(len(actions), 1)
        blob = path.read_text(encoding="utf-8").lower()
        self.assertNotIn("cmd: irrigation_start", blob)
        self.assertNotIn('cmd: "irrigation_start"', blob)

    def test_wave2_scenarios_exist_and_have_form(self) -> None:
        self.assertTrue(AE4_SCENARIO_DIR.is_dir(), "нет каталога scenarios/ae4")
        for scenario_id, filename in REQUIRED_WAVE2.items():
            self._assert_scenario_form(scenario_id, filename, 2)

    def test_wave3_scenarios_exist_and_have_form(self) -> None:
        self.assertTrue(AE4_SCENARIO_DIR.is_dir(), "нет каталога scenarios/ae4")
        for scenario_id, filename in REQUIRED_WAVE3.items():
            self._assert_scenario_form(scenario_id, filename, 3)

    def test_node_sim_scenarios_drive_mqtt(self) -> None:
        for scenario_id, filename in NODE_SIM_SCENARIOS.items():
            path = AE4_SCENARIO_DIR / filename
            self.assertTrue(path.is_file(), f"нет файла {filename}")
            scenario = load_scenario_file(path)
            meta = scenario.get("meta") or {}
            self.assertEqual(str(meta.get("id")), scenario_id)
            self.assertEqual(str(meta.get("runtime")), "ae4")
            self.assertFalse(bool(meta.get("requires_physical_node")))
            types = [str(action.get("type")) for action in scenario.get("actions") or []]
            self.assertIn("start_simulator", types)
            self.assertIn("mqtt_publish", types)
            blob = path.read_text(encoding="utf-8")
            self.assertNotIn("document_contract", blob)
            self.assertIn("hydro/gh-ae4-sim/", blob)

    def test_realhw_scenarios_use_test_node_fault_mode(self) -> None:
        for scenario_id, filename in {
            "AE4_HW_01": "AE4_HW_01_test_node_planned_shot.yaml",
            "AE4_HW_02": "AE4_HW_02_test_node_both_tanks_empty.yaml",
        }.items():
            path = AE4_SCENARIO_DIR / filename
            scenario = load_scenario_file(path)
            meta = scenario.get("meta") or {}
            self.assertEqual(str(meta.get("id")), scenario_id)
            self.assertTrue(bool(meta.get("requires_physical_node")))
            types = [str(action.get("type")) for action in scenario.get("actions") or []]
            self.assertIn("hardware_set_fault_mode", types)
            self.assertNotIn("start_simulator", types)
            blob = path.read_text(encoding="utf-8")
            self.assertIn("storage_state", blob)
            self.assertIn("automation_runtime = 'ae4'", blob)
            self.assertNotIn("start-cycle", blob)

    def test_wave4_scenarios_exist_and_have_form(self) -> None:
        self.assertTrue(AE4_SCENARIO_DIR.is_dir(), "нет каталога scenarios/ae4")
        for scenario_id, filename in REQUIRED_WAVE4.items():
            self._assert_scenario_form(scenario_id, filename, 4)


if __name__ == "__main__":
    unittest.main()
