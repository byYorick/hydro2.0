"""Операторский разблок зоны: fail-safe OFF, fail active task, workflow → idle.

Заменяет destructive SQL (`DELETE zone_workflow_state`) штатным AE3-путём.
Не является новым task_type: это operator control, как control-mode.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping, Optional

from ae3lite.domain.errors import ErrorCodes
from common.db import create_zone_event, fetch as _default_fetch
from common.utils.time import utcnow_naive as _utcnow

_logger = logging.getLogger(__name__)
_PID_RESET_ATTEMPTS = 2


class OperatorUnblockZoneUseCase:
    """Сбрасывает застрявшую зону в startup-required без обхода history-logger."""

    def __init__(
        self,
        *,
        task_repository: Any,
        workflow_repository: Any,
        lease_repository: Any | None = None,
        zone_intent_repository: Any | None = None,
        command_gateway: Any | None = None,
        pid_state_repository: Any | None = None,
        fetch_fn: Any = None,
    ) -> None:
        self._task_repository = task_repository
        self._workflow_repository = workflow_repository
        self._lease_repository = lease_repository
        self._zone_intent_repository = zone_intent_repository
        self._command_gateway = command_gateway
        self._pid_state_repository = pid_state_repository
        self._fetch_fn = fetch_fn or _default_fetch

    async def run(
        self,
        *,
        zone_id: int,
        now: datetime | None = None,
        source: str = "laravel_api",
        reason: str | None = None,
        user_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> dict[str, Any]:
        stamp = now or _utcnow()
        zone_id = int(zone_id)
        workflow = await self._workflow_repository.get(zone_id=zone_id)
        previous_phase = str(getattr(workflow, "workflow_phase", "") or "") if workflow is not None else ""
        previous_stage = self._extract_stage(getattr(workflow, "payload", None) if workflow is not None else None)

        get_active = getattr(self._task_repository, "get_active_for_zone", None)
        active_task = await get_active(zone_id=zone_id) if callable(get_active) else None

        failed_task_id: Optional[int] = None
        fail_safe = {"attempted": False, "success": False, "reason": "no_active_task"}
        if active_task is not None:
            failed_task_id = int(getattr(active_task, "id", 0) or 0) or None
            fail_safe = await self._fail_safe_shutdown(task=active_task, now=stamp)
            await self._fail_active_task(task=active_task, now=stamp, reason=reason)
            await self._release_lease(task=active_task, now=stamp)
            await self._fail_task_intent(task=active_task, now=stamp, reason=reason)

        failed_intents = await self._fail_remaining_intents(
            zone_id=zone_id,
            now=stamp,
            skip_intent_id=int(getattr(active_task, "intent_id", 0) or 0) if active_task is not None else 0,
            reason=reason,
        )
        await self._reset_workflow(zone_id=zone_id, workflow=workflow, now=stamp, reason=reason)
        await self._clear_correction_blocks(zone_id=zone_id)
        await self._emit_audit(
            zone_id=zone_id,
            previous_phase=previous_phase,
            previous_stage=previous_stage,
            failed_task_id=failed_task_id,
            failed_intents=failed_intents,
            fail_safe=fail_safe,
            source=source,
            reason=reason,
            user_id=user_id,
            user_role=user_role,
        )
        return {
            "zone_id": zone_id,
            "workflow_phase": "idle",
            "current_stage": "startup",
            "previous_phase": previous_phase or None,
            "previous_stage": previous_stage,
            "failed_task_id": failed_task_id,
            "failed_intent_ids": failed_intents,
            "fail_safe": fail_safe,
        }

    async def _fail_safe_shutdown(self, *, task: Any, now: datetime) -> dict[str, Any]:
        from ae3lite.application.services.correction_interrupt_safety import (
            attempt_task_fail_safe_shutdown,
        )

        try:
            result = await attempt_task_fail_safe_shutdown(
                task=task,
                now=now,
                command_gateway=self._command_gateway,
                planner_step_prefix="operator_unblock_fail_safe",
            )
        except Exception:
            _logger.warning(
                "operator_unblock: fail-safe exception task_id=%s zone_id=%s",
                getattr(task, "id", None),
                getattr(task, "zone_id", None),
                exc_info=True,
            )
            return {"attempted": True, "success": False, "reason": "exception"}
        return {
            "attempted": bool(getattr(result, "attempted", False)),
            "success": bool(getattr(result, "success", False)),
            "reason": str(getattr(result, "reason", "") or ""),
        }

    async def _fail_active_task(self, *, task: Any, now: datetime, reason: str | None) -> None:
        fail_fn = getattr(self._task_repository, "fail_for_recovery", None)
        if not callable(fail_fn):
            return
        task_id = int(getattr(task, "id", 0) or 0)
        if task_id <= 0:
            return
        message = "Оператор разблокировал зону"
        if reason:
            message = f"{message}: {reason}"
        try:
            await fail_fn(
                task_id=task_id,
                error_code=ErrorCodes.OPERATOR_UNBLOCKED,
                error_message=message,
                now=now,
            )
        except Exception:
            _logger.warning(
                "operator_unblock: fail_for_recovery failed task_id=%s",
                task_id,
                exc_info=True,
            )

    async def _release_lease(self, *, task: Any, now: datetime) -> None:
        if self._lease_repository is None:
            return
        owner = str(getattr(task, "claimed_by", "") or "").strip()
        if not owner:
            return
        release_fn = getattr(self._lease_repository, "release_if_owner_or_expired", None)
        if not callable(release_fn):
            return
        try:
            await release_fn(zone_id=int(task.zone_id), owner=owner, now=now)
        except Exception:
            _logger.warning(
                "operator_unblock: lease release failed zone_id=%s owner=%s",
                getattr(task, "zone_id", None),
                owner,
                exc_info=True,
            )

    async def _fail_task_intent(self, *, task: Any, now: datetime, reason: str | None) -> None:
        if self._zone_intent_repository is None:
            return
        intent_id = int(getattr(task, "intent_id", 0) or 0)
        if intent_id <= 0:
            return
        mark_fn = getattr(self._zone_intent_repository, "mark_terminal", None)
        if not callable(mark_fn):
            return
        try:
            await mark_fn(
                intent_id=intent_id,
                now=now,
                success=False,
                error_code=ErrorCodes.OPERATOR_UNBLOCKED,
                error_message=reason or "Оператор разблокировал зону",
            )
        except Exception:
            _logger.warning(
                "operator_unblock: intent terminal failed intent_id=%s",
                intent_id,
                exc_info=True,
            )

    async def _fail_remaining_intents(
        self,
        *,
        zone_id: int,
        now: datetime,
        skip_intent_id: int,
        reason: str | None,
    ) -> list[int]:
        if self._zone_intent_repository is None:
            return []
        mark_fn = getattr(self._zone_intent_repository, "mark_terminal", None)
        if not callable(mark_fn):
            return []
        try:
            rows = await self._fetch_fn(
                """
                SELECT id
                FROM zone_automation_intents
                WHERE zone_id = $1
                  AND status IN ('pending', 'claimed', 'running')
                ORDER BY id
                """,
                zone_id,
            )
        except Exception:
            _logger.warning(
                "operator_unblock: list active intents failed zone_id=%s",
                zone_id,
                exc_info=True,
            )
            return []
        failed: list[int] = []
        for row in rows or []:
            intent_id = int((row or {}).get("id") or 0)
            if intent_id <= 0 or intent_id == skip_intent_id:
                continue
            try:
                await mark_fn(
                    intent_id=intent_id,
                    now=now,
                    success=False,
                    error_code=ErrorCodes.OPERATOR_UNBLOCKED,
                    error_message=reason or "Оператор разблокировал зону",
                )
                failed.append(intent_id)
            except Exception:
                _logger.warning(
                    "operator_unblock: remaining intent terminal failed intent_id=%s",
                    intent_id,
                    exc_info=True,
                )
        return failed

    async def _reset_workflow(
        self,
        *,
        zone_id: int,
        workflow: Any,
        now: datetime,
        reason: str | None,
    ) -> None:
        payload: dict[str, Any] = {
            "ae3_cycle_start_stage": "startup",
            "operator_unblock": True,
            "operator_unblock_reason": reason,
        }
        scheduler_task_id = getattr(workflow, "scheduler_task_id", None) if workflow is not None else None
        await self._workflow_repository.upsert_phase(
            zone_id=zone_id,
            workflow_phase="idle",
            payload=payload,
            scheduler_task_id=scheduler_task_id,
            now=now,
        )

    async def _clear_correction_blocks(self, *, zone_id: int) -> None:
        if self._pid_state_repository is None:
            return
        last_exc: Exception | None = None
        for _attempt in range(1, _PID_RESET_ATTEMPTS + 1):
            try:
                await self._pid_state_repository.reset_no_effect_counts(zone_id=zone_id)
                return
            except Exception as exc:
                last_exc = exc
        _logger.warning(
            "operator_unblock: no_effect reset failed zone_id=%s error=%s",
            zone_id,
            last_exc,
        )

    async def _emit_audit(
        self,
        *,
        zone_id: int,
        previous_phase: str,
        previous_stage: str | None,
        failed_task_id: Optional[int],
        failed_intents: list[int],
        fail_safe: Mapping[str, Any],
        source: str,
        reason: str | None,
        user_id: Optional[int],
        user_role: Optional[str],
    ) -> None:
        details = {
            "from_phase": previous_phase or None,
            "from_stage": previous_stage,
            "to_phase": "idle",
            "to_stage": "startup",
            "failed_task_id": failed_task_id,
            "failed_intent_ids": failed_intents,
            "fail_safe": dict(fail_safe),
            "source": source,
            "reason": reason,
            "user_id": user_id,
            "user_role": user_role,
        }
        try:
            await create_zone_event(zone_id, "OPERATOR_UNBLOCKED", details)
        except Exception:
            _logger.warning(
                "operator_unblock: audit event failed zone_id=%s",
                zone_id,
                exc_info=True,
            )

    @staticmethod
    def _extract_stage(payload: Any) -> str | None:
        if not isinstance(payload, Mapping):
            return None
        stage = str(payload.get("ae3_cycle_start_stage") or "").strip()
        return stage or None
