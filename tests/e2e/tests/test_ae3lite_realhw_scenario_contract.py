#!/usr/bin/env python3
"""
Regression tests for AE3-Lite real-hardware scenario contract.
"""

import sys
import unittest
from pathlib import Path

import yaml


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

SCENARIO_PATH = E2E_ROOT / "scenarios" / "ae3lite" / "E100_ae3_two_tank_realhw_smoke.yaml"
READY_DURING_FILL_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E101_ae3_two_tank_realhw_ready_during_fill.yaml"
)
SETUP_READY_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E101_ae3_two_tank_realhw_setup_ready.yaml"
)
RETRY_LIMIT_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E102_ae3_recirculation_retry_limit_alert_reset_realhw.yaml"
)
READY_DURING_RECIRC_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E102_ae3_two_tank_realhw_ready_during_recirculation.yaml"
)
RETRY_LIMIT_RESOLVE_READY_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E103_ae3_recirculation_retry_limit_alert_resolve_ready_realhw.yaml"
)
HOT_RELOAD_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E104_ae3_two_tank_realhw_hot_reload_correction_config.yaml"
)
FAIL_CLOSED_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E105_ae3_two_tank_fail_closed_missing_command_plan_realhw.yaml"
)
PIGGYBACK_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E106_ae3_two_tank_realhw_piggyback_ec_ph_cycle.yaml"
)
START_IRRIGATION_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E107_ae3_irrigation_runtime_test_node.yaml"
)
SOIL_TELEMETRY_CONTRACT_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E108_ae3_irrigation_inline_correction_contract.yaml"
)
INLINE_CORRECTION_SCENARIO_PATH = (
    E2E_ROOT / "scenarios" / "ae3lite" / "E109_ae3_irrigation_inline_correction_test_node.yaml"
)
REALHW_CYCLE_START_SCENARIOS = [
    SCENARIO_PATH,
    READY_DURING_FILL_SCENARIO_PATH,
    SETUP_READY_SCENARIO_PATH,
    READY_DURING_RECIRC_SCENARIO_PATH,
    RETRY_LIMIT_SCENARIO_PATH,
    RETRY_LIMIT_RESOLVE_READY_SCENARIO_PATH,
    FAIL_CLOSED_SCENARIO_PATH,
    HOT_RELOAD_SCENARIO_PATH,
    PIGGYBACK_SCENARIO_PATH,
]
AE3_RUNTIME_DRAIN_SCENARIOS = [
    SCENARIO_PATH,
    READY_DURING_FILL_SCENARIO_PATH,
    SETUP_READY_SCENARIO_PATH,
    READY_DURING_RECIRC_SCENARIO_PATH,
    RETRY_LIMIT_SCENARIO_PATH,
    RETRY_LIMIT_RESOLVE_READY_SCENARIO_PATH,
    FAIL_CLOSED_SCENARIO_PATH,
    HOT_RELOAD_SCENARIO_PATH,
    PIGGYBACK_SCENARIO_PATH,
    START_IRRIGATION_SCENARIO_PATH,
    INLINE_CORRECTION_SCENARIO_PATH,
]
LOGIC_PROFILE_SCENARIOS = [
    SCENARIO_PATH,
    READY_DURING_FILL_SCENARIO_PATH,
    SETUP_READY_SCENARIO_PATH,
    READY_DURING_RECIRC_SCENARIO_PATH,
    RETRY_LIMIT_SCENARIO_PATH,
    RETRY_LIMIT_RESOLVE_READY_SCENARIO_PATH,
    HOT_RELOAD_SCENARIO_PATH,
    FAIL_CLOSED_SCENARIO_PATH,
    PIGGYBACK_SCENARIO_PATH,
    INLINE_CORRECTION_SCENARIO_PATH,
]
REALHW_SEEDED_TOPOLOGY_SCENARIOS = [
    SCENARIO_PATH,
    READY_DURING_FILL_SCENARIO_PATH,
    SETUP_READY_SCENARIO_PATH,
    READY_DURING_RECIRC_SCENARIO_PATH,
    RETRY_LIMIT_SCENARIO_PATH,
    RETRY_LIMIT_RESOLVE_READY_SCENARIO_PATH,
    HOT_RELOAD_SCENARIO_PATH,
    FAIL_CLOSED_SCENARIO_PATH,
    PIGGYBACK_SCENARIO_PATH,
]


