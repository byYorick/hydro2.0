"""DTO результата stage, возвращаемого handler-классами."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, Tuple

from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState


@dataclass(frozen=True)
class StageOutcome:
    """Объект значения, которым stage handler описывает результат выполнения.

    Поле ``kind`` определяет, как :class:`WorkflowRouter` интерпретирует outcome:

    * ``poll`` — остаться на текущем stage и переочередить задачу с *due_delay_sec*.
    * ``transition`` — перейти в *next_stage* и очистить состояние коррекции.
    * ``enter_correction`` — начать или продолжить коррекцию, оставаясь на текущем stage.
    * ``exit_correction`` — завершить коррекцию и перейти в *next_stage*.
    * ``complete`` — пометить задачу завершённой.
    * ``fail`` — пометить задачу как failed с *error_code* / *error_message*.
    """

    kind: Literal[
        "poll",
        "transition",
        "enter_correction",
        "exit_correction",
        "complete",
        "fail",
    ]

    next_stage: Optional[str] = None
    due_delay_sec: float = 0

    # Переопределения workflow state, применяемые при переходе
    stage_retry_count: Optional[int] = None
    clean_fill_cycle: Optional[int] = None

    # Состояние коррекции, задаётся при enter_correction / exit_correction
    correction: Optional[CorrectionState] = None

    # Информация об ошибке, задаётся при fail
    error_code: Optional[str] = None
    error_message: Optional[str] = None
