"""Initialization helpers for SchedulerTaskExecutor runtime components."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Set

from application.command_dispatch import CommandDispatch
from application.workflow_router import WorkflowRouter
from application.workflow_state_sync import WorkflowStateSync
from application.workflow_validator import WorkflowValidator
from domain.workflows.cycle_start import CycleStartWorkflow
from domain.workflows.three_tank import ThreeTankWorkflow
from domain.workflows.two_tank import TwoTankWorkflow
from infrastructure.workflow_state_store import WorkflowStateStore


def initialize_executor_components(
    *,
    executor: Any,
    command_bus: Any,
    zone_service: Optional[Any],
    workflow_state_store: Optional[WorkflowStateStore],
    workflow_state_persist_enabled: bool,
    two_tank_topologies: Set[str],
    three_tank_topologies: Set[str],
    cycle_start_workflows: Set[str],
) -> None:
    executor.command_bus = command_bus
    executor.zone_service = zone_service
    executor.workflow_state_store = workflow_state_store or WorkflowStateStore()
    executor.workflow_state_persist_enabled = workflow_state_persist_enabled
    executor._workflow_state_persist_failed = False

    executor.workflow_validator = WorkflowValidator(
        extract_workflow=executor._extract_workflow,
        extract_topology=executor._extract_topology,
        extract_payload_contract_version=executor._extract_payload_contract_version,
        is_supported_payload_contract_version=executor._is_supported_payload_contract_version,
        requires_explicit_workflow=executor._requires_explicit_workflow,
        build_invalid_payload_result=executor._build_diagnostics_invalid_payload_result,
        explicit_workflow_feature_enabled=executor._tank_state_machine_enabled,
    )
    executor.two_tank_workflow = TwoTankWorkflow(execute_impl=executor._execute_two_tank_startup_workflow_core)
    executor.three_tank_workflow = ThreeTankWorkflow(execute_impl=executor._execute_three_tank_startup_workflow_core)
    executor.cycle_start_workflow = CycleStartWorkflow(execute_impl=executor._execute_cycle_start_workflow_core)
    executor.workflow_router = WorkflowRouter(
        two_tank_topologies=two_tank_topologies,
        three_tank_topologies=three_tank_topologies,
        cycle_start_workflows=cycle_start_workflows,
        execute_two_tank=executor.two_tank_workflow.execute,
        execute_three_tank=executor.three_tank_workflow.execute,
        execute_cycle_start=executor.cycle_start_workflow.execute,
        execute_default=executor._execute_diagnostics,
    )
    executor.command_dispatch = CommandDispatch(
        execute_device_task_impl=executor._execute_device_task_core,
        dispatch_command_plan_impl=executor._dispatch_two_tank_command_plan_core,
    )
    executor.workflow_state_sync = WorkflowStateSync(sync_impl=executor._sync_zone_workflow_phase_core)


__all__ = ["initialize_executor_components"]