class TestAe3LiteRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def test_waits_for_expected_startup_commands(self) -> None:
        step = self._find_step("actions", "wait_expected_ae_commands_published")

        self.assertEqual(step.get("type"), "db.wait")
        query = str(step.get("query") or "")
        for fragment in [
            "channel = 'storage_state'",
            "payload->>'cmd' = 'state'",
            "channel = 'valve_clean_fill'",
            "payload->>'cmd' = 'set_relay'",
            "payload->'params'->>'state'",
        ]:
            self.assertIn(fragment, query)

    def test_asserts_expected_startup_commands_logged(self) -> None:
        assertion_names = {item.get("name") for item in self.scenario.get("assertions", [])}

        self.assertIn("irr_state_probe_logged", assertion_names)
        self.assertIn("clean_fill_start_logged", assertion_names)

    def test_runtime_progress_step_uses_v2_task_columns(self) -> None:
        step = self._find_step("actions", "wait_task_requeued_clean_fill_check")
        assertion = next(
            item
            for item in self.scenario.get("assertions", [])
            if item.get("name") == "runtime_task_pending_clean_fill_check"
        )

        query = str(step.get("query") or "")
        self.assertIn("topology AS mode", query)
        self.assertIn("current_stage AS stage", query)
        self.assertNotIn("payload->>'ae3_cycle_start_mode'", query)
        self.assertNotIn("payload->>'ae3_cycle_start_stage'", query)

        condition = str(assertion.get("condition") or "")
        self.assertIn("two_tank_drip_substrate_trays", condition)
        self.assertNotIn("== 'two_tank'", condition)

    def test_restores_previous_zone_runtime_in_cleanup(self) -> None:
        set_zone_context = self._find_step("actions", "set_zone_context")
        restore_runtime = self._find_step("cleanup", "restore_previous_zone_runtime")

        self.assertEqual(
            set_zone_context.get("previous_automation_runtime"),
            "${zone_ctx.0.automation_runtime}",
        )
        self.assertEqual(
            restore_runtime.get("params", {}).get("automation_runtime"),
            "${previous_automation_runtime}",
        )
        self.assertIn(":automation_runtime", str(restore_runtime.get("query") or ""))

    def test_cleans_zone_workflow_state_in_cleanup(self) -> None:
        step = self._find_step("cleanup", "cleanup_zone_workflow_state_after_run")

        self.assertEqual(step.get("type"), "database_execute")
        query = str(step.get("query") or "")
        self.assertIn("DELETE FROM zone_workflow_state", query)
        self.assertIn("WHERE zone_id = :zone_id", query)

    def test_realhw_cycle_start_scenarios_do_not_use_irrigate_once_intent_type(self) -> None:
        for scenario_path in REALHW_CYCLE_START_SCENARIOS:
            text = scenario_path.read_text(encoding="utf-8")
            self.assertNotIn(
                "'IRRIGATE_ONCE'",
                text,
                msg=f"{scenario_path.name} still uses IRRIGATE_ONCE for start-cycle flow",
            )

    def test_runtime_cleanup_waits_for_idle_worker_before_deleting_zone_state(self) -> None:
        for scenario_path in AE3_RUNTIME_DRAIN_SCENARIOS:
            text = scenario_path.read_text(encoding="utf-8")
            self.assertIn(
                "wait_zone_ae_runtime_idle_before_cleanup",
                text,
                msg=f"{scenario_path.name} does not wait for runtime idle before cleanup",
            )
            self.assertIn("status IN ('pending', 'claimed', 'running', 'waiting_command')", text)
            self.assertIn("FROM ae_zone_leases", text)
            self.assertIn("FROM zone_automation_intents", text)

    def test_logic_profile_mutating_scenarios_cleanup_zone_logic_profile_document(self) -> None:
        for scenario_path in LOGIC_PROFILE_SCENARIOS:
            text = scenario_path.read_text(encoding="utf-8")
            self.assertIn("/api/automation-configs/zone/${zone_id}/zone.logic_profile", text)
            self.assertIn("DELETE FROM automation_config_documents", text)
            self.assertIn("namespace = 'zone.logic_profile'", text)

    def test_smart_irrigation_scenarios_do_not_upsert_nodes_or_sensors_manually(self) -> None:
        for scenario_path in [
            START_IRRIGATION_SCENARIO_PATH,
            SOIL_TELEMETRY_CONTRACT_SCENARIO_PATH,
        ]:
            text = scenario_path.read_text(encoding="utf-8")
            self.assertNotIn("INSERT INTO nodes", text, msg=f"{scenario_path.name} still inserts nodes directly")
            self.assertNotIn("INSERT INTO sensors", text, msg=f"{scenario_path.name} still inserts sensors directly")

    def test_smart_irrigation_contract_waits_for_canonical_sensor_ingest(self) -> None:
        text = SOIL_TELEMETRY_CONTRACT_SCENARIO_PATH.read_text(encoding="utf-8")
        self.assertIn("DELETE FROM telemetry_samples", text)
        self.assertIn("DELETE FROM telemetry_last", text)
        self.assertIn("JOIN telemetry_last tl ON tl.sensor_id = s.id", text)

    def test_smart_irrigation_scenarios_use_named_hardware_harness_steps(self) -> None:
        expectations = {
            START_IRRIGATION_SCENARIO_PATH: [
                "type: hardware_activate_sensor_mode",
                "type: hardware_reset_state",
                "type: hardware_set_fault_mode",
            ],
            SOIL_TELEMETRY_CONTRACT_SCENARIO_PATH: [
                "type: hardware_set_fault_mode",
            ],
            INLINE_CORRECTION_SCENARIO_PATH: [
                "type: hardware_activate_sensor_mode",
                "type: hardware_set_fault_mode",
            ],
        }

        for scenario_path, required_fragments in expectations.items():
            text = scenario_path.read_text(encoding="utf-8")
            self.assertNotIn("type: ae_test_hook", text, msg=f"{scenario_path.name} still uses raw ae_test_hook")
            for fragment in required_fragments:
                self.assertIn(fragment, text, msg=f"{scenario_path.name} missing {fragment}")

    def test_realhw_scenarios_use_seeded_topology_and_live_config_publish(self) -> None:
        for scenario_path in REALHW_SEEDED_TOPOLOGY_SCENARIOS:
            with self.subTest(path=scenario_path.name):
                text = scenario_path.read_text(encoding="utf-8")
                self.assertNotIn("INSERT INTO nodes", text)
                self.assertNotIn("INSERT INTO sensors", text)
                self.assertNotIn("upsert_irrig_channels", text)
                self.assertNotIn("delete_old_level_sensors", text)
                self.assertNotIn("insert_level_sensors", text)
                self.assertNotIn("cleanup_ph_ec_sensors", text)
                self.assertNotIn("insert_ph_ec_sensors", text)
                self.assertNotIn("upsert_sensor_mode_channels", text)
                self.assertIn("/api/nodes/${irrig_node_id}/config/publish", text)
                self.assertIn("/api/nodes/${ph_node_id}/config/publish", text)
                self.assertIn("/api/nodes/${ec_node_id}/config/publish", text)
                self.assertIn("wait_irrigation_level_sensors_registered", text)

