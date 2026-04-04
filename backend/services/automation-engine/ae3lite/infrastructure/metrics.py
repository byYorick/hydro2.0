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

# ─── Stage deadline and correction exhaustion ────────────────────────

STAGE_DEADLINE_EXCEEDED = Counter(
    "ae3_stage_deadline_exceeded_total",
    "Total hard deadline exceedances per stage (no retries left)",
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
