"""Tests for workflow_topology: TopologyRegistry and TWO_TANK graph."""

import pytest

from ae3lite.application.services.workflow_topology import (
    StageDef,
    TopologyRegistry,
    TWO_TANK,
)


@pytest.fixture
def registry() -> TopologyRegistry:
    return TopologyRegistry()


class TestTwoTankGraphIntegrity:
    """Validates that the TWO_TANK graph has no broken links."""

    def test_validate_two_tank_no_errors(self, registry: TopologyRegistry):
        errors = registry.validate("two_tank")
        assert errors == [], f"Graph validation errors: {errors}"

    def test_validate_canonical_alias_no_errors(self, registry: TopologyRegistry):
        errors = registry.validate("two_tank_drip_substrate_trays")
        assert errors == []

    def test_all_stage_keys_match_sdef_name(self):
        for key, sdef in TWO_TANK.items():
            assert key == sdef.name, (
                f"Key {key!r} doesn't match StageDef.name {sdef.name!r}"
            )

    def test_startup_stage_exists(self):
        assert "startup" in TWO_TANK

    def test_complete_ready_stage_exists(self):
        assert "complete_ready" in TWO_TANK

    def test_no_terminal_with_next_stage(self):
        for name, sdef in TWO_TANK.items():
            if sdef.terminal_error:
                assert sdef.next_stage is None, (
                    f"Stage {name} has terminal_error AND next_stage"
                )

    def test_correction_stages_have_both_branches(self):
        for name, sdef in TWO_TANK.items():
            if sdef.has_correction:
                assert sdef.on_corr_success, (
                    f"Stage {name} has_correction but no on_corr_success"
                )
                assert sdef.on_corr_fail, (
                    f"Stage {name} has_correction but no on_corr_fail"
                )

    def test_all_next_stage_refs_exist(self):
        for name, sdef in TWO_TANK.items():
            if sdef.next_stage:
                assert sdef.next_stage in TWO_TANK, (
                    f"Stage {name} -> next_stage {sdef.next_stage!r} not found"
                )

    def test_all_corr_refs_exist(self):
        for name, sdef in TWO_TANK.items():
            if sdef.on_corr_success:
                assert sdef.on_corr_success in TWO_TANK, (
                    f"Stage {name} -> on_corr_success {sdef.on_corr_success!r} not found"
                )
            if sdef.on_corr_fail:
                assert sdef.on_corr_fail in TWO_TANK, (
                    f"Stage {name} -> on_corr_fail {sdef.on_corr_fail!r} not found"
                )

    def test_expected_stage_count(self):
        assert len(TWO_TANK) == 33, (
            f"Expected 33 stages, got {len(TWO_TANK)}"
        )


class TestTopologyRegistryLookup:
    """Tests for get/stages/has_topology methods."""

    def test_get_known_stage(self, registry: TopologyRegistry):
        sdef = registry.get("two_tank", "startup")
        assert sdef.name == "startup"
        assert sdef.handler == "startup"

    def test_get_command_stage(self, registry: TopologyRegistry):
        sdef = registry.get("two_tank", "clean_fill_start")
        assert sdef.handler == "command"
        assert sdef.command_plans == ("clean_fill_start",)
        assert sdef.next_stage == "clean_fill_check"

    def test_get_correction_enabled_stage(self, registry: TopologyRegistry):
        sdef = registry.get("two_tank", "solution_fill_check")
        assert sdef.has_correction is True
        assert sdef.on_corr_success == "solution_fill_check"
        assert sdef.on_corr_fail == "solution_fill_check"

    def test_irrigation_recovery_correction_fail_is_fail_closed(self, registry: TopologyRegistry):
        sdef = registry.get("two_tank", "irrigation_recovery_check")
        assert sdef.has_correction is True
        assert sdef.on_corr_success == "irrigation_recovery_stop_to_ready"
        assert sdef.on_corr_fail == "irrigation_recovery_stop_failed"

    def test_get_terminal_stage(self, registry: TopologyRegistry):
        sdef = registry.get("two_tank", "clean_fill_timeout_stop")
        assert sdef.terminal_error is not None
        assert sdef.terminal_error[0] == "clean_tank_not_filled_timeout"
        assert sdef.next_stage is None

    def test_get_unknown_topology_raises(self, registry: TopologyRegistry):
        with pytest.raises(KeyError, match="Неизвестная topology"):
            registry.get("nonexistent", "startup")

    def test_get_unknown_stage_raises(self, registry: TopologyRegistry):
        with pytest.raises(KeyError, match="Неизвестный stage"):
            registry.get("two_tank", "nonexistent_stage")

    def test_stages_returns_full_graph(self, registry: TopologyRegistry):
        stages = registry.stages("two_tank")
        assert len(stages) == 33
        assert "startup" in stages
        assert "complete_ready" in stages
        assert "prepare_recirculation_window_exhausted" in stages
        assert "irrigation_recovery_stop_failed" in stages
        assert "clean_fill_source_empty_stop" in stages
        assert "solution_fill_source_empty_stop" in stages
        assert "solution_fill_leak_stop" in stages
        assert "prepare_recirculation_solution_low_stop" in stages
        assert "prepare_recirculation_timeout_stop" not in stages

    def test_stages_unknown_topology_raises(self, registry: TopologyRegistry):
        with pytest.raises(KeyError, match="Неизвестная topology"):
            registry.stages("nonexistent")

    def test_has_topology_true(self, registry: TopologyRegistry):
        assert registry.has_topology("two_tank") is True
        assert registry.has_topology("two_tank_drip_substrate_trays") is True

    def test_has_topology_false(self, registry: TopologyRegistry):
        assert registry.has_topology("nonexistent") is False