class TestAe3LiteRetryLimitRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with RETRY_LIMIT_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def test_cleans_stale_runtime_intents_before_start_cycle(self) -> None:
        step = self._find_step("actions", "cleanup_zone_runtime_intents")

        self.assertEqual(step.get("type"), "database_execute")
        query = str(step.get("query") or "")
        self.assertIn("DELETE FROM zone_automation_intents", query)
        self.assertIn("WHERE zone_id = :zone_id", query)

    def test_second_run_primes_fresh_irr_snapshot_after_reset(self) -> None:
        probe_step = self._find_step("actions", "probe_state_after_reset_second_run")
        wait_probe_step = self._find_step("actions", "wait_probe_state_after_reset_second_run_done")
        snapshot_step = self._find_step("actions", "wait_runtime_irr_state_snapshot_after_reset_second_run")

        self.assertEqual(probe_step.get("type"), "ae_test_hook")
        command = probe_step.get("command") or {}
        self.assertEqual(command.get("channel"), "storage_state")
        self.assertEqual(command.get("cmd"), "state")

        self.assertEqual(wait_probe_step.get("type"), "db.wait")
        wait_probe_query = str(wait_probe_step.get("query") or "")
        self.assertIn("status = 'DONE'", wait_probe_query)

        self.assertEqual(snapshot_step.get("type"), "db.wait")
        snapshot_query = str(snapshot_step.get("query") or "")
        self.assertIn("type = 'IRR_STATE_SNAPSHOT'", snapshot_query)
        self.assertIn("created_at >= :probe_created_at", snapshot_query)
        for fragment in [
            "snapshot'->>'pump_main",
            "snapshot'->>'valve_clean_fill",
            "snapshot'->>'valve_clean_supply",
            "snapshot'->>'valve_solution_fill",
            "snapshot'->>'valve_solution_supply",
            "snapshot'->>'valve_irrigation",
        ]:
            self.assertIn(fragment, snapshot_query)

    def test_retry_limit_scenario_applies_fast_tank_recirc_overrides(self) -> None:
        step = self._find_step("actions", "apply_test_node_correction_preset")
        payload = (step.get("payload") or {}).get("payload") or {}
        phase_overrides = payload.get("phase_overrides") or {}
        tank_recirc = phase_overrides.get("tank_recirc") or {}
        retry_cfg = tank_recirc.get("retry") or {}
        timing_cfg = tank_recirc.get("timing") or {}

        self.assertEqual(retry_cfg.get("prepare_recirculation_timeout_sec"), 45)
        self.assertEqual(retry_cfg.get("prepare_recirculation_max_attempts"), 3)
        self.assertEqual(timing_cfg.get("stabilization_sec"), 10)

    def test_retry_limit_scenario_restores_targets_via_authority_api(self) -> None:
        restore_step = self._find_step("actions", "restore_normal_targets_after_first_failure")
        wait_step = self._find_step("actions", "wait_grow_cycle_bundle_restored_after_first_failure")

        self.assertEqual(restore_step.get("type"), "api_put")
        self.assertEqual(
            restore_step.get("endpoint"),
            "/api/automation-configs/grow_cycle/${grow_cycle_id}/cycle.phase_overrides",
        )
        self.assertEqual((restore_step.get("payload") or {}).get("payload"), {})

        self.assertEqual(wait_step.get("type"), "db.wait")
        self.assertIn("automation_effective_bundles", str(wait_step.get("query") or ""))

    def test_retry_limit_scenario_counts_any_recirc_correction_not_fixed_triplets(self) -> None:
        first_assertion = next(
            item
            for item in self.scenario.get("assertions", [])
            if item.get("name") == "first_recirc_commands_attempted_three_times"
        )
        second_assertion = next(
            item
            for item in self.scenario.get("assertions", [])
            if item.get("name") == "second_recirc_commands_attempted_three_times"
        )

        first_condition = str(first_assertion.get("condition") or "")
        second_condition = str(second_assertion.get("condition") or "")

        self.assertIn("recirc_ec_cnt", first_condition)
        self.assertIn("recirc_ph_cnt", first_condition)
        self.assertIn(">= 1", first_condition)
        self.assertNotIn(">= 3 and", first_condition)

        self.assertIn("recirc_ec_cnt", second_condition)
        self.assertIn("recirc_ph_cnt", second_condition)
        self.assertIn(">= 1", second_condition)
        self.assertNotIn(">= 3 and", second_condition)

    def test_retry_limit_second_run_waits_for_idle_before_cleanup(self) -> None:
        text = RETRY_LIMIT_SCENARIO_PATH.read_text(encoding="utf-8")
        self.assertIn("wait_zone_ae_runtime_idle_before_second_cleanup", text)


