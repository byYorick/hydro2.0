"""Unit tests for workflow input policy helpers."""

from domain.policies.workflow_input_policy import (
    extract_payload_contract_version,
    extract_refill_config,
    extract_workflow,
    is_supported_payload_contract_version,
    is_three_tank_startup_workflow,
    is_two_tank_startup_workflow,
    normalize_two_tank_workflow,
)


def test_extract_refill_config_merges_execution_and_payload_overrides():
    payload = {
        "config": {"execution": {"refill": {"channel": "a", "timeout_sec": 10}}},
        "refill": {"timeout_sec": 20},
    }
    merged = extract_refill_config(payload)
    assert merged["channel"] == "a"
    assert merged["timeout_sec"] == 20


def test_extract_payload_contract_version_normalizes_case():
    payload = {"payload_contract_version": " V2 "}
    assert extract_payload_contract_version(payload) == "v2"


def test_extract_workflow_legacy_default_to_cycle_start():
    payload = {"targets": {"diagnostics": {"execution": {"strategy": "x"}}}}
    workflow = extract_workflow(
        payload=payload,
        legacy_workflow_default_enabled=True,
        requires_explicit_workflow=lambda p: True,
    )
    assert workflow == "cycle_start"


def test_is_supported_payload_contract_version():
    assert is_supported_payload_contract_version("v2") is True
    assert is_supported_payload_contract_version("unknown") is False


def test_normalize_two_tank_workflow_mapping():
    assert normalize_two_tank_workflow("cycle_start") == "startup"
    assert normalize_two_tank_workflow("refill_check") == "clean_fill_check"


def test_is_two_tank_startup_workflow_predicate():
    assert is_two_tank_startup_workflow(
        topology="two_tank_drip_substrate_trays",
        workflow="prepare_recirculation_check",
    ) is True
    assert is_two_tank_startup_workflow(topology="three_tank", workflow="startup") is False


def test_is_three_tank_startup_workflow_predicate():
    assert is_three_tank_startup_workflow(topology="three_tank", workflow="startup") is True
    assert is_three_tank_startup_workflow(topology="two_tank_drip_substrate_trays", workflow="startup") is False
