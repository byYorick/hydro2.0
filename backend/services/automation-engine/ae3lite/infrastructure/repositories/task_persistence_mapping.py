"""PgAutomationTaskRepository mapping: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

import asyncpg

from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.infrastructure.repositories.task_persistence_shared import CORRECTION_OPTIONAL_FIELDS


@dataclass(frozen=True)
class TaskPersistenceMappingPorts:
    pass


class TaskPersistenceMapping:
    def __init__(self, ports: TaskPersistenceMappingPorts) -> None:
        self._ports = ports

    def normalize_timestamp(self, value: datetime) -> datetime:
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
        return normalized.replace(microsecond=0)

    def normalize_meta(self, value: Mapping[str, Any] | None) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    def normalize_json_mapping(self, value: Mapping[str, Any] | None) -> dict[str, Any] | None:
        return dict(value) if isinstance(value, Mapping) else None

    def task_from_row(self, row: asyncpg.Record | None) -> AutomationTask | None:
        return AutomationTask.from_row(row) if row is not None else None

    @staticmethod
    def db_axis_max_attempts(value: Any) -> int | None:
        """Map domain max-attempts to DB CHECK (NULL OR >= 1).

        Domain uses ``0`` for a disabled correction axis (irrigation pH-only →
        ``ec_max_attempts=0``, fill Ca-only → ``ph_max_attempts=0``). PostgreSQL
        rejects ``0`` via ``ae_tasks_corr_{ec,ph}_max_attempts_check``; persist
        ``NULL`` instead. Readers map NULL → 0 via ``int(... or 0)``.
        """
        if value is None:
            return None
        try:
            n = int(value)
        except (TypeError, ValueError):
            return None
        return None if n <= 0 else n

    def correction_values(self, correction: CorrectionState | None) -> tuple[Any, ...]:
        if correction is None:
            # Поддерживать согласованность NOT NULL колонок коррекции, когда коррекция неактивна.
            # Некоторые поля БД, например `corr_ec_current_seq_index`, имеют NOT NULL и default.
            values: list[Any] = [None] * len(CORRECTION_OPTIONAL_FIELDS)
            for field_name, default in (
                ("ec_current_seq_index", 0),
                ("dilute_attempts", 0),
                ("ec_pid_frozen", False),
            ):
                try:
                    idx = CORRECTION_OPTIONAL_FIELDS.index(field_name)
                    values[idx] = default
                except ValueError:
                    pass
            return (*tuple(values), False)

        values_list: list[Any] = []
        for field_name in CORRECTION_OPTIONAL_FIELDS:
            raw = getattr(correction, field_name)
            if field_name in {"ec_max_attempts", "ph_max_attempts"}:
                values_list.append(self.db_axis_max_attempts(raw))
            else:
                values_list.append(raw)
        return (*tuple(values_list), bool(correction.limit_policy_logged))
