"""
Prometheus-метрики AE3-Lite v2.

Отслеживает:
- stage transitions (counter + histogram длительности stage)
- correction cycles (attempts, outcomes)
- worker tick latency
- task lifecycle (created, completed, failed)
- command dispatch latency
"""

from prometheus_client import Counter, Gauge, Histogram

# ─── Intent lifecycle ───────────────────────────────────────────────

INTENT_CLAIMED = Counter(
    "ae3_intent_claimed_total",
    "Total legacy intents claimed by AE3",
    ["source_status"],
)

INTENT_TERMINAL = Counter(
    "ae3_intent_terminal_total",
    "Total legacy intents marked terminal by AE3",
    ["status"],
)

INTENT_STALE_RECLAIMED = Counter(
    "ae3_intent_stale_reclaimed_total",
    "Total stale claimed intents reclaimed by AE3",
)

# ─── Config validation (Phase 2: shadow mode) ───────────────────────

SHADOW_CONFIG_VALIDATION = Counter(
    "ae3_shadow_config_validation_total",
    "Shadow-mode validation of resolved correction config against Pydantic "
    "schema. Labels: result=ok|invalid, namespace=zone.correction|... . "
    "Does not affect runtime; Phase 3 switches handlers to strict path.",
    ["result", "namespace"],
)

# ─── Config hot-reload (Phase 5: live mode) ─────────────────────────

CONFIG_HOT_RELOAD = Counter(
    "ae3_config_hot_reload_total",
    "Handler checkpoint triggered a live-mode config refresh. "
    "Labels: result=applied|no_change|disabled|error, namespace=combined listing.",
    ["result"],
)

# Phase 7: config-mode observability for Grafana dashboards
ZONE_CONFIG_INVALID = Counter(
    "ae3_zone_config_invalid_total",
    "Schema-validation failure на resolved zone config "
    "(shadow / strict validation paths).",
    ["zone_id", "topology"],
)

ZONE_CONFIG_MODE = Gauge(
    "ae3_zone_config_mode",
    "Per-zone config_mode gauge: 0=locked, 1=live. Updated on checkpoint "
    "observations so dashboards reflect live state without querying DB.",
    ["zone_id"],
)

ZONE_CONFIG_LIVE_EDITS = Counter(
    "ae3_zone_config_live_edits_total",
    "Live-mode edit applied (AE3 `_checkpoint` detected revision advance "
    "and refreshed plan). Labels: zone_id, handler (which stage triggered).",
    ["zone_id", "handler"],
)

# ─── Task lifecycle ─────────────────────────────────────────────────

TASK_CREATED = Counter(
    "ae3_task_created_total",
    "Total tasks created",
    ["topology"],
)

TASK_COMPLETED = Counter(
    "ae3_task_completed_total",
    "Total tasks completed successfully",
    ["topology"],
)

TASK_FAILED = Counter(
    "ae3_task_failed_total",
    "Total tasks failed",
    ["topology", "error_code"],
)

# ─── Stage transitions ──────────────────────────────────────────────

STAGE_ENTERED = Counter(
    "ae3_stage_entered_total",
    "Total stage entries",
    ["topology", "stage"],
)

STAGE_DURATION = Histogram(
    "ae3_stage_duration_seconds",
    "Time spent in a stage before transition",
    ["topology", "stage"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800],
)

STAGE_RETRY = Counter(
    "ae3_stage_retry_total",
    "Total stage retries (deadline exceeded, soft errors)",
    ["topology", "stage"],
)

# ─── Correction cycle ───────────────────────────────────────────────

CORRECTION_STARTED = Counter(
    "ae3_correction_started_total",
    "Total correction cycles started",
    ["topology"],
)

CORRECTION_COMPLETED = Counter(
    "ae3_correction_completed_total",
    "Total correction cycles completed",
    ["topology", "outcome"],  # outcome: success | fail
)

CORRECTION_ATTEMPT = Counter(
    "ae3_correction_attempt_total",
    "Total correction dose attempts",
    ["topology", "corr_step"],
)

# ─── Worker tick ────────────────────────────────────────────────────

