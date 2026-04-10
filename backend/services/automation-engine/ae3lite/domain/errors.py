"""Доменные ошибки AE3-Lite v1."""

from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    """Канонические значения `ae_tasks.status`.

    Примесь ``str`` позволяет прозрачно сравнивать enum с обычными строками:
        task.status == TaskStatus.COMPLETED  →  True  (когда task.status == "completed")
    """

    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    WAITING_COMMAND = "waiting_command"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

    @property
    def is_active(self) -> bool:
        return self in (
            TaskStatus.CLAIMED,
            TaskStatus.RUNNING,
            TaskStatus.WAITING_COMMAND,
        )


class IntentStatus(str, Enum):
    """Канонические значения `zone_automation_intents.status`."""

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
    """Централизованный реестр строковых error code для AE3-Lite.

    Используйте эти константы вместо inline-литералов, чтобы сохранять
    единообразие и удобную навигацию по коду в IDE.

    Пример::
        raise TaskExecutionError(ErrorCodes.AE3_UNKNOWN_HANDLER, "Не найден handler для stage X")
    """

    # Жизненный цикл задачи
    AE3_TASK_EXECUTION_FAILED = "ae3_task_execution_failed"
    AE3_TASK_EXECUTION_UNHANDLED_EXCEPTION = "ae3_task_execution_unhandled_exception"
    AE3_TASK_FINALIZE_FAILED = "ae3_task_finalize_failed"
    AE3_TASK_CREATE_FAILED = "ae3_task_create_failed"
    AE3_TASK_COMPLETE_FAILED = "ae3_task_complete_failed"
    AE3_TASK_MISSING_OWNER = "ae3_task_missing_owner"

    # Переходы между stage
    AE3_UNKNOWN_HANDLER = "ae3_unknown_handler"
    AE3_UNKNOWN_OUTCOME_KIND = "ae3_unknown_outcome_kind"
    AE3_TRANSITION_NO_NEXT_STAGE = "ae3_transition_no_next_stage"
    AE3_COMMAND_NO_ROUTING = "ae3_command_no_routing"
    AE3_ENTER_CORRECTION_NO_STATE = "ae3_enter_correction_no_state"
    AE3_UNKNOWN_CORR_STEP = "ae3_unknown_corr_step"
    AE3_STAGE_FAILED = "ae3_stage_failed"
    AE3_EMPTY_COMMAND_PLAN = "ae3_empty_command_plan"

    # Snapshot / read-model
    AE3_SNAPSHOT_BUILD_FAILED = "ae3_snapshot_build_failed"
    AE3_SNAPSHOT_ZONE_NOT_FOUND = "ae3_snapshot_zone_not_found"
    AE3_SNAPSHOT_NO_ACTIVE_GROW_CYCLE = "ae3_snapshot_no_active_grow_cycle"
    AE3_SNAPSHOT_MISSING_CURRENT_PHASE = "ae3_snapshot_missing_current_phase"
    AE3_SNAPSHOT_BUNDLE_MISSING = "ae3_snapshot_bundle_missing"
    AE3_SNAPSHOT_BUNDLE_INVALID = "ae3_snapshot_bundle_invalid"
    AE3_SNAPSHOT_ZONE_BUNDLE_MISSING = "ae3_snapshot_zone_bundle_missing"
    AE3_SNAPSHOT_LOGIC_PROFILE_BUNDLE_MISSING = "ae3_snapshot_logic_profile_bundle_missing"
    AE3_SNAPSHOT_ACTIVE_LOGIC_PROFILE_MISSING = "ae3_snapshot_active_logic_profile_missing"
    AE3_SNAPSHOT_EMPTY_COMMAND_PLANS = "ae3_snapshot_empty_command_plans"
    AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS = "ae3_snapshot_no_online_actuator_channels"
    AE3_SNAPSHOT_CONFLICTING_CONFIG_VALUES = "ae3_snapshot_conflicting_config_values"

    # Отправка и reconcile команд
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
    # Параллельная очистка удалила `ae_tasks`, пока publish pipeline ещё выполнялся.
    # Это симметрично случаю с пропавшей задачей в `finalize_task`.
    AE3_TASK_MISSING_DURING_PUBLISH = "task_missing_during_publish"

    # Состояние IRR
    IRR_STATE_UNAVAILABLE = "irr_state_unavailable"
    IRR_STATE_STALE = "irr_state_stale"
    IRR_STATE_MISMATCH = "irr_state_mismatch"

    # Датчики уровня / баки
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

    # API запуска цикла
    START_CYCLE_ZONE_BUSY = "start_cycle_zone_busy"
    START_CYCLE_RATE_LIMITED = "start_cycle_rate_limited"
    START_CYCLE_INTENT_NOT_FOUND = "start_cycle_intent_not_found"
    START_CYCLE_INTENT_CLAIM_UNAVAILABLE = "start_cycle_intent_claim_unavailable"
    START_CYCLE_INTENT_TERMINAL = "start_cycle_intent_terminal"
    START_CYCLE_IDEMPOTENCY_KEY_CONFLICT = "start_cycle_idempotency_key_conflict"
    START_CYCLE_MISSING_IDEMPOTENCY_KEY = "start_cycle_missing_idempotency_key"
    START_CYCLE_BLOCKED_BY_ALERT = "start_cycle_blocked_by_alert"

    # API / инфраструктура
    AE3_API_UNHANDLED_EXCEPTION = "ae3_api_unhandled_exception"
    AE3_API_HTTP_5XX = "ae3_api_http_5xx"
    AE3_BACKGROUND_TASK_CRASHED = "ae3_background_task_crashed"

    # Критические защитные проверки конфигурации
    ZONE_CORRECTION_CONFIG_MISSING_CRITICAL = "zone_correction_config_missing_critical"
    ZONE_DOSING_CALIBRATION_MISSING_CRITICAL = "zone_dosing_calibration_missing_critical"
    ZONE_PID_CONFIG_MISSING_CRITICAL = "zone_pid_config_missing_critical"
    ZONE_RECIPE_PHASE_TARGETS_MISSING_CRITICAL = "zone_recipe_phase_targets_missing_critical"