class TestAe3LiteReadyDuringFillRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with READY_DURING_FILL_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def test_post_fill_handoff_has_no_extra_correction_and_closes_cleanly(self) -> None:
        wait_force_step = self._find_step("actions", "wait_force_solution_tank_full_done")
        post_fill_step = self._find_step("actions", "load_post_fill_activity")
        stabilize_wait_step = self._find_step("actions", "wait_stabilize_ph_ec_done")
        stabilize_window_step = self._find_step("actions", "wait_stabilized_ph_ec_window")
        assertion = next(
            item
            for item in self.scenario.get("assertions", [])
            if item.get("name") == "post_fill_handoff_closed_without_extra_correction"
        )

        wait_force_query = str(wait_force_step.get("query") or "")
        self.assertIn("created_at", wait_force_query)
        self.assertEqual(wait_force_step.get("save"), "force_solution_tank_full_done_row")

        stabilize_wait_query = str(stabilize_wait_step.get("query") or "")
        stabilize_window_query = str(stabilize_window_step.get("query") or "")
        self.assertIn("created_at", stabilize_wait_query)
        self.assertEqual(stabilize_wait_step.get("save"), "stabilize_ph_ec_done_row")
        self.assertIn("tsamp.ts >= CAST(:after_stabilize_at AS timestamptz)", stabilize_window_query)
        self.assertEqual(
            stabilize_window_step.get("params", {}).get("after_stabilize_at"),
            "${stabilize_ph_ec_done_row.0.created_at}",
        )

        stabilize_window_query = str(stabilize_window_step.get("query") or "")
        self.assertIn("ph_samples", stabilize_window_query)
        self.assertIn("ec_samples", stabilize_window_query)
        self.assertIn("ABS(EXTRACT(EPOCH FROM (ph.ts - ec.ts))) <= 10", stabilize_window_query)
        self.assertIn("tsamp.value BETWEEN 6.88 AND 6.92", stabilize_window_query)
        self.assertIn("tsamp.value BETWEEN 0.64 AND 0.66", stabilize_window_query)
        self.assertNotIn("ph.cnt = 3", stabilize_window_query)
        self.assertNotIn("ec.cnt = 3", stabilize_window_query)

        self.assertEqual(post_fill_step.get("type"), "database_query")
        post_fill_query = str(post_fill_step.get("query") or "")
        self.assertIn("prepare_recirculation_start_cnt_after_full", post_fill_query)
        self.assertIn("prepare_recirculation_stop_cnt_after_full", post_fill_query)
        self.assertIn("correction_cmd_cnt_after_full", post_fill_query)
        self.assertIn("created_at >= CAST(:after_tank_full_at AS timestamptz)", post_fill_query)
        self.assertEqual(
            post_fill_step.get("params", {}).get("after_tank_full_at"),
            "${force_solution_tank_full_done_row.0.created_at}",
        )

        condition = str(assertion.get("condition") or "")
        self.assertIn("correction_cmd_cnt_after_full", condition)
        self.assertIn("prepare_recirculation_start_cnt_after_full", condition)
        self.assertIn("prepare_recirculation_stop_cnt_after_full", condition)