TICK_DURATION = Histogram(
    "ae3_tick_duration_seconds",
    "Time to process a single worker tick (one task evaluation)",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

TICK_ERRORS = Counter(
    "ae3_tick_errors_total",
    "Total unhandled errors during worker tick",
    ["error_type"],
)

# ─── Command dispatch ───────────────────────────────────────────────

COMMAND_DISPATCHED = Counter(
    "ae3_command_dispatched_total",
    "Total commands dispatched to history-logger",
    ["stage"],
)

COMMAND_DISPATCH_DURATION = Histogram(
    "ae3_command_dispatch_duration_seconds",
    "Time to dispatch command batch to history-logger",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

COMMAND_DISPATCH_FAILED = Counter(
    "ae3_command_dispatch_failed_total",
    "Total command dispatch failures before terminal command status",
    ["stage", "error_type"],
)

COMMAND_TERMINAL = Counter(
    "ae3_command_terminal_total",
    "Total terminal command acknowledgements received",
    ["terminal_status"],  # DONE, NO_EFFECT, ERROR, TIMEOUT, etc.
)

COMMAND_ROUNDTRIP_DURATION = Histogram(
    "ae3_command_roundtrip_duration_seconds",
    "Time from accepted publish to terminal legacy command status",
    ["channel", "terminal_status"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

COMMAND_POLL_ITERATIONS = Counter(
    "ae3_command_poll_iterations_total",
    "Total polling iterations spent waiting for terminal legacy command status",
    ["channel", "terminal_status"],
)

COMMAND_PUBLISH_REDRIVEN = Counter(
    "ae3_command_publish_redriven_total",
    "Publish pipeline continued via reconcile after HL publish without confirmed external_id",
    ["reason"],
)

COMMAND_CMD_ID_REUSED = Counter(
    "ae3_command_cmd_id_reused_total",
    "Stable cmd_id reused for planner_step retry",
    ["stage"],
)

# ─── Irrigation ─────────────────────────────────────────────────────

IRRIGATION_DECISION = Counter(
    "ae3_irrigation_decision_total",
    "Irrigation decision outcomes",
    ["topology", "strategy", "outcome"],  # outcome: run | skip | degraded_run | fail
)

IRRIGATION_DURATION = Histogram(
    "ae3_irrigation_duration_seconds",
    "Actual irrigation duration from irrigation_start to irrigation_stop",
    ["topology", "stop_reason"],  # stop_reason: ready | recovery | setup | manual
    buckets=[30, 60, 120, 300, 600, 1200, 1800, 3600],
)

IRRIGATION_SOLUTION_MIN = Counter(
    "ae3_irrigation_solution_min_total",
    "Solution-min triggered during irrigation",
    ["topology"],
)

IRRIGATION_REPLAY = Counter(
    "ae3_irrigation_replay_total",
    "Irrigation setup replays after solution-min",
    ["topology"],
)

IRRIGATION_EC_COMPONENT_DOSE = Counter(
    "ae3_irrigation_ec_component_dose_total",
    "EC component doses during irrigation correction",
    ["topology", "component"],
)

IRRIGATION_CORRECTION_ENTERED = Counter(
    "ae3_irrigation_correction_entered_total",
    "Correction cycles entered during active irrigation",
    ["topology"],
)

IRRIGATION_WAIT_READY_POLL = Counter(
    "ae3_irrigation_wait_ready_poll_total",
    "Poll iterations in await_ready while zone_workflow_phase is not ready",
    ["topology"],
)

IRRIGATION_WAIT_READY_RESOLVED = Counter(
    "ae3_irrigation_wait_ready_resolved_total",
    "Transitions from await_ready to decision_gate (snapshot workflow_phase became ready)",
    ["topology"],
)

IRRIGATION_WAIT_READY_TIMEOUT = Counter(
    "ae3_irrigation_wait_ready_timeout_total",
    "Failures: irrigation_wait_ready_timeout (deadline exceeded)",
    ["topology"],
)

IRRIGATION_WAIT_READY_DURATION_SECONDS = Histogram(
    "ae3_irrigation_wait_ready_duration_seconds",
    "Wall time spent in await_ready until transition to decision_gate",
    ["topology"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600],
)

IRRIGATION_BLOCKED = Counter(
    "ae3_start_irrigation_blocked_total",
    "Ingress blocks for start-irrigation before task creation",
    ["reason"],
)

# ─── Active tasks gauge ─────────────────────────────────────────────

ACTIVE_TASKS = Gauge(
    "ae3_active_tasks",
    "Currently active (running/waiting_command) tasks",
    ["topology"],
)

# ─── Zone lease health ───────────────────────────────────────────────

ZONE_LEASE_LOST = Counter(
    "ae3_zone_lease_lost_total",
    "Total zone lease heartbeat losses (lease could not be extended)",
    ["zone_id"],
)

ZONE_LEASE_RELEASE_FAILED = Counter(
    "ae3_zone_lease_release_failed_total",
    "Total failures to release zone lease after task completion",
    ["zone_id"],
)

LEASE_HEARTBEAT_FAILED = Counter(
    "ae3_lease_heartbeat_failed_total",
    "Consecutive lease extend failures during task heartbeat (per failed attempt)",
    ["zone_id"],
)

INTENT_SYNC_FAILED = Counter(
    "ae3_intent_sync_failed_total",
    "Intent↔task sync operations exhausted retries without persisting status",
    ["operation"],
)

ORPHAN_INTENT_RECONCILED = Counter(
    "ae3_orphan_intent_reconciled_total",
    "Orphan intents reconciled from terminal ae_tasks by background janitor",
    ["outcome"],
)

# ─── Stage deadline and correction exhaustion ────────────────────────

STAGE_DEADLINE_EXCEEDED = Counter(
    "ae3_stage_deadline_exceeded_total",
    "Total hard deadline exceedances per stage (no retries left)",
    ["topology", "stage"],
)

FAIL_SAFE_TRANSITION = Counter(
    "ae3_fail_safe_transition_total",
    "Fail-safe transitions triggered by AE3 stage logic",
    ["topology", "stage", "reason", "source"],
)

EMERGENCY_STOP_RECONCILE = Counter(
    "ae3_emergency_stop_reconcile_total",
    "Emergency-stop reconcile outcomes after node runtime event",
    ["topology", "stage", "outcome"],
)

NODE_RUNTIME_EVENT_KICK = Counter(
    "ae3_node_runtime_event_kick_total",
    "Worker kicks caused by node runtime events",
    ["event_type", "channel"],
)

NODE_REBOOT_DETECTED = Counter(
    "ae3_node_reboot_detected_total",
    "Detections of ESP32 reboot pattern (all expected truthy snapshot fields turned False) during IRR probe",
    ["topology", "stage", "node_uid"],
)

IRR_PROBE_DEFERRED = Counter(
    "ae3_irr_probe_deferred_total",
    "IRR probe attempts deferred by backoff (node unreachable / unavailable / stale snapshot)",
    ["topology", "stage", "reason"],
)

IRR_PROBE_STREAK_EXHAUSTED = Counter(
    "ae3_irr_probe_streak_exhausted_total",
    "Streak of consecutive deferred IRR probes reached limit and stage was escalated",
    ["topology", "stage"],
)

CORRECTION_EXHAUSTED = Counter(
    "ae3_correction_exhausted_total",
    "Total correction cycles that exhausted all dose attempts",
    ["topology", "stage"],
)

CORRECTION_CAP_IGNORED = Counter(
    "ae3_correction_cap_ignored_total",
    "Total times attempt-based correction caps were intentionally ignored by stage policy",
    ["topology", "stage", "cap_type"],
)

CORRECTION_DOSE_CLAMPED = Counter(
    "ae3_correction_dose_clamped_total",
    "Correction doses clamped to max_dose_ms (requested_ml > effective_ml)",
    ["pid_type"],
)

CORRECTION_PUMP_CALIBRATION_MIRROR_MISMATCH = Counter(
    "ae3_correction_pump_calibration_mirror_mismatch_total",
    "Dual calibration mismatch between pump_calibrations and NodeConfig actuator mirror",
    ["field"],
)

CORRECTION_OBSERVE_OUT_OF_BOUNDS = Counter(
    "ae3_correction_observe_out_of_bounds_total",
    "Correction observe/decision windows rejected with sensor_out_of_bounds",
)

CORRECTION_NO_EFFECT = Counter(
    "ae3_correction_no_effect_total",
    "Correction cycles that reached consecutive no-effect limit",
    ["pid_type"],
)

CORRECTION_ESTOP_INTERRUPT = Counter(
    "ae3_correction_estop_interrupt_total",
    "Correction windows interrupted by EMERGENCY_STOP_ACTIVATED",
)

CORRECTION_CONTROL_MODE_BLOCKED = Counter(
    "ae3_correction_control_mode_blocked_total",
    "Correction dosing deferred because manual/semi control_mode stopped flow-path",
)

# ─── Startup recovery ────────────────────────────────────────────────

STARTUP_RECOVERY_RUN = Counter(
    "ae3_startup_recovery_run_total",
    "Total startup recovery passes executed by AE3 runtime",
)

STARTUP_RECOVERY_TASK = Counter(
    "ae3_startup_recovery_task_total",
    "Tasks processed during startup recovery grouped by recovery outcome",
    ["outcome"],  # completed | failed | waiting_command | recovered_waiting_command
)

STARTUP_RECOVERY_SKIPPED = Counter(
    "ae3_startup_recovery_skipped_total",
    "Startup recovery passes skipped without scanning tasks",
    ["reason"],
)

WAITING_COMMAND_RECONCILE = Counter(
    "ae3_waiting_command_reconcile_total",
    "Background waiting_command reconcile outcomes",
    ["outcome"],
)

STALE_TASKS_RECLAIMED = Counter(
    "ae3_stale_tasks_reclaimed_total",
    "Stale claimed/running tasks reclaimed by background janitor",
    ["from_status", "action"],
)

RECONCILE_FOREIGN_LEASE = Counter(
    "ae3_reconcile_foreign_lease_total",
    "Foreign active lease reconcile decisions (bounded skip vs escalate)",
    ["source", "outcome"],
)

# ─── Pending queue observability (PR4) ─────────────────────────────

PENDING_TASKS = Gauge(
    "ae3_pending_tasks",
    "Количество задач AE3 в статусе pending",
)

OLDEST_PENDING_TASK_AGE_SECONDS = Gauge(
    "ae3_oldest_pending_task_age_seconds",
    "Возраст самой старой pending-задачи в секундах",
)

OLDEST_ACTIVE_TASK_AGE_SECONDS = Gauge(
    "ae3_oldest_active_task_age_seconds",
    "Возраст самой старой активной задачи по статусу (секунды)",
    ["status"],
)

RECONCILE_CONSECUTIVE_ERRORS = Gauge(
    "ae3_reconcile_consecutive_errors",
    "Подряд идущие ошибки фонового waiting_command/stale reconcile loop",
)

TASK_DURATION_SECONDS = Histogram(
    "ae3_task_duration_seconds",
    "Wall-clock длительность задачи от created_at до terminal transition",
    ["topology", "outcome"],
    buckets=[5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200],
)

LISTENER_CONNECTED = Gauge(
    "ae3_listener_connected",
    "Состояние PostgreSQL NOTIFY listener (1=connected, 0=down)",
    ["listener"],
)

LISTENER_RECONNECT_TOTAL = Counter(
    "ae3_listener_reconnect_total",
    "Переподключения PostgreSQL NOTIFY listener после ошибки",
    ["listener"],
)

LISTENER_INVALID_PAYLOAD = Counter(
    "ae3_listener_invalid_payload_total",
    "Некорректный JSON/payload в PostgreSQL NOTIFY listener",
    ["listener"],
)

OBSERVABILITY_WRITE_FAILED = Counter(
    "ae3_observability_write_failed_total",
    "Ошибки записи zone_events/alerts, проглоченные без прерывания runtime",
    ["kind"],
)

# ─── Worker drain supervisor (PR2) ─────────────────────────────────

DRAIN_CRASHES = Counter(
    "ae3_drain_crashes_total",
    "Total unhandled crashes in AE3 drain loop recovered by drain supervisor",
)

TASK_EXECUTION_CRASHED = Counter(
    "ae3_task_execution_crashed_total",
    "Total task executions that crashed in worker wrapper (isolated per-task)",
    ["error"],
)

FLOW_STOP_FAILED = Counter(
    "ae3_flow_stop_failed_total",
    "Flow-path stop не подтверждён OFF (команда или probe)",
    ["stage"],
)

CLAIM_ROLLBACK_FAILED = Counter(
    "ae3_claim_rollback_failed_total",
    "Total claim rollbacks that failed after zone lease conflict",
)

TASK_RUNNING_TRANSITION_MISSED = Counter(
    "ae3_task_running_transition_missed_total",
    "Total mark_running CAS misses handled fail-closed",
)

# ─── Greenhouse climate ─────────────────────────────────────────────

GREENHOUSE_CLIMATE_TICK_TOTAL = Counter(
    "greenhouse_climate_tick_total",
    "Greenhouse climate ticks grouped by terminal runtime status",
    ["status"],
)

GREENHOUSE_CLIMATE_COMMAND_TOTAL = Counter(
    "greenhouse_climate_command_total",
    "Greenhouse climate actuator commands grouped by side and terminal status",
    ["side", "status"],
)

GREENHOUSE_CLIMATE_DECISION_DURATION_SECONDS = Histogram(
    "greenhouse_climate_decision_duration_seconds",
    "Wall-clock duration of one greenhouse climate tick",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

GREENHOUSE_CLIMATE_SENSOR_STALE_TOTAL = Counter(
    "greenhouse_climate_sensor_stale_total",
    "Greenhouse climate stale sensor detections",
    ["kind"],
)

GREENHOUSE_CLIMATE_WIND_CLAMP_TOTAL = Counter(
    "greenhouse_climate_wind_clamp_total",
    "Greenhouse climate decisions where wind clamp was active",
)

GREENHOUSE_CLIMATE_RAIN_CLAMP_TOTAL = Counter(
    "greenhouse_climate_rain_clamp_total",
    "Greenhouse climate decisions where rain clamp was active",
)

GREENHOUSE_CLIMATE_COMMAND_FAILED_TOTAL = Counter(
    "greenhouse_climate_command_failed_total",
    "Greenhouse climate actuator command failures grouped by side and failure code",
    ["side", "failure"],
)


def inc_observability_write_failed(*, kind: str) -> None:
    """Инкрементирует счётчик проглоченных ошибок observability-записи."""
    normalized = str(kind or "").strip().lower() or "unknown"
    OBSERVABILITY_WRITE_FAILED.labels(kind=normalized).inc()


def initialize_counter_series() -> None:
    """Pre-register counter series for known static label combinations.

    Creates child counters with value 0 so Grafana timeseries / rate() queries
    render baseline "0" instead of "No data" before the first real increment.
    Covers only enum-style labels (topology, stage, component, known
    error_type). Dynamic labels (zone_id, error_code, exception class names)
    remain lazy; dashboard queries fall back via `or vector(0)` where needed.
    """
    from ae3lite.application.services.workflow_topology import TopologyRegistry

    registry = TopologyRegistry()

    for error_type in ("LeaseLost", "TimeoutError"):
        TICK_ERRORS.labels(error_type=error_type)

    for topology in ("two_tank_drip_substrate_trays", "two_tank", "generic_cycle_start"):
        IRRIGATION_SOLUTION_MIN.labels(topology=topology)
        for component in ("A", "B", "micro"):
            IRRIGATION_EC_COMPONENT_DOSE.labels(topology=topology, component=component)
        try:
            stages = registry.stages(topology)
        except KeyError:
            continue
        for stage in stages.keys():
            STAGE_RETRY.labels(topology=topology, stage=stage)
            STAGE_DEADLINE_EXCEEDED.labels(topology=topology, stage=stage)
            CORRECTION_EXHAUSTED.labels(topology=topology, stage=stage)
