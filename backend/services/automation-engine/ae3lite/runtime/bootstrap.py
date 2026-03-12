"""Bootstrap helpers for wiring AE3-Lite v2 runtime services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ae3lite.application.adapters import LegacyIntentMapper
from ae3lite.application.use_cases import (
    ClaimNextTaskUseCase,
    CreateTaskFromIntentUseCase,
    ExecuteTaskUseCase,
    GetZoneAutomationStateUseCase,
    GetZoneControlStateUseCase,
    ReconcileCommandUseCase,
    StartupRecoveryUseCase,
)
from ae3lite.application.use_cases.workflow_router import WorkflowRouter
from ae3lite.domain.services import CycleStartPlanner, TopologyRegistry
from ae3lite.infrastructure.clients import HistoryLoggerClient
from ae3lite.infrastructure.gateways import SequentialCommandGateway
from ae3lite.infrastructure.read_models import PgTaskStatusReadModel, PgZoneRuntimeMonitor, PgZoneSnapshotReadModel
from ae3lite.infrastructure.repositories import (
    PgAeCommandRepository,
    PgAutomationTaskRepository,
    PgPidStateRepository,
    PgZoneAlertWriteRepository,
    PgZoneLeaseRepository,
    PgZoneWorkflowRepository,
)
from ae3lite.runtime.config import Ae3RuntimeConfig
from ae3lite.runtime.worker import Ae3RuntimeWorker
from common.db import fetch


@dataclass(frozen=True)
class Ae3RuntimeBundle:
    """Ready-to-use AE3 runtime services for compat ingress and worker drain."""

    create_task_from_intent_use_case: CreateTaskFromIntentUseCase
    get_zone_control_state_use_case: GetZoneControlStateUseCase
    get_zone_automation_state_use_case: GetZoneAutomationStateUseCase
    task_status_read_model: PgTaskStatusReadModel
    worker: Ae3RuntimeWorker


def build_ae3_runtime_bundle(
    *,
    config: Ae3RuntimeConfig,
    spawn_background_task_fn: Callable[..., Any],
    mark_intent_running_fn: Callable[..., Any],
    mark_intent_terminal_fn: Callable[..., Any],
    now_fn: Callable[[], datetime],
    logger: Any,
) -> Ae3RuntimeBundle:
    task_repository = PgAutomationTaskRepository()
    zone_lease_repository = PgZoneLeaseRepository()
    command_repository = PgAeCommandRepository()
    task_status_read_model = PgTaskStatusReadModel()
    history_logger_client = HistoryLoggerClient(
        base_url=config.history_logger_url,
        token=config.history_logger_api_token,
        source="automation-engine",
    )

    create_task_from_intent_use_case = CreateTaskFromIntentUseCase(
        task_repository=task_repository,
        zone_lease_repository=zone_lease_repository,
        legacy_intent_mapper=LegacyIntentMapper(),
    )
    reconcile_command_use_case = ReconcileCommandUseCase(
        task_repository=task_repository,
        command_repository=command_repository,
    )
    command_gateway = SequentialCommandGateway(
        task_repository=task_repository,
        command_repository=command_repository,
        history_logger_client=history_logger_client,
        poll_interval_sec=config.reconcile_poll_interval_sec,
    )
    workflow_repository = PgZoneWorkflowRepository()
    alert_repository = PgZoneAlertWriteRepository()
    pid_state_repository = PgPidStateRepository()
    runtime_monitor = PgZoneRuntimeMonitor()
    topology_registry = TopologyRegistry()

    workflow_router = WorkflowRouter(
        task_repository=task_repository,
        workflow_repository=workflow_repository,
        topology_registry=topology_registry,
        runtime_monitor=runtime_monitor,
        command_gateway=command_gateway,
        alert_repository=alert_repository,
        pid_state_repository=pid_state_repository,
    )

    worker = Ae3RuntimeWorker(
        owner=config.worker_owner,
        claim_next_task_use_case=ClaimNextTaskUseCase(
            task_repository=task_repository,
            zone_lease_repository=zone_lease_repository,
            lease_ttl_sec=config.lease_ttl_sec,
        ),
        idle_poll_interval_sec=config.reconcile_poll_interval_sec,
        execute_task_use_case=ExecuteTaskUseCase(
            task_repository=task_repository,
            zone_snapshot_read_model=PgZoneSnapshotReadModel(),
            planner=CycleStartPlanner(),
            command_gateway=command_gateway,
            workflow_router=workflow_router,
            alert_repository=alert_repository,
        ),
        startup_recovery_use_case=StartupRecoveryUseCase(
            task_repository=task_repository,
            lease_repository=zone_lease_repository,
            reconcile_command_use_case=reconcile_command_use_case,
            command_gateway=command_gateway,
            workflow_repository=workflow_repository,
            topology_registry=topology_registry,
        ),
        zone_lease_repository=zone_lease_repository,
        spawn_background_task_fn=spawn_background_task_fn,
        mark_intent_running_fn=mark_intent_running_fn,
        mark_intent_terminal_fn=mark_intent_terminal_fn,
        now_fn=now_fn,
        logger=logger,
        lease_ttl_sec=config.lease_ttl_sec,
    )
    get_zone_control_state_use_case = GetZoneControlStateUseCase(
        task_repository=task_repository,
        fetch_fn=fetch,
    )
    get_zone_automation_state_use_case = GetZoneAutomationStateUseCase(
        task_repository=task_repository,
        fetch_fn=fetch,
    )
    return Ae3RuntimeBundle(
        create_task_from_intent_use_case=create_task_from_intent_use_case,
        get_zone_control_state_use_case=get_zone_control_state_use_case,
        get_zone_automation_state_use_case=get_zone_automation_state_use_case,
        task_status_read_model=task_status_read_model,
        worker=worker,
    )
