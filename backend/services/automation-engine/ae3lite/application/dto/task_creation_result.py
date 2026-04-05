"""DTO результата создания канонической задачи AE3-Lite из legacy ingress."""

from __future__ import annotations

from dataclasses import dataclass

from ae3lite.domain.entities import AutomationTask


@dataclass(frozen=True)
class TaskCreationResult:
    """Описывает, была ли каноническая задача AE3 создана заново или дедуплицирована."""

    task: AutomationTask
    created: bool
