"""climate tick completion: explicit dependencies and invocation data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from ae3lite.greenhouse_climate.decision_engine import ClimateDecision
from ae3lite.infrastructure.clients import HistoryLoggerClient


@dataclass(frozen=True)
class ClimateTickCompletionPorts:
    lease_lost_status: Callable[..., Any]
    load_manual_override: Callable[..., Any]
    lock_owned_greenhouse_lease: Callable[..., Any]
    publish_greenhouse_alert_lifecycle: Callable[..., Any]
    record_tick_metric: Callable[..., Any]
    unique_alert_codes: Callable[..., Any]
    get_pool: Callable[..., Any]
    logger: Callable[..., Any]


class ClimateTickCompletion:
    def __init__(self, ports: ClimateTickCompletionPorts) -> None:
        self._ports = ports

    async def complete_missing_bundle(
        self, *, greenhouse_id: int, lease_owner: str, intent_id: int, task_id: int | None, tick_started: float
    ) -> Any:
        pool = await self._ports.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                if not await self._ports.lock_owned_greenhouse_lease(
                    conn, greenhouse_id=greenhouse_id, owner=lease_owner
                ):
                    self._ports.record_tick_metric(tick_started, "failed")
                    return {
                        "status": "failed",
                        "error_code": "greenhouse_climate_lease_lost",
                        "greenhouse_id": greenhouse_id,
                    }
                intent_update = await conn.execute(
                    """
                    UPDATE greenhouse_automation_intents
                    SET status = 'failed', completed_at = now(), updated_at = now(),
                        error_code = 'greenhouse_bundle_missing', error_message = 'No valid automation bundle'
                    WHERE id = $1 AND status = 'running'
                    """,
                    intent_id,
                )
                if intent_update != "UPDATE 1":
                    raise RuntimeError("greenhouse_climate_intent_transition_failed")
                if task_id is not None:
                    task_update = await conn.execute(
                        """
                        UPDATE greenhouse_automation_tasks
                        SET status = 'failed',
                            workflow_stage = 'bundle_load',
                            error_code = 'greenhouse_bundle_missing',
                            error_message = 'No valid automation bundle',
                            completed_at = now(),
                            updated_at = now()
                        WHERE id = $1 AND status IN ('claimed', 'running', 'waiting_command')
                        """,
                        task_id,
                    )
                    if task_update != "UPDATE 1":
                        raise RuntimeError("greenhouse_climate_task_transition_failed")
        self._ports.record_tick_metric(tick_started, "failed")
        return {"status": "failed", "reason": "bundle_missing", "greenhouse_id": greenhouse_id}

    async def complete_disabled_tick(
        self,
        *,
        greenhouse_id: int,
        lease_owner: str,
        intent_id: int,
        task_id: int | None,
        tick_started: float,
        state: Mapping[str, Any],
        control_mode: str,
        alert_publisher: Any,
    ) -> Any:
        override = await self._ports.load_manual_override(greenhouse_id)
        active_override_id = int(override.get("id")) if isinstance(override, dict) and override.get("id") else None
        next_tick_idle = datetime.now(timezone.utc) + timedelta(hours=1)
        current_left = int(state.get("left_position_pct") or 0)
        current_right = int(state.get("right_position_pct") or 0)
        factors = {"enabled": False, "control_mode": control_mode}
        pool = await self._ports.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                if not await self._ports.lock_owned_greenhouse_lease(
                    conn, greenhouse_id=greenhouse_id, owner=lease_owner
                ):
                    self._ports.record_tick_metric(tick_started, "failed")
                    return {
                        "status": "failed",
                        "error_code": "greenhouse_climate_lease_lost",
                        "greenhouse_id": greenhouse_id,
                    }
                state_update = await conn.execute(
                    """
                    UPDATE greenhouse_automation_state
                    SET climate_enabled = false,
                        control_mode = $8,
                        recommended_left_position_pct = $2,
                        recommended_right_position_pct = $3,
                        decision_reason = 'climate_disabled',
                        decision_factors = $4::jsonb,
                        weather_fresh = false,
                        inside_climate_fresh = false,
                        active_alerts_summary = '[]'::jsonb,
                        last_decision_at = now(),
                        next_scheduled_tick_at = $5,
                        active_manual_override_id = $6,
                        last_task_id = $7,
                        last_error_code = NULL,
                        last_error_message = NULL,
                        updated_at = now()
                    WHERE greenhouse_id = $1
                    """,
                    greenhouse_id,
                    current_left,
                    current_right,
                    json.dumps(factors),
                    next_tick_idle,
                    active_override_id,
                    task_id,
                    control_mode,
                )
                if state_update != "UPDATE 1":
                    raise RuntimeError("greenhouse_climate_state_transition_failed")
                intent_update = await conn.execute(
                    """
                    UPDATE greenhouse_automation_intents
                    SET status = 'completed', completed_at = now(), updated_at = now()
                    WHERE id = $1 AND status = 'running'
                    """,
                    intent_id,
                )
                if intent_update != "UPDATE 1":
                    raise RuntimeError("greenhouse_climate_intent_transition_failed")
                if task_id is not None:
                    task_update = await conn.execute(
                        """
                        UPDATE greenhouse_automation_tasks
                        SET status = 'completed',
                            workflow_stage = 'disabled',
                            decision_snapshot = $2::jsonb,
                            completed_at = now(),
                            updated_at = now()
                        WHERE id = $1 AND status IN ('claimed', 'running', 'waiting_command')
                        """,
                        task_id,
                        json.dumps({"decision_reason": "climate_disabled", "factors": factors}),
                    )
                    if task_update != "UPDATE 1":
                        raise RuntimeError("greenhouse_climate_task_transition_failed")
        await self._ports.publish_greenhouse_alert_lifecycle(
            greenhouse_id=greenhouse_id,
            active_codes=[],
            details={"decision_reason": "climate_disabled", "task_id": task_id},
            alert_publisher=alert_publisher,
        )
        self._ports.record_tick_metric(tick_started, "completed")
        return {"status": "completed", "reason": "climate_disabled", "greenhouse_id": greenhouse_id}

    async def complete_active_tick(
        self,
        *,
        greenhouse_id: int,
        lease_owner: str,
        intent_id: int,
        task_id: int | None,
        tick_started: float,
        state: Mapping[str, Any],
        decision: ClimateDecision,
        left_cmd_id: str | None,
        right_cmd_id: str | None,
        left_done: bool,
        right_done: bool,
        command_failures: list[str],
        control_mode: str,
        snap: Mapping[str, Any],
        next_tick_active: datetime,
        active_override_id: int | None,
        active_alerts: list[str],
        alert_publisher: Any,
    ) -> Any:
        model_left = int(decision.left_target_pct) if left_done else int(state.get("left_position_pct") or 0)
        model_right = int(decision.right_target_pct) if right_done else int(state.get("right_position_pct") or 0)
        lease_lost = any(str(item).endswith(f":{self._ports.lease_lost_status()}") for item in command_failures)
        final_status = "failed" if command_failures else "completed"
        if lease_lost:
            error_code = "greenhouse_climate_lease_lost"
        elif command_failures:
            error_code = "greenhouse_vent_command_failed"
        else:
            error_code = None
        error_message = None if not command_failures else ", ".join(command_failures)
        if command_failures:
            active_alerts.append("GREENHOUSE_VENT_COMMAND_FAILED")
            active_alerts = self._ports.unique_alert_codes(active_alerts)

        def lease_lost_response() -> dict[str, Any]:
            self._ports.record_tick_metric(tick_started, "failed")
            return {
                "status": "failed",
                "greenhouse_id": greenhouse_id,
                "decision": decision.decision_reason,
                "suppress": decision.suppress_commands,
                "left_cmd_id": left_cmd_id,
                "right_cmd_id": right_cmd_id,
                "command_failures": command_failures,
                "error_code": "greenhouse_climate_lease_lost",
            }

        if lease_lost:
            # A successor tick may already own the greenhouse. Leave this
            # intent/task for stale recovery instead of overwriting its state.
            self._ports.logger().warning(
                "greenhouse_climate_tick lost lease before outcome gh=%s intent=%s", greenhouse_id, intent_id
            )
            return lease_lost_response()

        pool = await self._ports.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                if not await self._ports.lock_owned_greenhouse_lease(
                    conn, greenhouse_id=greenhouse_id, owner=lease_owner
                ):
                    self._ports.logger().warning(
                        "greenhouse_climate_tick lost lease at outcome gh=%s intent=%s", greenhouse_id, intent_id
                    )
                    command_failures.append("lease:LEASE_LOST")
                    return lease_lost_response()

                state_update = await conn.execute(
                    """
                    UPDATE greenhouse_automation_state
                    SET climate_enabled = true,
                        control_mode = $2,
                        left_position_pct = $3,
                        right_position_pct = $4,
                        recommended_left_position_pct = $5,
                        recommended_right_position_pct = $6,
                        last_sent_left_position_pct = CASE WHEN $14 THEN $5 ELSE last_sent_left_position_pct END,
                        last_sent_right_position_pct = CASE WHEN $15 THEN $6 ELSE last_sent_right_position_pct END,
                        decision_reason = $7,
                        decision_factors = $8::jsonb,
                        weather_fresh = $11,
                        inside_climate_fresh = $12,
                        last_decision_at = now(),
                        last_command_at = CASE WHEN ($9::varchar IS NOT NULL OR $10::varchar IS NOT NULL) THEN now() ELSE last_command_at END,
                        last_left_cmd_id = COALESCE($9, last_left_cmd_id),
                        last_right_cmd_id = COALESCE($10, last_right_cmd_id),
                        next_scheduled_tick_at = $13,
                        active_manual_override_id = $16,
                        last_task_id = $17,
                        last_error_code = $18,
                        last_error_message = $19,
                        active_alerts_summary = $20::jsonb,
                        updated_at = now()
                    WHERE greenhouse_id = $1
                    """,
                    greenhouse_id,
                    control_mode,
                    model_left,
                    model_right,
                    decision.left_target_pct,
                    decision.right_target_pct,
                    decision.decision_reason,
                    json.dumps(decision.factors),
                    left_cmd_id,
                    right_cmd_id,
                    snap["weather_fresh"],
                    snap["inside_fresh"],
                    next_tick_active,
                    left_done,
                    right_done,
                    active_override_id,
                    task_id,
                    error_code,
                    error_message,
                    json.dumps(active_alerts),
                )
                if state_update != "UPDATE 1":
                    raise RuntimeError("greenhouse_climate_state_transition_failed")
                intent_update = await conn.execute(
                    """
                    UPDATE greenhouse_automation_intents
                    SET status = $2, completed_at = now(), updated_at = now(),
                        error_code = $3, error_message = $4
                    WHERE id = $1 AND status = 'running'
                    """,
                    intent_id,
                    final_status,
                    error_code,
                    error_message,
                )
                if intent_update != "UPDATE 1":
                    raise RuntimeError("greenhouse_climate_intent_transition_failed")
                if task_id is not None:
                    task_update = await conn.execute(
                        """
                        UPDATE greenhouse_automation_tasks
                        SET status = $2,
                            workflow_stage = 'terminal',
                            decision_snapshot = $3::jsonb,
                            command_refs = $4::jsonb,
                            error_code = $5,
                            error_message = $6,
                            completed_at = now(),
                            updated_at = now()
                        WHERE id = $1 AND status IN ('claimed', 'running', 'waiting_command')
                        """,
                        task_id,
                        final_status,
                        json.dumps({"decision_reason": decision.decision_reason, "factors": decision.factors}),
                        json.dumps({"left_cmd_id": left_cmd_id, "right_cmd_id": right_cmd_id}),
                        error_code,
                        error_message,
                    )
                    if task_update != "UPDATE 1":
                        raise RuntimeError("greenhouse_climate_task_transition_failed")

        await self._ports.publish_greenhouse_alert_lifecycle(
            greenhouse_id=greenhouse_id,
            active_codes=active_alerts,
            details={
                "task_id": task_id,
                "decision_reason": decision.decision_reason,
                "weather_fresh": bool(snap["weather_fresh"]),
                "inside_climate_fresh": bool(snap["inside_fresh"]),
                "inside_temp_spread": snap.get("inside_temp_spread"),
                "inside_rh_spread": snap.get("inside_rh_spread"),
                "command_failures": command_failures,
            },
            alert_publisher=alert_publisher,
        )
        self._ports.record_tick_metric(tick_started, final_status)
        return {
            "status": "ok" if final_status == "completed" else "failed",
            "greenhouse_id": greenhouse_id,
            "decision": decision.decision_reason,
            "suppress": decision.suppress_commands,
            "left_cmd_id": left_cmd_id,
            "right_cmd_id": right_cmd_id,
            "command_failures": command_failures,
        }

    async def persist_tick_exception(
        self, *, greenhouse_id: int, lease_owner: str, intent_id: int, task_id: int | None, exc: Exception
    ) -> Any:
        try:
            pool = await self._ports.get_pool()
            async with pool.acquire() as conn:
                async with conn.transaction():
                    if await self._ports.lock_owned_greenhouse_lease(
                        conn, greenhouse_id=greenhouse_id, owner=lease_owner
                    ):
                        await conn.execute(
                            """
                            UPDATE greenhouse_automation_intents
                            SET status = 'failed', completed_at = now(), updated_at = now(),
                                error_code = 'greenhouse_climate_tick_failed', error_message = $2
                            WHERE id = $1 AND status = 'running'
                            """,
                            intent_id,
                            str(exc)[:2000],
                        )
                        if task_id is not None:
                            await conn.execute(
                                """
                                UPDATE greenhouse_automation_tasks
                                SET status = 'failed',
                                    workflow_stage = 'exception',
                                    error_code = 'greenhouse_climate_tick_failed',
                                    error_message = $2,
                                    completed_at = now(),
                                    updated_at = now()
                                WHERE id = $1 AND status IN ('claimed', 'running', 'waiting_command')
                                """,
                                task_id,
                                str(exc)[:2000],
                            )
        except Exception:
            self._ports.logger().warning(
                "greenhouse_climate_tick could not persist failure gh=%s intent=%s",
                greenhouse_id,
                intent_id,
                exc_info=True,
            )
