"""Workflow input extraction and normalization helpers."""

from __future__ import annotations

from typing import Any, Callable, Dict


def extract_execution_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    return execution


def extract_refill_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    execution = extract_execution_config(payload)
    execution_refill = execution.get("refill") if isinstance(execution.get("refill"), dict) else {}
    payload_refill = payload.get("refill") if isinstance(payload.get("refill"), dict) else {}
    merged = dict(execution_refill)
    merged.update(payload_refill)
    return merged


def extract_payload_contract_version(payload: Dict[str, Any]) -> str:
    execution = extract_execution_config(payload)
    raw_version = (
        payload.get("payload_contract_version")
        or execution.get("payload_contract_version")
        or ""
    )
    return str(raw_version or "").strip().lower()


def is_supported_payload_contract_version(contract_version: str) -> bool:
    if not contract_version:
        return True
    return contract_version in {"v1", "v2", "1", "2", "legacy"}


def extract_workflow(
    *,
    payload: Dict[str, Any],
    legacy_workflow_default_enabled: bool,
    requires_explicit_workflow: Callable[[Dict[str, Any]], bool],
) -> str:
    execution = extract_execution_config(payload)
    raw_workflow = (
        payload.get("workflow")
        or payload.get("diagnostics_workflow")
        or execution.get("workflow")
        or ""
    )
    workflow = str(raw_workflow or "").strip().lower()
    if workflow:
        return workflow
    if legacy_workflow_default_enabled and requires_explicit_workflow(payload):
        # Three-tank topologies always require an explicit workflow even in legacy mode.
        # Legacy default applies only to two-tank (and empty-topology) payloads.
        topology = extract_topology(payload)
        if not topology.startswith("three_tank"):
            return "cycle_start"
    return ""


def extract_topology(payload: Dict[str, Any]) -> str:
    execution = extract_execution_config(payload)
    targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}
    diagnostics_targets = targets.get("diagnostics") if isinstance(targets.get("diagnostics"), dict) else {}
    diagnostics_execution = (
        diagnostics_targets.get("execution")
        if isinstance(diagnostics_targets.get("execution"), dict)
        else {}
    )
    raw = (
        payload.get("topology")
        or execution.get("topology")
        or diagnostics_execution.get("topology")
        or ""
    )
    return str(raw).strip().lower()


def normalize_two_tank_workflow(workflow: str) -> str:
    if workflow == "cycle_start":
        return "startup"
    if workflow == "refill_check":
        return "clean_fill_check"
    return workflow


def is_two_tank_startup_workflow(*, topology: str, workflow: str) -> bool:
    if topology != "two_tank_drip_substrate_trays":
        return False
    return workflow in {
        "startup",
        "clean_fill_check",
        "solution_fill_check",
        "prepare_recirculation",
        "prepare_recirculation_check",
        "irrigation_recovery",
        "irrigation_recovery_check",
    }


def is_three_tank_startup_workflow(*, topology: str, workflow: str) -> bool:
    if topology not in {
        "three_tank_drip_substrate_trays",
        "three_tank_substrate_trays",
        "three_tank",
    }:
        return False
    return workflow in {"startup", "cycle_start", "refill_check"}


__all__ = [
    "extract_execution_config",
    "extract_payload_contract_version",
    "extract_refill_config",
    "extract_topology",
    "extract_workflow",
    "is_supported_payload_contract_version",
    "is_three_tank_startup_workflow",
    "is_two_tank_startup_workflow",
    "normalize_two_tank_workflow",
]
