"""Workflow payload contract validation for scheduler task execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from infrastructure.observability import log_structured

logger = logging.getLogger(__name__)
_WORKFLOWS_REQUIRING_TOPOLOGY = {
    "startup",
    "cycle_start",
    "refill_check",
    "clean_fill_check",
    "solution_fill_check",
    "prepare_recirculation",
    "prepare_recirculation_check",
    "irrigation_recovery",
    "irrigation_recovery_check",
}


@dataclass(frozen=True)
class WorkflowValidationResult:
    valid: bool
    workflow: str
    topology: str
    payload_contract_version: str
    requires_explicit_workflow: bool
    error_result: Optional[Dict[str, Any]] = None


class WorkflowValidator:
    """Validates diagnostics workflow payload against contract gates."""

    def __init__(
        self,
        *,
        extract_workflow: Callable[[Dict[str, Any]], str],
        extract_topology: Callable[[Dict[str, Any]], str],
        extract_payload_contract_version: Callable[[Dict[str, Any]], str],
        is_supported_payload_contract_version: Callable[[str], bool],
        requires_explicit_workflow: Callable[[Dict[str, Any]], bool],
        build_invalid_payload_result: Callable[..., Dict[str, Any]],
        explicit_workflow_feature_enabled: Callable[[], bool],
    ) -> None:
        self._extract_workflow = extract_workflow
        self._extract_topology = extract_topology
        self._extract_payload_contract_version = extract_payload_contract_version
        self._is_supported_payload_contract_version = is_supported_payload_contract_version
        self._requires_explicit_workflow = requires_explicit_workflow
        self._build_invalid_payload_result = build_invalid_payload_result
        self._explicit_workflow_feature_enabled = explicit_workflow_feature_enabled

    def validate_diagnostics(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        task_type: str,
        task_id: Optional[str],
        correlation_id: Optional[str],
    ) -> WorkflowValidationResult:
        workflow = self._extract_workflow(payload)
        topology = self._extract_topology(payload)
        contract_version = self._extract_payload_contract_version(payload)
        requires_explicit = (
            self._explicit_workflow_feature_enabled()
            and self._requires_explicit_workflow(payload)
        )

        if not self._is_supported_payload_contract_version(contract_version):
            reason_code = "invalid_payload_contract_version"
            log_structured(
                logger,
                logging.WARNING,
                "Diagnostics payload rejected: unsupported contract version",
                component="workflow_validator",
                zone_id=zone_id,
                task_id=task_id,
                task_type=task_type,
                workflow=workflow or None,
                decision="fail",
                reason_code=reason_code,
                result_status="rejected",
                correlation_id=correlation_id,
            )
            return WorkflowValidationResult(
                valid=False,
                workflow=workflow,
                topology=topology,
                payload_contract_version=contract_version,
                requires_explicit_workflow=requires_explicit,
                error_result=self._build_invalid_payload_result(
                    reason_code=reason_code,
                    reason=(
                        "Неподдерживаемая версия payload_contract_version для diagnostics workflow: "
                        f"{contract_version}"
                    ),
                    payload_contract_version=contract_version,
                ),
            )

        topology_required = requires_explicit or workflow in _WORKFLOWS_REQUIRING_TOPOLOGY
        if topology_required and not topology:
            reason_code = "invalid_payload_missing_topology"
            log_structured(
                logger,
                logging.WARNING,
                "Diagnostics payload rejected: missing topology",
                component="workflow_validator",
                zone_id=zone_id,
                task_id=task_id,
                task_type=task_type,
                workflow=workflow or None,
                decision="fail",
                reason_code=reason_code,
                result_status="rejected",
                correlation_id=correlation_id,
            )
            return WorkflowValidationResult(
                valid=False,
                workflow=workflow,
                topology=topology,
                payload_contract_version=contract_version,
                requires_explicit_workflow=requires_explicit,
                error_result=self._build_invalid_payload_result(
                    reason_code=reason_code,
                    reason="Для diagnostics task требуется обязательное payload.topology",
                    payload_contract_version=contract_version or "v2",
                ),
            )

        if not workflow:
            reason_code = "invalid_payload_missing_workflow"
            log_structured(
                logger,
                logging.WARNING,
                "Diagnostics payload rejected: missing workflow",
                component="workflow_validator",
                zone_id=zone_id,
                task_id=task_id,
                task_type=task_type,
                decision="fail",
                reason_code=reason_code,
                result_status="rejected",
                correlation_id=correlation_id,
            )
            return WorkflowValidationResult(
                valid=False,
                workflow=workflow,
                topology=topology,
                payload_contract_version=contract_version,
                requires_explicit_workflow=requires_explicit,
                error_result=self._build_invalid_payload_result(
                    reason_code=reason_code,
                    reason="Для diagnostics task требуется обязательное payload.workflow",
                    payload_contract_version=contract_version or "v2",
                ),
            )

        log_structured(
            logger,
            logging.INFO,
            "Diagnostics payload validated",
            component="workflow_validator",
            zone_id=zone_id,
            task_id=task_id,
            task_type=task_type,
            workflow=workflow or None,
            decision="run",
            reason_code="payload_valid",
            result_status="success",
            correlation_id=correlation_id,
        )
        return WorkflowValidationResult(
            valid=True,
            workflow=workflow,
            topology=topology,
            payload_contract_version=contract_version,
            requires_explicit_workflow=requires_explicit,
        )
