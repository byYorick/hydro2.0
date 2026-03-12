"""Domain errors for AE3-Lite v1."""

from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    """Canonical ae_tasks.status values.

    Using ``str`` mixin allows transparent comparison with plain strings:
        task.status == TaskStatus.COMPLETED  →  True  (when task.status == "completed")
    """

    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    WAITING_COMMAND = "waiting_command"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    @property
    def is_active(self) -> bool:
        return self in (
            TaskStatus.CLAIMED,
            TaskStatus.RUNNING,
            TaskStatus.WAITING_COMMAND,
        )


class IntentStatus(str, Enum):
    """Canonical zone_automation_intents.status values."""

    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TERMINAL = "terminal"

    @property
    def is_terminal(self) -> bool:
        return self in (
            IntentStatus.COMPLETED,
            IntentStatus.FAILED,
            IntentStatus.CANCELLED,
            IntentStatus.TERMINAL,
        )


class ErrorCodes:
    """Centralized registry of AE3-Lite error code string constants.

    Use these constants instead of inline string literals to ensure
    consistency and enable IDE navigation.

    Example::
        raise TaskExecutionError(ErrorCodes.AE3_UNKNOWN_HANDLER, "No handler for stage X")
    """

    # Task lifecycle
    AE3_TASK_EXECUTION_FAILED = "ae3_task_execution_failed"
    AE3_TASK_EXECUTION_UNHANDLED_EXCEPTION = "ae3_task_execution_unhandled_exception"
    AE3_TASK_FINALIZE_FAILED = "ae3_task_finalize_failed"
    AE3_TASK_CREATE_FAILED = "ae3_task_create_failed"
    AE3_TASK_COMPLETE_FAILED = "ae3_task_complete_failed"
    AE3_TASK_MISSING_OWNER = "ae3_task_missing_owner"

    # Stage transitions
    AE3_UNKNOWN_HANDLER = "ae3_unknown_handler"
    AE3_UNKNOWN_OUTCOME_KIND = "ae3_unknown_outcome_kind"
    AE3_TRANSITION_NO_NEXT_STAGE = "ae3_transition_no_next_stage"
    AE3_COMMAND_NO_ROUTING = "ae3_command_no_routing"
    AE3_ENTER_CORRECTION_NO_STATE = "ae3_enter_correction_no_state"
    AE3_UNKNOWN_CORR_STEP = "ae3_unknown_corr_step"
    AE3_STAGE_FAILED = "ae3_stage_failed"
    AE3_EMPTY_COMMAND_PLAN = "ae3_empty_command_plan"

    # Command dispatch / reconcile
    AE3_MISSING_AE_COMMAND = "ae3_missing_ae_command"
    AE3_MISSING_CMD_ID = "ae3_missing_cmd_id"
    AE3_LEGACY_COMMAND_NOT_FOUND = "ae3_legacy_command_not_found"
    AE3_UNSUPPORTED_LEGACY_STATUS = "ae3_unsupported_legacy_status"
    AE3_WAITING_COMMAND_TRANSITION_FAILED = "ae3_waiting_command_transition_failed"
    AE3_RUNNING_TRANSITION_FAILED = "ae3_running_transition_failed"
    AE3_FAILED_TRANSITION_FAILED = "ae3_failed_transition_failed"
    AE3_COMPLETE_TRANSITION_FAILED = "ae3_complete_transition_failed"
    AE3_TASK_RUNNING_TRANSITION_FAILED = "ae3_task_running_transition_failed"
    AE3_COMMAND_POLL_DEADLINE_EXCEEDED = "ae3_command_poll_deadline_exceeded"
    AE3_INVALID_PLANNED_COMMAND = "ae3_invalid_planned_command"
    COMMAND_SEND_FAILED = "command_send_failed"

    # IRR state
    IRR_STATE_UNAVAILABLE = "irr_state_unavailable"
    IRR_STATE_STALE = "irr_state_stale"
    IRR_STATE_MISMATCH = "irr_state_mismatch"

    # Level sensors / tank
    TWO_TANK_CLEAN_LEVEL_UNAVAILABLE = "two_tank_clean_level_unavailable"
    TWO_TANK_CLEAN_LEVEL_STALE = "two_tank_clean_level_stale"
    TWO_TANK_CLEAN_MIN_LEVEL_UNAVAILABLE = "two_tank_clean_min_level_unavailable"
    TWO_TANK_CLEAN_MIN_LEVEL_STALE = "two_tank_clean_min_level_stale"
    TWO_TANK_SOLUTION_LEVEL_UNAVAILABLE = "two_tank_solution_level_unavailable"
    TWO_TANK_SOLUTION_LEVEL_STALE = "two_tank_solution_level_stale"
    TWO_TANK_SOLUTION_MIN_LEVEL_UNAVAILABLE = "two_tank_solution_min_level_unavailable"
    TWO_TANK_SOLUTION_MIN_LEVEL_STALE = "two_tank_solution_min_level_stale"
    TWO_TANK_PREPARE_TARGETS_UNAVAILABLE = "two_tank_prepare_targets_unavailable"
    TWO_TANK_PREPARE_TARGETS_STALE = "two_tank_prepare_targets_stale"
    SENSOR_STATE_INCONSISTENT = "sensor_state_inconsistent"

    # Start-cycle API
    START_CYCLE_ZONE_BUSY = "start_cycle_zone_busy"
    START_CYCLE_RATE_LIMITED = "start_cycle_rate_limited"
    START_CYCLE_INTENT_NOT_FOUND = "start_cycle_intent_not_found"
    START_CYCLE_INTENT_CLAIM_UNAVAILABLE = "start_cycle_intent_claim_unavailable"
    START_CYCLE_INTENT_TERMINAL = "start_cycle_intent_terminal"
    START_CYCLE_IDEMPOTENCY_KEY_CONFLICT = "start_cycle_idempotency_key_conflict"
    START_CYCLE_MISSING_IDEMPOTENCY_KEY = "start_cycle_missing_idempotency_key"

    # API / infra
    AE3_API_UNHANDLED_EXCEPTION = "ae3_api_unhandled_exception"
    AE3_API_HTTP_5XX = "ae3_api_http_5xx"
    AE3_BACKGROUND_TASK_CRASHED = "ae3_background_task_crashed"


