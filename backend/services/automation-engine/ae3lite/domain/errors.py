"""Domain errors for AE3-Lite v1."""

from __future__ import annotations


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