class TestAe3LiteRetryLimitResolveReadyRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with RETRY_LIMIT_RESOLVE_READY_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def test_second_run_primes_fresh_irr_snapshot_after_reset(self) -> None:
        probe_step = self._find_step("actions", "probe_state_after_reset_second_run")
        wait_probe_step = self._find_step("actions", "wait_probe_state_after_reset_second_run_done")
        snapshot_step = self._find_step("actions", "wait_runtime_irr_state_snapshot_after_reset_second_run")

        self.assertEqual(probe_step.get("type"), "ae_test_hook")
        command = probe_step.get("command") or {}
        self.assertEqual(command.get("channel"), "storage_state")
        self.assertEqual(command.get("cmd"), "state")

        self.assertEqual(wait_probe_step.get("type"), "db.wait")
        wait_probe_query = str(wait_probe_step.get("query") or "")
        self.assertIn("status = 'DONE'", wait_probe_query)

        self.assertEqual(snapshot_step.get("type"), "db.wait")
        snapshot_query = str(snapshot_step.get("query") or "")
        self.assertIn("type = 'IRR_STATE_SNAPSHOT'", snapshot_query)
        self.assertIn("created_at >= :probe_created_at", snapshot_query)
        for fragment in [
            "snapshot'->>'pump_main",
            "snapshot'->>'valve_clean_fill",
            "snapshot'->>'valve_clean_supply",
            "snapshot'->>'valve_solution_fill",
            "snapshot'->>'valve_solution_supply",
            "snapshot'->>'valve_irrigation",
        ]:
            self.assertIn(fragment, snapshot_query)

    def test_second_run_waits_for_idle_before_cleanup(self) -> None:
        text = RETRY_LIMIT_RESOLVE_READY_SCENARIO_PATH.read_text(encoding="utf-8")
        self.assertIn("wait_zone_ae_runtime_idle_before_second_cleanup", text)


