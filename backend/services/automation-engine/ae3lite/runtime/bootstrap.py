"""Bootstrap-helper'ы для связывания runtime-сервисов AE3-Lite v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import httpx

from ae3lite.application.use_cases import (
    ClaimNextTaskUseCase,
    CreateTaskFromIntentUseCase,
    ExecuteTaskUseCase,
    GuardSolutionTankStartupResetUseCase,
    GetZoneAutomationStateUseCase,
    GetZoneControlStateUseCase,
    RequestManualStepUseCase,
    SetControlModeUseCase,
    StartupRecoveryUseCase,
    StaleTaskReconcileUseCase,
    TriggerSolutionTopupFromLevelEventUseCase,
    WaitingCommandReconcileUseCase,
)
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.application.use_cases.workflow_router import WorkflowRouter
from ae3lite.domain.services.cycle_start_planner import CycleStartPlanner
from ae3lite.domain.services.irrigation_decision_controller import IrrigationDecisionController
from ae3lite.infrastructure.clients import HistoryLoggerClient
from ae3lite.infrastructure.gateways import SequentialCommandGateway
from ae3lite.infrastructure.read_models import PgTaskStatusReadModel, PgZoneRuntimeMonitor, PgZoneSnapshotReadModel
from ae3lite.infrastructure.repositories import (
    PgAeCommandRepository,
    PgAutomationTaskRepository,
    PgPidStateRepository,
    PgZoneCorrectionAuthorityRepository,
    PgZoneAlertRepository,
    PgZoneIntentRepository,
    PgZoneLeaseRepository,
    PgZoneWorkflowRepository,
)
from ae3lite.runtime.env import Ae3RuntimeConfig
from ae3lite.runtime.worker import Ae3RuntimeWorker
from common.biz_alerts import BizAlertPublisher
from common.db import fetch


@dataclass(frozen=True)
class Ae3RuntimeBundle:
    """Готовые к использованию runtime-сервисы AE3 для compat-ingress и drain worker'а."""

    create_task_from_intent_use_case: CreateTaskFromIntentUseCase
    solution_tank_startup_guard_use_case: GuardSolutionTankStartupResetUseCase
    trigger_solution_topup_from_level_event_use_case: TriggerSolutionTopupFromLevelEventUseCase
    get_zone_control_state_use_case: GetZoneControlStateUseCase
    request_manual_step_use_case: RequestManualStepUseCase
    set_control_mode_use_case: SetControlModeUseCase
    get_zone_automation_state_use_case: GetZoneAutomationStateUseCase
    task_status_read_model: PgTaskStatusReadModel
    zone_intent_repository: PgZoneIntentRepository
    worker: Ae3RuntimeWorker
    http_client: httpx.AsyncClient
    history_logger_client: HistoryLoggerClient


