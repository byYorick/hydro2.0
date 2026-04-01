#!/usr/bin/env python3
"""
Contract tests for the smart-irrigation E2E launcher.
"""

import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "run_smart_irrigation_pipeline.sh"


class TestSmartIrrigationLauncherContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_launcher_enables_smart_irrigation_seed_profile(self) -> None:
        self.assertIn('HYDRO_SEED_PROFILE="${HYDRO_SEED_PROFILE:-smart-irrigation}"', self.script)
        self.assertIn("docker-compose.e2e.yml", self.script)

    def test_launcher_runs_canonical_smart_irrigation_pipeline_scenarios(self) -> None:
        for scenario_name in [
            "E108_ae3_irrigation_inline_correction_contract.yaml",
            "E107_ae3_start_irrigation_api_smoke.yaml",
            "E109_ae3_irrigation_inline_correction_node_sim.yaml",
        ]:
            self.assertIn(scenario_name, self.script)


if __name__ == "__main__":
    unittest.main()