class TestAe3LiteSetupReadyRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SETUP_READY_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def test_fill_and_recirc_ph_commands_are_optional_in_cold_start_setup_ready(self) -> None:
        fill_step = self._find_step("actions", "load_fill_ph_correction_commands_if_any")
        recirc_stage_step = self._find_step("actions", "wait_prepare_recirculation_stage")
        recirc_ph_step = self._find_step("actions", "load_recirculation_ph_correction_commands_if_any")

        self.assertEqual(fill_step.get("type"), "database_query")
        fill_query = str(fill_step.get("query") or "")
        self.assertIn("channel IN ('pump_acid', 'pump_base')", fill_query)
        self.assertNotIn("expected_rows", fill_step)

        recirc_stage_query = str(recirc_stage_step.get("query") or "")
        self.assertIn("updated_at AS stage_started_at", recirc_stage_query)

        recirc_ph_query = str(recirc_ph_step.get("query") or "")
        self.assertIn("created_at >= CAST(:after_stage_started_at AS timestamptz)", recirc_ph_query)
        self.assertIn("channel IN ('pump_acid', 'pump_base')", recirc_ph_query)
        self.assertNotIn("expected_rows", recirc_ph_step)
        self.assertEqual(
            recirc_ph_step.get("params", {}).get("after_command_id"),
            "${recirc_ec_correction_row.0.id}",
        )

    def test_process_observe_windows_match_default_real_hardware_contract(self) -> None:
        for step_name in [
            "apply_solution_fill_process_calibration",
            "apply_tank_recirc_process_calibration",
            "apply_irrigation_process_calibration",
        ]:
            step = self._find_step("actions", step_name)
            observe = (
                (step.get("payload") or {})
                .get("payload", {})
                .get("meta", {})
                .get("observe", {})
            )
            self.assertEqual(observe.get("telemetry_period_sec"), 2)
            self.assertEqual(observe.get("window_min_samples"), 3)
            self.assertEqual(observe.get("decision_window_sec"), 6)

    def test_ready_targets_wait_uses_phase_windows(self) -> None:
        step = self._find_step("actions", "wait_targets_reached_on_node")
        snapshot_step = self._find_step("actions", "load_task_snapshot_after_target_wait")
        snapshot_assertion = next(
            item
            for item in self.scenario.get("assertions", [])
            if item.get("name") == "task_snapshot_captured_before_cleanup"
        )
        completed_step = self._find_step("actions", "wait_task_completed")
        workflow_ready_step = self._find_step("actions", "wait_workflow_ready")
        targets_after_completion_step = self._find_step("actions", "load_targets_reached_from_samples")
        targets_assertion = next(
            item
            for item in self.scenario.get("assertions", [])
            if item.get("name") == "targets_reached_near_completion"
        )

        self.assertEqual(step.get("type"), "db.wait")
        self.assertTrue(step.get("optional"))
        query = str(step.get("query") or "")
        self.assertIn("ph.last_value BETWEEN 4.80 AND 5.20", query)
        self.assertIn("ec.last_value BETWEEN 2.20 AND 2.60", query)
        self.assertIn("'targets_reached'::text AS wait_outcome", query)
        self.assertIn("'task_failed'::text AS wait_outcome", query)
        self.assertIn("t.status = 'failed'", query)
        self.assertNotIn("OR EXISTS", query)
        self.assertNotIn("status = 'completed'", query)
        self.assertNotIn("ABS(ph.last_value - 5.0)", query)
        self.assertNotIn("ABS(ec.last_value - 2.4)", query)
        self.assertEqual(step.get("params", {}).get("task_id"), "${task_id}")
        self.assertEqual(float(step.get("timeout", 0.0)), 330.0)

        self.assertEqual(snapshot_step.get("type"), "database_query")
        snapshot_query = str(snapshot_step.get("query") or "")
        self.assertIn("SELECT", snapshot_query)
        self.assertIn("current_stage", snapshot_query)
        self.assertIn("error_code", snapshot_query)
        self.assertIn("error_message", snapshot_query)
        self.assertEqual(snapshot_step.get("params", {}).get("task_id"), "${task_id}")

        completed_query = str(completed_step.get("query") or "")
        self.assertIn("status = 'completed'", completed_query)
        self.assertEqual(float(completed_step.get("timeout", 0.0)), 1020.0)

        workflow_ready_query = str(workflow_ready_step.get("query") or "")
        self.assertIn("workflow_phase = 'ready'", workflow_ready_query)
        self.assertNotIn("task_failed", workflow_ready_query)

        targets_after_completion_query = str(targets_after_completion_step.get("query") or "")
        self.assertIn("completed_at", targets_after_completion_query)
        self.assertIn("telemetry_samples", targets_after_completion_query)
        self.assertEqual(
            targets_after_completion_step.get("params", {}).get("completed_at"),
            "${completed_task_row.0.completed_at}",
        )

        snapshot_condition = str(snapshot_assertion.get("condition") or "")
        self.assertIn("task_snapshot_after_target_wait_row", snapshot_condition)
        targets_condition = str(targets_assertion.get("condition") or "")
        self.assertIn("targets_reached_completed_row", targets_condition)

    def test_setup_ready_cleanup_removes_zone_workflow_state(self) -> None:
        step = self._find_step("cleanup", "cleanup_zone_workflow_state_after_run")

        self.assertEqual(step.get("type"), "database_execute")
        query = str(step.get("query") or "")
        self.assertIn("DELETE FROM zone_workflow_state", query)
        self.assertIn("WHERE zone_id = :zone_id", query)


class TestAe3LiteDoseCommandContract(unittest.TestCase):
    SCENARIO_PATHS = [
        READY_DURING_FILL_SCENARIO_PATH,
        SETUP_READY_SCENARIO_PATH,
        RETRY_LIMIT_SCENARIO_PATH,
        RETRY_LIMIT_RESOLVE_READY_SCENARIO_PATH,
        HOT_RELOAD_SCENARIO_PATH,
        PIGGYBACK_SCENARIO_PATH,
    ]

    def test_realhw_correction_scenarios_expect_canonical_dose_command(self) -> None:
        for path in self.SCENARIO_PATHS:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("payload->>'cmd' = 'run_pump'", text)
                self.assertIn("payload->>'cmd' = 'dose'", text)