def build_ae3_runtime_bundle(
    *,
    config: Ae3RuntimeConfig,
    spawn_background_task_fn: Callable[..., Any],
    now_fn: Callable[[], datetime],
    logger: Any,
) -> Ae3RuntimeBundle:
    task_repository = PgAutomationTaskRepository()
    zone_lease_repository = PgZoneLeaseRepository()
    zone_alert_repository = PgZoneAlertRepository()
    command_repository = PgAeCommandRepository()
    task_status_read_model = PgTaskStatusReadModel()
    zone_intent_repository = PgZoneIntentRepository()
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=config.http_client_connect_timeout_sec,
            read=config.http_client_read_timeout_sec,
            write=config.http_client_write_timeout_sec,
            pool=config.http_client_pool_timeout_sec,
        )
    )
    history_logger_client = HistoryLoggerClient(
        base_url=config.history_logger_url,
        token=config.history_logger_api_token,
        source="automation-engine",
        client=http_client,
        max_retries=config.hl_max_retries,
        retry_backoff_sec=config.hl_retry_backoff_sec,
        breaker_fail_threshold=config.hl_breaker_fail_threshold,
        breaker_open_sec=config.hl_breaker_open_sec,
    )

    create_task_from_intent_use_case = CreateTaskFromIntentUseCase(
        task_repository=task_repository,
        zone_lease_repository=zone_lease_repository,
        zone_intent_repository=zone_intent_repository,
        zone_alert_repository=zone_alert_repository,
    )
    command_gateway = SequentialCommandGateway(
        task_repository=task_repository,
        command_repository=command_repository,
        history_logger_client=history_logger_client,
        poll_interval_sec=config.reconcile_poll_interval_sec,
        command_poll_default_sec=config.command_poll_default_sec,
        command_poll_margin_sec=config.command_poll_margin_sec,
    )
    workflow_repository = PgZoneWorkflowRepository()
    alert_repository = BizAlertPublisher()
    topology_registry = TopologyRegistry()
    startup_recovery_use_case = StartupRecoveryUseCase(
        task_repository=task_repository,
        lease_repository=zone_lease_repository,
        command_gateway=command_gateway,
        workflow_repository=workflow_repository,
        topology_registry=topology_registry,
        alert_repository=alert_repository,
        worker_owner=config.worker_owner,
    )
    waiting_command_reconcile_use_case = WaitingCommandReconcileUseCase(
        task_repository=task_repository,
        lease_repository=zone_lease_repository,
        startup_recovery_use_case=startup_recovery_use_case,
        batch_limit=config.waiting_command_reconcile_batch_limit,
    )
    stale_task_reconcile_use_case = StaleTaskReconcileUseCase(
        task_repository=task_repository,
        lease_repository=zone_lease_repository,
        alert_repository=alert_repository,
        stale_claimed_ttl_sec=config.stale_claimed_ttl_sec,
        stale_running_ttl_sec=config.stale_running_ttl_sec,
    )
    pid_state_repository = PgPidStateRepository()
    correction_authority_repository = PgZoneCorrectionAuthorityRepository()
    runtime_monitor = PgZoneRuntimeMonitor()
    irrigation_decision_controller = IrrigationDecisionController()

    workflow_router = WorkflowRouter(
        task_repository=task_repository,
        workflow_repository=workflow_repository,
        topology_registry=topology_registry,
        runtime_monitor=runtime_monitor,
        command_gateway=command_gateway,
        alert_repository=alert_repository,
        pid_state_repository=pid_state_repository,
        decision_controller=irrigation_decision_controller,
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
            workflow_repository=workflow_repository,
            correction_authority_repository=correction_authority_repository,
            alert_repository=alert_repository,
            command_repository=command_repository,
        ),
        startup_recovery_use_case=startup_recovery_use_case,
        waiting_command_reconcile_use_case=waiting_command_reconcile_use_case,
        stale_task_reconcile_use_case=stale_task_reconcile_use_case,
        task_repository=task_repository,
        command_repository=command_repository,
        zone_lease_repository=zone_lease_repository,
        zone_intent_repository=zone_intent_repository,
        spawn_background_task_fn=spawn_background_task_fn,
        now_fn=now_fn,
        logger=logger,
        lease_ttl_sec=config.lease_ttl_sec,
        max_task_execution_sec=config.max_task_execution_sec,
        max_parallel_tasks=config.max_parallel_tasks,
        reconcile_poll_interval_sec=config.reconcile_poll_interval_sec,
        stale_task_reconcile_interval_sec=config.stale_task_reconcile_sec,
        shutdown_grace_sec=config.shutdown_grace_sec,
        lease_heartbeat_max_failures=config.lease_heartbeat_max_failures,
        lease_heartbeat_transient_retries=config.lease_heartbeat_transient_retries,
        intent_sync_max_retries=config.intent_sync_max_retries,
    )
    get_zone_control_state_use_case = GetZoneControlStateUseCase(
        task_repository=task_repository,
        fetch_fn=fetch,
        workflow_repository=workflow_repository,
    )
    request_manual_step_use_case = RequestManualStepUseCase(
        task_repository=task_repository,
        fetch_fn=fetch,
    )
    set_control_mode_use_case = SetControlModeUseCase(
        task_repository=task_repository,
    )
    solution_tank_startup_guard_use_case = GuardSolutionTankStartupResetUseCase(
        runtime_monitor=runtime_monitor,
        workflow_repository=workflow_repository,
        fetch_fn=fetch,
    )
    trigger_solution_topup_from_level_event_use_case = TriggerSolutionTopupFromLevelEventUseCase(
        zone_intent_repository=zone_intent_repository,
        create_task_from_intent_use_case=create_task_from_intent_use_case,
        runtime_monitor=runtime_monitor,
        fetch_fn=fetch,
    )
    get_zone_automation_state_use_case = GetZoneAutomationStateUseCase(
        task_repository=task_repository,
        workflow_repository=workflow_repository,
        fetch_fn=fetch,
        startup_reset_guard_use_case=solution_tank_startup_guard_use_case,
    )
    return Ae3RuntimeBundle(
        create_task_from_intent_use_case=create_task_from_intent_use_case,
        solution_tank_startup_guard_use_case=solution_tank_startup_guard_use_case,
        trigger_solution_topup_from_level_event_use_case=trigger_solution_topup_from_level_event_use_case,
        get_zone_control_state_use_case=get_zone_control_state_use_case,
        request_manual_step_use_case=request_manual_step_use_case,
        set_control_mode_use_case=set_control_mode_use_case,
        get_zone_automation_state_use_case=get_zone_automation_state_use_case,
        task_status_read_model=task_status_read_model,
        zone_intent_repository=zone_intent_repository,
        worker=worker,
        http_client=http_client,
        history_logger_client=history_logger_client,
    )
