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
        self.assertIn('SCENARIO_SET="${SCENARIO_SET:-smart_irrigation}"', self.script)
        self.assertIn("run_automation_engine_real_hardware.sh", self.script)

    def test_launcher_delegates_to_real_hardware_harness(self) -> None:
        self.assertIn('exec "$REAL_HW_LAUNCHER" "$@"', self.script)
        self.assertNotIn("-m runner.suite", self.script)


if __name__ == "__main__":
    unittest.main()
