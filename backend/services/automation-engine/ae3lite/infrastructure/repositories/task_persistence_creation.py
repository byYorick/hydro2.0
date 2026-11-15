"""PgAutomationTaskRepository creation: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

import asyncpg

from ae3lite.domain.entities import AutomationTask


@dataclass(frozen=True)
class TaskPersistenceCreationPorts:
    fetchrow: Callable[..., Awaitable[Any]]
    normalize_json_mapping: Callable[..., Any]
    normalize_meta: Callable[..., Any]
    normalize_timestamp: Callable[..., Any]
    task_from_row: Callable[..., Any]


class TaskPersistenceCreation:
    def __init__(self, ports: TaskPersistenceCreationPorts) -> None:
        self._ports = ports

    async def create_pending(
        self,
        *,
        zone_id: int,
        idempotency_key: str,
        task_type: str,
        topology: str,
        current_stage: str,
        workflow_phase: str,
        intent_source: str | None = None,
        intent_trigger: str | None = None,
        intent_id: int | None = None,
        intent_meta: Mapping[str, Any] | None = None,
        scheduled_for: datetime,
        due_at: datetime,
        now: datetime,
        irrigation_mode: str | None = None,
        irrigation_requested_duration_sec: int | None = None,
        irrigation_decision_strategy: str | None = None,
        irrigation_decision_config: Mapping[str, Any] | None = None,
        irrigation_bundle_revision: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> AutomationTask | None:
        normalized_scheduled_for = self._ports.normalize_timestamp(scheduled_for)
        normalized_due_at = self._ports.normalize_timestamp(due_at)
        normalized_now = self._ports.normalize_timestamp(now)
        normalized_meta = self._ports.normalize_meta(intent_meta)
        normalized_decision_config = self._ports.normalize_json_mapping(irrigation_decision_config)

        try:
            row = await self._ports.fetchrow(
                """
                INSERT INTO ae_tasks (
                    zone_id, task_type, status, idempotency_key,
                    topology, current_stage, workflow_phase,
                    control_mode_snapshot,
                    irrigation_mode, irrigation_requested_duration_sec,
                    irrigation_decision_strategy, irrigation_decision_config, irrigation_bundle_revision,
                    intent_source, intent_trigger, intent_id, intent_meta,
                    scheduled_for, due_at, stage_entered_at,
                    created_at, updated_at
                )
                VALUES (
                    $1, $2, 'pending', $3,
                    $4, $5, $6,
                    (SELECT control_mode FROM zones WHERE id = $1),
                    $7, $8, $9, $10::jsonb, $11,
                    $12, $13, $14, $15::jsonb,
                    $16, $17, $18,
                    $18, $18
                )
                RETURNING *
                """,
                zone_id,
                task_type,
                idempotency_key,
                topology,
                current_stage,
                workflow_phase,
                irrigation_mode,
                irrigation_requested_duration_sec,
                irrigation_decision_strategy,
                normalized_decision_config,
                irrigation_bundle_revision,
                intent_source,
                intent_trigger,
                intent_id,
                normalized_meta,
                normalized_scheduled_for,
                normalized_due_at,
                normalized_now,
                conn=conn,
            )
        except asyncpg.UniqueViolationError:
            return None

        return self._ports.task_from_row(row)

    async def update_irrigation_runtime(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        irrigation_mode: str | None = None,
        irrigation_requested_duration_sec: int | None = None,
        irrigation_decision_strategy: str | None = None,
        irrigation_decision_config: Mapping[str, Any] | None = None,
        irrigation_bundle_revision: str | None = None,
        irrigation_decision_outcome: str | None = None,
        irrigation_decision_reason_code: str | None = None,
        irrigation_decision_degraded: bool | None = None,
        irrigation_replay_count: int | None = None,
        irrigation_wait_ready_deadline_at: datetime | None = None,
        irrigation_setup_deadline_at: datetime | None = None,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        normalized_now = self._ports.normalize_timestamp(now)
        normalized_wait_ready_deadline_at = (
            self._ports.normalize_timestamp(irrigation_wait_ready_deadline_at)
            if irrigation_wait_ready_deadline_at is not None
            else None
        )
        normalized_setup_deadline_at = (
            self._ports.normalize_timestamp(irrigation_setup_deadline_at)
            if irrigation_setup_deadline_at is not None
            else None
        )
        normalized_decision_config = self._ports.normalize_json_mapping(irrigation_decision_config)
        row = await self._ports.fetchrow(
            """
            UPDATE ae_tasks
            SET irrigation_mode = COALESCE($3, irrigation_mode),
                irrigation_requested_duration_sec = COALESCE($4, irrigation_requested_duration_sec),
                irrigation_decision_strategy = COALESCE($5, irrigation_decision_strategy),
                irrigation_decision_config = COALESCE($6::jsonb, irrigation_decision_config),
                irrigation_bundle_revision = COALESCE($7, irrigation_bundle_revision),
                irrigation_decision_outcome = COALESCE($8, irrigation_decision_outcome),
                irrigation_decision_reason_code = COALESCE($9, irrigation_decision_reason_code),
                irrigation_decision_degraded = CASE
                    WHEN $10::boolean IS NULL THEN irrigation_decision_degraded
                    ELSE $10
                END,
                irrigation_replay_count = COALESCE($11, irrigation_replay_count),
                irrigation_wait_ready_deadline_at = CASE
                    WHEN $12::timestamptz IS NULL THEN irrigation_wait_ready_deadline_at
                    ELSE $12
                END,
                irrigation_setup_deadline_at = CASE
                    WHEN $13::timestamptz IS NULL THEN irrigation_setup_deadline_at
                    ELSE $13
                END,
                updated_at = $14
            WHERE id = $1
              AND claimed_by = $2
              AND claim_generation = $15
              AND status IN ('claimed', 'running', 'waiting_command')
            RETURNING *
            """,
            task_id,
            owner,
            irrigation_mode,
            irrigation_requested_duration_sec,
            irrigation_decision_strategy,
            normalized_decision_config,
            irrigation_bundle_revision,
            irrigation_decision_outcome,
            irrigation_decision_reason_code,
            irrigation_decision_degraded,
            irrigation_replay_count,
            normalized_wait_ready_deadline_at,
            normalized_setup_deadline_at,
            normalized_now,
            int(claim_generation),
        )
        return self._ports.task_from_row(row)