class Ae3LiteError(Exception):
    """Base AE3-Lite domain error."""


class SnapshotBuildError(Ae3LiteError):
    """Raised when the runtime read-model cannot build a consistent zone snapshot."""


class PlannerConfigurationError(Ae3LiteError):
    """Raised when CycleStartPlanner receives unsupported or invalid config."""


class CommandPublishError(Ae3LiteError):
    """Raised when AE3-Lite cannot publish a planned command safely."""


class CommandReconcileError(Ae3LiteError):
    """Raised when AE3-Lite cannot reconcile a waiting command safely."""


class StartupRecoveryError(Ae3LiteError):
    """Raised when AE3-Lite cannot recover in-flight startup state safely."""


class TaskFinalizeError(Ae3LiteError):
    """Raised when AE3-Lite cannot move task into a terminal state safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "ae3_task_finalize_failed").strip() or "ae3_task_finalize_failed"


class TaskClaimRollbackError(Ae3LiteError):
    """Raised when a claimed task cannot be safely returned back to pending."""


class TaskCreateError(Ae3LiteError):
    """Raised when AE3-Lite cannot create or resolve a canonical task safely."""

    def __init__(self, code: str, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = str(code or "ae3_task_create_failed").strip() or "ae3_task_create_failed"
        self.details = details if isinstance(details, dict) else {}


class TaskExecutionError(Ae3LiteError):
    """Raised when AE3-Lite runtime execution must fail closed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "ae3_task_execution_failed").strip() or "ae3_task_execution_failed"