class TestAe3LiteHotReloadRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with HOT_RELOAD_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def _find_assertion(self, name: str) -> dict:
        for item in self.scenario.get("assertions", []):
            if item.get("name") == name:
                return item
        self.fail(f"Assertion '{name}' is missing")

    def test_hot_reload_requires_targets_after_reconfiguration(self) -> None:
        recirc_stage_step = self._find_step("actions", "wait_prepare_recirculation_stage")
        recirc_ec_step = self._find_step("actions", "wait_recirculation_ec_correction_command")
        step = self._find_step("actions", "wait_targets_reached_on_node_after_hot_reload")
        assertion = self._find_assertion("targets_reached_after_hot_reload")
        hot_reload_step = self._find_step("actions", "hot_reload_correction_config")
        clamp_assertion = self._find_assertion("post_reload_command_is_clamped")

        recirc_stage_query = str(recirc_stage_step.get("query") or "")
        self.assertIn("current_stage = 'prepare_recirculation_check'", recirc_stage_query)
        self.assertIn("updated_at AS stage_started_at", recirc_stage_query)

        recirc_ec_query = str(recirc_ec_step.get("query") or "")
        self.assertIn("created_at >= CAST(:after_stage_started_at AS timestamptz)", recirc_ec_query)
        self.assertEqual(
            recirc_ec_step.get("params", {}).get("after_stage_started_at"),
            "${prepare_recirc_stage_row.0.stage_started_at}",
        )

        self.assertEqual(step.get("type"), "db.wait")
        query = str(step.get("query") or "")
        self.assertIn("ph.last_value BETWEEN 4.90 AND 5.15", query)
        self.assertIn("ec.last_value BETWEEN 2.30 AND 2.60", query)
        self.assertIn("ph.last_ts >= NOW() - INTERVAL '30 seconds'", query)
        self.assertNotIn("status IN ('pending', 'completed')", query)

        condition = str(assertion.get("condition") or "")
        self.assertIn("len(context.get('targets_reached_after_hot_reload_row', [])) == 1", condition)

        payload = (hot_reload_step.get("payload") or {}).get("payload") or {}
        phase_overrides = payload.get("phase_overrides") or {}
        solution_fill = phase_overrides.get("solution_fill") or {}
        tank_recirc = phase_overrides.get("tank_recirc") or {}

        self.assertEqual(((solution_fill.get("controllers") or {}).get("ec") or {}).get("kp"), 12.0)
        self.assertEqual(((solution_fill.get("controllers") or {}).get("ec") or {}).get("max_dose_ml"), 20.0)
        self.assertEqual(((solution_fill.get("controllers") or {}).get("ph") or {}).get("max_dose_ml"), 10.0)
        self.assertEqual(((solution_fill.get("dosing") or {}).get("max_ec_dose_ml")), 20.0)
        self.assertEqual(((solution_fill.get("dosing") or {}).get("max_ph_dose_ml")), 10.0)
        self.assertEqual(((tank_recirc.get("controllers") or {}).get("ec") or {}).get("min_interval_sec"), 15)
        self.assertEqual(((tank_recirc.get("controllers") or {}).get("ph") or {}).get("min_interval_sec"), 15)
        self.assertEqual(((tank_recirc.get("controllers") or {}).get("ec") or {}).get("max_dose_ml"), 30.0)
        self.assertEqual(((tank_recirc.get("controllers") or {}).get("ph") or {}).get("max_dose_ml"), 16.0)

        clamp_condition = str(clamp_assertion.get("condition") or "")
        self.assertIn("<= 30.0", clamp_condition)
        self.assertIn("<= 16.0", clamp_condition)

    def test_hot_reload_ack_uses_authority_document_and_current_api(self) -> None:
        wait_step = self._find_step("actions", "wait_hot_reload_apply_ack")
        get_step = self._find_step("actions", "get_zone_correction_config_after_hot_reload")

        self.assertEqual(wait_step.get("type"), "db.wait")
        wait_query = str(wait_step.get("query") or "")
        self.assertIn("FROM automation_config_documents acd", wait_query)
        self.assertIn("acd.namespace = 'zone.correction'", wait_query)
        self.assertIn("acd.scope_type = 'zone'", wait_query)
        self.assertIn("acd.payload->>'last_applied_version'", wait_query)
        self.assertIn("acd.payload->>'last_applied_at'", wait_query)
        self.assertNotIn("zone_correction_configs", wait_query)

        self.assertEqual(get_step.get("type"), "api_get")
        self.assertEqual(
            get_step.get("endpoint"),
            "/api/automation-configs/zone/${zone_id}/zone.correction",
        )


class TestAe3LiteFailClosedRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with FAIL_CLOSED_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_assertion(self, name: str) -> dict:
        for item in self.scenario.get("assertions", []):
            if item.get("name") == name:
                return item
        self.fail(f"Assertion '{name}' is missing")

    def test_fail_closed_expects_planner_validation_error_for_missing_channel(self) -> None:
        code_assertion = self._find_assertion("runtime_task_failed_with_planner_config_code")
        message_assertion = self._find_assertion("runtime_task_error_mentions_missing_required_channel")
        no_probe_assertion = self._find_assertion("startup_state_probe_not_written_before_fail_closed")

        code_condition = str(code_assertion.get("condition") or "")
        message_condition = str(message_assertion.get("condition") or "")
        no_probe_condition = str(no_probe_assertion.get("condition") or "")

        self.assertIn("ae3_task_execution_failed", code_condition)
        self.assertIn("clean_fill_start", message_condition)
        self.assertIn("missing required channels", message_condition)
        self.assertIn("valve_clean_fill", message_condition)
        self.assertIn("state_probe_cnt", no_probe_condition)
        self.assertIn("== 0", no_probe_condition)


