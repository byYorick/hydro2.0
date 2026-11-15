"""Создаёт или разрешает каноническую задачу AE3-Lite из scheduler intent."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from ae3lite.application.dto import TaskCreationResult
from ae3lite.application.level_monitor import load_zone_level_monitor_config, solution_topup_need_active
from ae3lite.domain.errors import ErrorCodes, SnapshotBuildError, TaskCreateError
from ae3lite.infrastructure.metrics import TASK_CREATED
from ae3lite.infrastructure.read_models.active_grow_cycle_order_sql import SQL_ACTIVE_GROW_CYCLE_ORDER_BY
from common.db import get_pool
from common.trace_context import get_trace_id


from ae3lite.application.services.intent_task_creation import IntentTaskCreation, IntentTaskCreationPorts
from ae3lite.application.services.intent_task_admission import IntentTaskAdmission, IntentTaskAdmissionPorts
from ae3lite.application.services.intent_task_irrigation_decision import (
    IntentTaskIrrigationDecision,
    IntentTaskIrrigationDecisionPorts,
)
from ae3lite.application.services.intent_task_topup import IntentTaskTopup, IntentTaskTopupPorts
from ae3lite.application.services.intent_task_solution_change import (
    IntentTaskSolutionChange,
    IntentTaskSolutionChangePorts,
)
from ae3lite.application.services.intent_task_payload import IntentTaskPayload, IntentTaskPayloadPorts


class CreateTaskFromIntentUseCase:
    """Создаёт каноническую задачу AE3 v2, сохраняя внешнюю семантику idempotency.

    Использует advisory lock PostgreSQL (`pg_try_advisory_xact_lock`) на `zone_id`,
    чтобы предотвратить дублирующее создание задачи при конкурентных запросах.
    """

    HARD_BLOCKING_ALERT_CODES = frozenset(
        {
            "biz_zone_correction_config_missing",
            "biz_zone_dosing_calibration_missing",
        }
    )

    def __init__(
        self,
        *,
        task_repository: Any,
        zone_lease_repository: Any,
        zone_intent_repository: Any,
        zone_alert_repository: Any | None = None,
    ) -> None:
        self._task_repository = task_repository
        self._zone_lease_repository = zone_lease_repository
        self._zone_intent_repository = zone_intent_repository
        self._zone_alert_repository = zone_alert_repository
        self._intent_task_creation = IntentTaskCreation(
            IntentTaskCreationPorts(
                assert_required_nodes_available_for_task=lambda *args, **kwargs: (
                    self._assert_required_nodes_available_for_task(*args, **kwargs)
                ),
                ensure_runtime_cycle_preconditions=lambda *args, **kwargs: self._ensure_runtime_cycle_preconditions(
                    *args, **kwargs
                ),
                ensure_solution_change_preconditions=lambda *args, **kwargs: self._ensure_solution_change_preconditions(
                    *args, **kwargs
                ),
                ensure_solution_topup_preconditions=lambda *args, **kwargs: self._ensure_solution_topup_preconditions(
                    *args, **kwargs
                ),
                find_blocking_alert=lambda *args, **kwargs: self._find_blocking_alert(*args, **kwargs),
                merge_lighting_tick_intent_payload=lambda *args, **kwargs: self._merge_lighting_tick_intent_payload(
                    *args, **kwargs
                ),
                merge_solution_topup_intent_payload=lambda *args, **kwargs: self._merge_solution_topup_intent_payload(
                    *args, **kwargs
                ),
                normalize_utc=lambda *args, **kwargs: self._normalize_utc(*args, **kwargs),
                resolve_irrigation_decision_snapshot=lambda *args, **kwargs: self._resolve_irrigation_decision_snapshot(
                    *args, **kwargs
                ),
                task_repository=lambda: self._task_repository,
                zone_intent_repository=lambda: self._zone_intent_repository,
                zone_lease_repository=lambda: self._zone_lease_repository,
                global_task_created=lambda: TASK_CREATED,
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
                global_get_trace_id=lambda *args, **kwargs: get_trace_id(*args, **kwargs),
            )
        )
        self._intent_task_admission = IntentTaskAdmission(
            IntentTaskAdmissionPorts(
                hard_blocking_alert_codes=lambda: self.HARD_BLOCKING_ALERT_CODES,
                zone_alert_repository=lambda: self._zone_alert_repository,
            )
        )
        self._intent_task_irrigation_decision = IntentTaskIrrigationDecision(IntentTaskIrrigationDecisionPorts())
        self._intent_task_topup = IntentTaskTopup(
            IntentTaskTopupPorts(
                normalize_utc=lambda *args, **kwargs: self._normalize_utc(*args, **kwargs),
            )
        )
        self._intent_task_solution_change = IntentTaskSolutionChange(IntentTaskSolutionChangePorts())
        self._intent_task_payload = IntentTaskPayload(IntentTaskPayloadPorts())

    async def run(
        self,
        *,
        zone_id: int,
        source: str,
        idempotency_key: str,
        intent_row: Mapping[str, Any],
        now: datetime,
        allow_create: bool = True,
        lighting_desired_state: str | None = None,
        lighting_brightness_pct: int | None = None,
        solution_topup_mode: str | None = None,
        solution_topup_trigger: str | None = None,
    ) -> TaskCreationResult:
        return await self._intent_task_creation.run(
            zone_id=zone_id,
            source=source,
            idempotency_key=idempotency_key,
            intent_row=intent_row,
            now=now,
            allow_create=allow_create,
            lighting_desired_state=lighting_desired_state,
            lighting_brightness_pct=lighting_brightness_pct,
            solution_topup_mode=solution_topup_mode,
            solution_topup_trigger=solution_topup_trigger,
        )

    async def _assert_required_nodes_available_for_task(
        self,
        *,
        zone_id: int,
        topology: str,
        conn: Any,
        task_type: str | None = None,
        current_stage: str | None = None,
    ) -> None:
        return await self._intent_task_admission.assert_required_nodes_available_for_task(
            zone_id=zone_id, topology=topology, conn=conn, task_type=task_type, current_stage=current_stage
        )

    async def _find_blocking_alert(self, *, zone_id: int, conn: Any | None = None) -> dict[str, Any] | None:
        return await self._intent_task_admission.find_blocking_alert(zone_id=zone_id, conn=conn)

    async def _ensure_runtime_cycle_preconditions(
        self,
        *,
        zone_id: int,
        meta: Any,
        conn: Any,
    ) -> None:
        return await self._intent_task_admission.ensure_runtime_cycle_preconditions(
            zone_id=zone_id, meta=meta, conn=conn
        )

    async def _resolve_irrigation_decision_snapshot(
        self,
        *,
        zone_id: int,
        meta: Any,
        conn: Any,
    ) -> dict[str, Any]:
        return await self._intent_task_irrigation_decision.resolve_irrigation_decision_snapshot(
            zone_id=zone_id, meta=meta, conn=conn
        )

    def _normalize_utc(self, value: datetime) -> datetime:
        return self._intent_task_irrigation_decision.normalize_utc(value=value)

    async def _ensure_solution_topup_preconditions(
        self,
        *,
        zone_id: int,
        meta: Any,
        conn: Any,
        now: datetime,
    ) -> None:
        return await self._intent_task_topup.ensure_solution_topup_preconditions(
            zone_id=zone_id, meta=meta, conn=conn, now=now
        )

    async def _ensure_solution_change_preconditions(
        self,
        *,
        zone_id: int,
        meta: Any,
        conn: Any,
    ) -> None:
        return await self._intent_task_solution_change.ensure_solution_change_preconditions(
            zone_id=zone_id, meta=meta, conn=conn
        )

    async def _resolve_solution_change_enabled_from_bundle(self, *, zone_id: int, conn: Any) -> bool:
        return await self._intent_task_solution_change.resolve_solution_change_enabled_from_bundle(
            zone_id=zone_id, conn=conn
        )

    def _merge_solution_topup_intent_payload(
        self,
        *,
        intent_meta: dict[str, Any],
        solution_topup_mode: str | None,
        solution_topup_trigger: str | None,
    ) -> dict[str, Any]:
        return self._intent_task_payload.merge_solution_topup_intent_payload(
            intent_meta=intent_meta,
            solution_topup_mode=solution_topup_mode,
            solution_topup_trigger=solution_topup_trigger,
        )

    def _merge_lighting_tick_intent_payload(
        self,
        *,
        intent_meta: dict[str, Any],
        lighting_desired_state: str | None,
        lighting_brightness_pct: int | None,
    ) -> dict[str, Any]:
        return self._intent_task_payload.merge_lighting_tick_intent_payload(
            intent_meta=intent_meta,
            lighting_desired_state=lighting_desired_state,
            lighting_brightness_pct=lighting_brightness_pct,
        )
