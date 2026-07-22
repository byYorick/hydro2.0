#!/usr/bin/env python3
"""Contract stubs for sequential nutrient E118–E121 scenarios.

These YAML files are status=stub / skip_live and must NOT appear in realhw suites.
They pin expected events, forbidden phases, and config keys until dedicated live
realhw paths exist (or remain covered by E104/E106/E107/E109 fragments).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

STUBS = {
    "E118": E2E_ROOT / "scenarios" / "ae3lite" / "E118_ae3_water_baseline_and_ca_fill_test_node.yaml",
    "E119": E2E_ROOT / "scenarios" / "ae3lite" / "E119_ae3_prepare_pipeline_sequence_test_node.yaml",
    "E120": E2E_ROOT / "scenarios" / "ae3lite" / "E120_ae3_recirc_dilute_overshoot_test_node.yaml",
    "E121": E2E_ROOT / "scenarios" / "ae3lite" / "E121_ae3_irrigation_ph_only_no_recovery_test_node.yaml",
}

FORBIDDEN_SHARED = (
    "irrig_recirc",
    "irrigation_recovery",
    "npk_ec_share",
)

EXPECTED_EVENTS_BY_STUB = {
    "E118": ("WATER_BASELINE_CAPTURED", "PIPELINE_STEP_CHANGED", "CORRECTION"),
    "E119": ("PIPELINE_STEP_CHANGED", "CORRECTION", "RECIRC_DILUTE_STARTED", "RECIRC_DILUTE_COMPLETED"),
    "E120": ("RECIRC_DILUTE_STARTED", "RECIRC_DILUTE_COMPLETED", "PIPELINE_STEP_CHANGED", "CORRECTION"),
    "E121": ("CORRECTION", "CORRECTION_DECISION_MADE"),
}


def _stub_context(data: dict) -> dict:
    for item in data.get("actions") or []:
        if item.get("step") == "set_stub_context":
            return item
    raise AssertionError("set_stub_context action missing")


class TestAe3LiteSequentialNutrientStubContract(unittest.TestCase):
    def test_stub_files_exist_and_mark_stub(self) -> None:
        for key, path in STUBS.items():
            self.assertTrue(path.exists(), msg=f"{key} missing: {path}")
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(data.get("status"), "stub", msg=f"{key} status must be stub")
            ctx = _stub_context(data)
            self.assertTrue(ctx.get("stub") is True)
            self.assertTrue(ctx.get("skip_live") is True)
            self.assertEqual(ctx.get("status"), "stub")
            self.assertTrue(
                ctx.get("forbidden_irrigation_ec_dose") is True,
                msg=f"{key} must set forbidden_irrigation_ec_dose",
            )

    def test_stubs_not_in_realhw_suite_catalog(self) -> None:
        suite_py = (E2E_ROOT / "runner" / "suite.py").read_text(encoding="utf-8")
        launcher = (E2E_ROOT / "run_automation_engine_real_hardware.sh").read_text(encoding="utf-8")
        for key, path in STUBS.items():
            name = path.name
            self.assertNotIn(
                name,
                suite_py,
                msg=f"{key} must not be listed in runner/suite.py realhw suites",
            )
            self.assertNotIn(
                name,
                launcher,
                msg=f"{key} must not be listed in realhw launcher",
            )

    def test_all_stubs_share_forbidden_canon(self) -> None:
        for key, path in STUBS.items():
            text = path.read_text(encoding="utf-8")
            for fragment in FORBIDDEN_SHARED:
                self.assertIn(fragment, text, msg=f"{key} missing forbidden fragment {fragment}")
            self.assertIn("pump_b", text, msg=f"{key} must document Ca=pump_b")
            ctx = _stub_context(yaml.safe_load(text))
            forbidden_owners = ctx.get("forbidden_prepare_owners") or []
            self.assertIn("npk_ec_share", forbidden_owners)
            self.assertIn("target_ec_prepare", forbidden_owners)

    def test_expected_events_documented(self) -> None:
        for key, events in EXPECTED_EVENTS_BY_STUB.items():
            ctx = _stub_context(yaml.safe_load(STUBS[key].read_text(encoding="utf-8")))
            documented = ctx.get("expected_events") or []
            for event in events:
                self.assertIn(event, documented, msg=f"{key} missing expected event {event}")

    def test_e118_documents_calcium_fill(self) -> None:
        data = yaml.safe_load(STUBS["E118"].read_text(encoding="utf-8"))
        ctx = _stub_context(data)
        self.assertEqual(ctx.get("expected_fill_channel"), "pump_b")
        self.assertEqual(ctx.get("expected_active_component"), "calcium")
        self.assertEqual(ctx.get("calcium_actuator"), "pump_b")
        self.assertIn("WATER_BASELINE_CAPTURED", ctx.get("expected_events") or [])
        assertion_names = {item.get("name") for item in data.get("assertions") or []}
        self.assertIn("stub_expects_water_baseline_event", assertion_names)
        self.assertIn("stub_forbids_irrig_recirc_and_npk_prepare_owner", assertion_names)

    def test_e119_documents_pipeline_order(self) -> None:
        data = yaml.safe_load(STUBS["E119"].read_text(encoding="utf-8"))
        ctx = _stub_context(data)
        self.assertEqual(
            ctx.get("pipeline_steps"),
            ["calcium", "ph", "magnesium", "ph", "npk", "ph", "micro", "ph_final"],
        )
        actuators = ctx.get("actuators") or {}
        self.assertEqual(actuators.get("calcium"), "pump_b")
        self.assertEqual(actuators.get("npk"), "pump_a")
        self.assertIn("PIPELINE_STEP_CHANGED", ctx.get("expected_events") or [])

    def test_e120_documents_dilute_fields(self) -> None:
        data = yaml.safe_load(STUBS["E120"].read_text(encoding="utf-8"))
        ctx = _stub_context(data)
        self.assertEqual(ctx.get("dilute_channel"), "valve_clean_supply")
        self.assertEqual(ctx.get("calcium_actuator"), "pump_b")
        recirc = ctx.get("recirc") or {}
        self.assertEqual(recirc.get("ec_overshoot_dilute_pct"), 15)
        self.assertEqual(recirc.get("dilute_pulse_sec"), 10)
        self.assertEqual(recirc.get("dilute_max_attempts"), 3)
        self.assertEqual(recirc.get("dilute_settle_sec"), 30)
        events = ctx.get("expected_events") or []
        self.assertIn("RECIRC_DILUTE_STARTED", events)
        self.assertIn("RECIRC_DILUTE_COMPLETED", events)
        text = STUBS["E120"].read_text(encoding="utf-8")
        self.assertIn("ec_overshoot_dilute_pct", text)
        self.assertIn("dilute_pulse_sec", text)
        self.assertIn("dilute_max_attempts", text)
        self.assertIn("dilute_settle_sec", text)

    def test_e121_forbids_irrig_recirc_and_recovery(self) -> None:
        data = yaml.safe_load(STUBS["E121"].read_text(encoding="utf-8"))
        ctx = _stub_context(data)
        self.assertIs(ctx.get("needs_ec"), False)
        self.assertEqual(ctx.get("expected_terminal_phase"), "ready")
        self.assertEqual(ctx.get("expected_stop_transition"), "stop_to_ready")
        self.assertIn("irrig_recirc", ctx.get("forbidden_workflow_phases") or [])
        for stage in ("irrigation_recovery", "irrigation_recovery_check", "irrigation_recovery_start"):
            self.assertIn(stage, ctx.get("forbidden_stages") or [])
        self.assertEqual(set(ctx.get("allowed_dose_channels") or []), {"pump_acid", "pump_base"})
        self.assertIn("pump_a", ctx.get("forbidden_dose_channels") or [])
        assertion_names = {item.get("name") for item in data.get("assertions") or []}
        self.assertIn("stub_irrigation_is_ph_only", assertion_names)
        self.assertIn("stub_stop_goes_to_ready", assertion_names)


if __name__ == "__main__":
    unittest.main()