class TestAe3LiteInlineCorrectionNodeSimScenarioContract(unittest.TestCase):
    def test_inline_irrigation_scenario_provisions_active_grow_cycle_bundle(self) -> None:
        text = INLINE_CORRECTION_SCENARIO_PATH.read_text(encoding="utf-8")

        for fragment in [
            "create_grow_cycle",
            "create_phase",
            "activate_grow_cycle",
            "/api/automation-configs/grow_cycle/${grow_cycle_id}/cycle.start_snapshot",
            "wait_grow_cycle_bundle_ready",
        ]:
            self.assertIn(fragment, text)

    def test_inline_irrigation_scenario_waits_for_dual_gap_decision_not_legacy_event(self) -> None:
        text = INLINE_CORRECTION_SCENARIO_PATH.read_text(encoding="utf-8")

        self.assertNotIn("IRRIGATION_CORRECTION_STARTED", text)
        self.assertNotIn("wait_zone_event", text)
        self.assertIn("wait_correction_decision_for_dual_gap", text)
        self.assertIn("type = 'CORRECTION_DECISION_MADE'", text)
        self.assertIn("details->>'selected_action' = 'ec'", text)
        self.assertIn("details->>'needs_ec' = 'true'", text)
        self.assertIn("details->>'needs_ph_down' = 'true'", text)
        self.assertIn("details->>'workflow_phase' IN ('irrigating', 'irrig_recirc')", text)

    def test_inline_irrigation_scenario_asserts_ec_dose_with_active_main_pump(self) -> None:
        text = INLINE_CORRECTION_SCENARIO_PATH.read_text(encoding="utf-8")

        self.assertIn("type = 'EC_DOSING'", text)
        self.assertIn("details->>'channel' = 'pump_a'", text)
        self.assertIn("wait_main_pump_snapshot_before_ec_dose", text)
        self.assertIn("type = 'IRR_STATE_SNAPSHOT'", text)
        self.assertIn("snapshot'->>'pump_main", text)
        self.assertIn("created_at <= CAST(:ec_dose_created_at AS timestamptz)", text)

    def test_inline_irrigation_scenario_asserts_ec_first_for_dual_gap(self) -> None:
        text = INLINE_CORRECTION_SCENARIO_PATH.read_text(encoding="utf-8")

        self.assertIn("inline_correction_decision_keeps_dual_gap_and_ec_first", text)
        self.assertIn("decision_reason", text)
        self.assertIn("ec_first_in_window", text)
        self.assertIn("needs_ph_down", text)
        self.assertNotIn("wait_ph_dose_command_during_irrigation", text)


class TestAe3LitePiggybackRealHwScenarioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with PIGGYBACK_SCENARIO_PATH.open("r", encoding="utf-8") as fh:
            cls.scenario = yaml.safe_load(fh)

    def _find_step(self, section: str, step_name: str) -> dict:
        for item in self.scenario.get(section, []):
            if item.get("step") == step_name:
                return item
        self.fail(f"Step '{step_name}' is missing in section '{section}'")

    def test_seeds_recirculation_solution_before_piggyback_waits(self) -> None:
        seed_step = self._find_step("actions", "seed_recirculation_sensor_values")
        seed_wait_step = self._find_step("actions", "wait_seeded_recirculation_telemetry")
        recirc_ec_step = self._find_step("actions", "wait_recirculation_ec_correction_command")
        recirc_ph_step = self._find_step("actions", "wait_recirculation_ph_correction_command")

        seed_command = seed_step.get("command") or {}
        seed_params = seed_command.get("params") or {}
        self.assertEqual(seed_command.get("channel"), "storage_state")
        self.assertEqual(seed_command.get("cmd"), "set_fault_mode")
        self.assertEqual(seed_params.get("ph_value"), 5.68)
        self.assertEqual(seed_params.get("ec_value"), 1.92)

        seed_wait_query = str(seed_wait_step.get("query") or "")
        self.assertIn("ph.last_value BETWEEN 5.63 AND 5.73", seed_wait_query)
        self.assertIn("ec.last_value BETWEEN 1.87 AND 1.97", seed_wait_query)

        recirc_ec_query = str(recirc_ec_step.get("query") or "")
        recirc_ph_query = str(recirc_ph_step.get("query") or "")
        self.assertIn("created_at >= CAST(:after_seeded_at AS timestamptz)", recirc_ec_query)
        self.assertIn("created_at >= CAST(:after_seeded_at AS timestamptz)", recirc_ph_query)
        self.assertEqual(
            recirc_ec_step.get("params", {}).get("after_seeded_at"),
            "${seed_recirculation_command_row.0.created_at}",
        )
        self.assertEqual(
            recirc_ph_step.get("params", {}).get("after_seeded_at"),
            "${seed_recirculation_command_row.0.created_at}",
        )


if __name__ == "__main__":
    unittest.main()
