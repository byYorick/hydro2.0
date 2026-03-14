"""Persist control mode for a zone and sync active AE3 task snapshot."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ae3lite.application.use_cases.manual_control_contract import normalize_control_mode
from common.db import execute


class SetControlModeUseCase:
    """Update zones.control_mode and keep the active task snapshot in sync."""

    def __init__(
        self,
        *,
        task_repository: Any,
        execute_fn: Any = execute,
    ) -> None:
        self._task_repository = task_repository
        self._execute_fn = execute_fn

    async def run(
        self,
        *,
        zone_id: int,
        control_mode: str,
        now: datetime,
    ) -> str:
        normalized_control_mode = normalize_control_mode(control_mode)
        await self._execute_fn(
            """
            UPDATE zones
            SET control_mode = $2,
                updated_at = NOW()
            WHERE id = $1
            """,
            zone_id,
            normalized_control_mode,
        )
        await self._task_repository.update_control_mode_snapshot_for_zone(
            zone_id=zone_id,
            control_mode=normalized_control_mode,
            now=now,
        )
        return normalized_control_mode


__all__ = ["SetControlModeUseCase"]
