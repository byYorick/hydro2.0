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