class TestTopologyRegistryValidate:
    """Tests for validate() error detection."""

    def test_validate_unknown_topology(self, registry: TopologyRegistry):
        errors = registry.validate("nonexistent")
        assert len(errors) == 1
        assert "Неизвестная topology" in errors[0]

    def test_validate_broken_next_stage(self):
        broken = {
            "a": StageDef("a", "command", next_stage="b_missing"),
        }
        reg = TopologyRegistry({"broken": broken})
        errors = reg.validate("broken")
        assert any("неизвестный next_stage" in e for e in errors)

    def test_validate_name_mismatch(self):
        broken = {
            "key": StageDef("different_name", "command"),
        }
        reg = TopologyRegistry({"broken": broken})
        errors = reg.validate("broken")
        assert any("не совпадает" in e for e in errors)

    def test_validate_correction_without_branches(self):
        broken = {
            "stage": StageDef(
                "stage", "check",
                has_correction=True,
                on_corr_success=None,
                on_corr_fail=None,
            ),
        }
        reg = TopologyRegistry({"broken": broken})
        errors = reg.validate("broken")
        assert any("has_correction=True" in e and "on_corr_success/on_corr_fail" in e for e in errors)

    def test_validate_terminal_and_next(self):
        broken = {
            "stage": StageDef(
                "stage", "command",
                next_stage="stage",
                terminal_error=("err", "msg"),
            ),
        }
        reg = TopologyRegistry({"broken": broken})
        errors = reg.validate("broken")
        assert any("terminal_error и next_stage" in e for e in errors)

    def test_validate_broken_corr_refs(self):
        broken = {
            "check": StageDef(
                "check", "check",
                has_correction=True,
                on_corr_success="missing_ok",
                on_corr_fail="missing_fail",
            ),
        }
        reg = TopologyRegistry({"broken": broken})
        errors = reg.validate("broken")
        assert any("on_corr_success" in e for e in errors)
        assert any("on_corr_fail" in e for e in errors)


class TestStageDefImmutability:
    """StageDef is a frozen dataclass — no mutation allowed."""

    def test_frozen(self):
        sdef = StageDef("test", "command")
        with pytest.raises(AttributeError):
            sdef.name = "modified"  # type: ignore[misc]

    def test_equality(self):
        a = StageDef("x", "command", workflow_phase="filling")
        b = StageDef("x", "command", workflow_phase="filling")
        assert a == b

    def test_hash(self):
        a = StageDef("x", "command")
        b = StageDef("x", "command")
        assert hash(a) == hash(b)
        assert len({a, b}) == 1


class TestWorkflowPhases:
    """Validates that workflow_phase values in TWO_TANK are consistent."""

    EXPECTED_PHASES = {"idle", "tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"}

    def test_all_phases_are_expected(self):
        phases = {sdef.workflow_phase for sdef in TWO_TANK.values()}
        unexpected = phases - self.EXPECTED_PHASES
        assert not unexpected, f"Unexpected phases: {unexpected}"

    def test_startup_is_idle(self):
        assert TWO_TANK["startup"].workflow_phase == "idle"

    def test_complete_ready_is_ready(self):
        assert TWO_TANK["complete_ready"].workflow_phase == "ready"

    def test_clean_fill_stages_are_filling(self):
        for name, sdef in TWO_TANK.items():
            if name.startswith("clean_fill"):
                assert sdef.workflow_phase == "tank_filling", (
                    f"{name} should be tank_filling"
                )

    def test_solution_fill_stages_are_filling_or_ready(self):
        for name, sdef in TWO_TANK.items():
            if name.startswith("solution_fill"):
                assert sdef.workflow_phase in {"tank_filling", "tank_recirc", "ready"}, (
                    f"{name} has unexpected phase {sdef.workflow_phase}"
                )

    def test_prepare_recirculation_stages_are_tank_recirc_or_ready(self):
        for name, sdef in TWO_TANK.items():
            if name.startswith("prepare_recirculation"):
                assert sdef.workflow_phase in {"tank_recirc", "ready"}, (
                    f"{name} should be tank_recirc"
                )

    def test_irrigation_stages_use_expected_transition_phases(self):
        for name, sdef in TWO_TANK.items():
            if name.startswith("irrigation_"):
                assert sdef.workflow_phase in {"tank_filling", "irrigating", "irrig_recirc", "ready"}, (
                    f"{name} has unexpected phase {sdef.workflow_phase}"
                )
