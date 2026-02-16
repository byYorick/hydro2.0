"""Line-budget guard rail for large automation-engine modules.

This is a non-regression gate for decomposition phases.
Budgets should be tightened as phases D2-D7 progress.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


LINE_BUDGET = {
    "scheduler_task_executor.py": 200,
    "application/scheduler_executor_impl.py": 4200,
    "application/task_events.py": 400,
    "application/task_events_persistence.py": 500,
    "application/task_context.py": 300,
    "application/cycle_alerts.py": 300,
    "application/execution_flow_policy.py": 500,
    "application/execution_logging.py": 400,
    "application/execution_finalize.py": 500,
    "application/execution_startup.py": 400,
    "application/execution_decision.py": 400,
    "application/execution_prepare.py": 300,
    "application/decision_retry_enqueue.py": 400,
    "application/workflow_phase_update.py": 400,
    "application/two_tank_enqueue.py": 300,
    "application/two_tank_compensation.py": 400,
    "application/two_tank_logging.py": 300,
    "application/two_tank_command_plan_core.py": 500,
    "application/dispatch_merge.py": 300,
    "application/command_publish_batch.py": 700,
    "application/device_task_core.py": 500,
    "application/ventilation_climate_guards.py": 400,
    "application/two_tank_runtime_config.py": 900,
    "application/workflow_phase_sync_core.py": 700,
    "application/sensor_mode_dispatch.py": 400,
    "application/two_tank_recovery_transition.py": 500,
    "application/refill_command_resolver.py": 400,
    "application/diagnostics_execution.py": 500,
    "application/two_tank_phase_starters.py": 1200,
    "application/diagnostics_task_execution.py": 400,
    "application/executor_run.py": 500,
    "application/executor_init.py": 400,
    "application/executor_constants.py": 600,
    "application/executor_method_delegates.py": 700,
    "application/executor_small_delegates.py": 500,
    "application/executor_event_delegates.py": 400,
    "application/executor_bound_two_tank_methods.py": 500,
    "application/executor_bound_core_methods.py": 500,
    "application/executor_bound_workflow_methods.py": 500,
    "application/executor_bound_refill_methods.py": 500,
    "application/executor_bound_misc_methods.py": 500,
    "application/executor_bound_policy_static_methods.py": 800,
    "application/executor_bound_workflow_input_methods.py": 500,
    "application/executor_bound_query_dispatch_methods.py": 500,
    "application/executor_bound_runtime_methods.py": 400,
    "application/executor_bound_phase_methods.py": 400,
    "application/api_automation_state.py": 500,
    "application/api_payload_parsing.py": 300,
    "application/api_task_snapshot.py": 400,
    "application/decision_alerts.py": 300,
    "application/execution_branches.py": 400,
    "application/no_action_branch.py": 400,
    "application/workflow_phase_policy.py": 500,
    "api.py": 3100,
    "services/zone_automation_service.py": 2700,
    "correction_controller.py": 1600,
    "infrastructure/node_query_adapter.py": 500,
    "infrastructure/telemetry_query_adapter.py": 700,
    "domain/policies/cycle_start_refill_policy.py": 500,
    "domain/policies/command_mapping_policy.py": 500,
    "domain/policies/decision_detail_policy.py": 500,
    "domain/policies/diagnostics_policy.py": 500,
    "domain/policies/normalization_policy.py": 500,
    "domain/policies/outcome_policy.py": 500,
    "domain/policies/outcome_enrichment_policy.py": 700,
    "domain/policies/target_evaluation_policy.py": 500,
    "domain/policies/two_tank_guard_policy.py": 500,
    "domain/policies/workflow_input_policy.py": 500,
    "domain/workflows/two_tank_core.py": 300,
    "domain/workflows/two_tank_startup_core.py": 950,
    "domain/workflows/two_tank_recovery_core.py": 600,
}


def _count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def test_line_budget_non_regression():
    exceeded = []
    for rel_path, budget in LINE_BUDGET.items():
        full_path = ROOT / rel_path
        line_count = _count_lines(full_path)
        if line_count > budget:
            exceeded.append((rel_path, line_count, budget))

    assert not exceeded, "\n".join(
        f"{path}: {count} lines (budget {budget})"
        for path, count, budget in exceeded
    )