class Ae3LiteError(Exception):
    """Базовая доменная ошибка AE3-Lite."""


class SnapshotBuildError(Ae3LiteError):
    """Выбрасывается, когда runtime read-model не может собрать согласованный snapshot зоны."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        normalized = str(code or ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED).strip()
        self.code = normalized or ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED
        self.details = details if isinstance(details, dict) else {}


class PlannerConfigurationError(Ae3LiteError):
    """Выбрасывается, когда CycleStartPlanner получает неподдерживаемую или некорректную конфигурацию."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        normalized = str(code or "").strip()
        if normalized:
            self.code = normalized


class CommandPublishError(Ae3LiteError):
    """Выбрасывается, когда AE3-Lite не может безопасно опубликовать planned command."""


class StartupRecoveryError(Ae3LiteError):
    """Выбрасывается, когда AE3-Lite не может безопасно восстановить in-flight состояние после старта."""


class TaskFinalizeError(Ae3LiteError):
    """Выбрасывается, когда AE3-Lite не может безопасно перевести задачу в terminal state."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "ae3_task_finalize_failed").strip() or "ae3_task_finalize_failed"


class TaskClaimRollbackError(Ae3LiteError):
    """Выбрасывается, когда claimed-задачу нельзя безопасно вернуть в pending."""


class TaskCreateError(Ae3LiteError):
    """Выбрасывается, когда AE3-Lite не может безопасно создать или разрешить canonical task."""

    def __init__(self, code: str, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = str(code or "ae3_task_create_failed").strip() or "ae3_task_create_failed"
        self.details = details if isinstance(details, dict) else {}


class TaskExecutionError(Ae3LiteError):
    """Выбрасывается, когда выполнение AE3-Lite должно завершиться по fail-closed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "ae3_task_execution_failed").strip() or "ae3_task_execution_failed"


class TaskTerminalStateReached(Ae3LiteError):
    """Выбрасывается, когда задача становится terminal извне во время reconcile команды."""

    def __init__(self, *, task: object, message: str) -> None:
        super().__init__(message)
        self.task = task


class ManualControlError(Ae3LiteError):
    """Выбрасывается, когда API manual control/control-mode должно отклонить запрос."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = str(code or "manual_control_error").strip() or "manual_control_error"
        self.status_code = int(status_code or 409)
        self.details = details if isinstance(details, dict) else {}
