"""Сохраняет control mode зоны и синхронизирует snapshot активной задачи AE3.

См. doc_ai/06_DOMAIN_ZONES_RECIPES/CONTROL_MODES_SPEC.md §6.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from ae3lite.application.use_cases.manual_control_contract import normalize_control_mode
from common.db import create_zone_event, execute

logger = logging.getLogger(__name__)


class SetControlModeUseCase:
    """Обновляет `zones.control_mode` с audit, cancel active task и reconcile flag.

    Правила (§6 spec):
    - Любой переход пишет `CONTROL_MODE_CHANGED` zone event.
    - `* → manual`: активная task помечается failed с
      `error_code=control_mode_switched_to_manual` (graceful stop команд уже
      должен был отправить UI / scheduler до вызова).
    - `manual → auto|semi`: ставит флаг `needs_manual_to_auto_reconcile` через
      `zones.automation_runtime_state` (AE3 runtime подхватит и принудительно
      пройдёт `manual_to_auto_cleanup` → `startup` при следующем tick).
    """

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
        user_id: Optional[int] = None,
        user_role: Optional[str] = None,
        source: str = "api",
        reason: Optional[str] = None,
    ) -> str:
        normalized_control_mode = normalize_control_mode(control_mode)

        previous_mode = await self._fetch_current_mode(zone_id=zone_id)
        if previous_mode == normalized_control_mode:
            return normalized_control_mode

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

        active_task_id: Optional[int] = None
        active_task_action = "none"
        get_active = getattr(self._task_repository, "get_active_for_zone", None)
        active_task = await get_active(zone_id=zone_id) if callable(get_active) else None
        if active_task is not None:
            active_task_id = int(getattr(active_task, "id", 0) or 0) or None

            if normalized_control_mode == "manual" and previous_mode in {"auto", "semi"}:
                fail_fn = getattr(self._task_repository, "fail_for_recovery", None)
                if callable(fail_fn):
                    try:
                        await fail_fn(
                            task_id=active_task_id,
                            error_code="control_mode_switched_to_manual",
                            error_message=(
                                f"Active task {active_task_id} cancelled due to control_mode change "
                                f"from {previous_mode} to manual"
                            ),
                            now=now,
                        )
                        active_task_action = "cancelled"
                    except Exception:
                        logger.warning(
                            "AE3 set_control_mode: не смог прервать task %s при switch в manual",
                            active_task_id,
                            exc_info=True,
                        )
                        active_task_action = "cancel_failed"

        # При возврате из manual ставим reconcile-флаг, чтобы runtime прошёл cleanup.
        needs_reconcile = (
            previous_mode == "manual"
            and normalized_control_mode in {"auto", "semi"}
        )
        if needs_reconcile:
            await self._mark_needs_manual_to_auto_reconcile(zone_id=zone_id)

        await self._emit_audit_event(
            zone_id=zone_id,
            previous_mode=previous_mode,
            new_mode=normalized_control_mode,
            user_id=user_id,
            user_role=user_role,
            source=source,
            reason=reason,
            active_task_id=active_task_id,
            active_task_action=active_task_action,
            needs_reconcile=needs_reconcile,
        )

        return normalized_control_mode

    async def _fetch_current_mode(self, *, zone_id: int) -> str:
        from common.db import fetch

        rows = await fetch(
            "SELECT control_mode FROM zones WHERE id = $1",
            zone_id,
        )
        if not rows:
            return ""
        return str(rows[0].get("control_mode") or "").strip().lower()

    async def _mark_needs_manual_to_auto_reconcile(self, *, zone_id: int) -> None:
        """Ставит reconcile flag в `zones.settings->manual_to_auto_reconcile_pending`.

        Runtime AE3 при следующем tick'е читает этот флаг и принудительно
        запускает двухстадийный reconcile (`manual_to_auto_cleanup` → `startup`).
        Использовать settings JSONB (nullable по миграции zones) чтобы не
        плодить новые колонки и связанные миграции.
        """
        await self._execute_fn(
            """
            UPDATE zones
            SET settings = COALESCE(settings, '{}'::jsonb) || jsonb_build_object(
                'manual_to_auto_reconcile_pending', true,
                'manual_to_auto_reconcile_requested_at', extract(epoch from NOW())::bigint
            ),
                updated_at = NOW()
            WHERE id = $1
            """,
            zone_id,
        )

    async def _emit_audit_event(
        self,
        *,
        zone_id: int,
        previous_mode: str,
        new_mode: str,
        user_id: Optional[int],
        user_role: Optional[str],
        source: str,
        reason: Optional[str],
        active_task_id: Optional[int],
        active_task_action: str,
        needs_reconcile: bool,
    ) -> None:
        details = {
            "from": previous_mode or None,
            "to": new_mode,
            "user_id": user_id,
            "user_role": user_role,
            "source": source,
            "reason": reason,
            "active_task_id": active_task_id,
            "active_task_action": active_task_action,
            "needs_manual_to_auto_reconcile": bool(needs_reconcile),
        }
        try:
            await create_zone_event(zone_id, "CONTROL_MODE_CHANGED", details)
        except Exception:
            logger.warning(
                "AE3 set_control_mode: не смог записать CONTROL_MODE_CHANGED zone_id=%s",
                zone_id,
                exc_info=True,
            )


__all__ = ["SetControlModeUseCase"]
