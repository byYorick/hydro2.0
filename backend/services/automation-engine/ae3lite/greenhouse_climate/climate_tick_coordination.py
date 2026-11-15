"""climate tick coordination: explicit dependencies and invocation data."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from ae3lite.infrastructure.clients import HistoryLoggerClient


@dataclass(frozen=True)
class ClimateTickCoordinationPorts:
    claim_greenhouse_lease: Callable[..., Any]
    complete_active_tick: Callable[..., Any]
    complete_disabled_tick: Callable[..., Any]
    complete_missing_bundle: Callable[..., Any]
    ensure_state_row: Callable[..., Any]
    execute_vent_commands: Callable[..., Any]
    expired_manual_override_return_mode: Callable[..., Any]
    parse_bundle: Callable[..., Any]
    persist_tick_exception: Callable[..., Any]
    plan_active_tick: Callable[..., Any]
    record_tick_metric: Callable[..., Any]
    release_greenhouse_lease: Callable[..., Any]
    execute: Callable[..., Any]
    fetch: Callable[..., Any]
    logger: Callable[..., Any]
    resolve_greenhouse_lease_owner: Callable[..., Any]
    uuid4: Callable[..., Any]


class ClimateTickCoordination:
    def __init__(self, ports: ClimateTickCoordinationPorts) -> None:
        self._ports = ports

    async def run_greenhouse_climate_tick(
        self,
        *,
        greenhouse_id: int,
        idempotency_key: str,
        history_logger_client: HistoryLoggerClient,
        alert_publisher: Any,
        worker_owner: str | None,
        lease_ttl_sec: int,
    ) -> dict[str, Any]:
        tick_started = time.monotonic()
        # One owner per execution, not per process: a second tick from the same
        # worker must not renew or release the first tick's lease.
        lease_owner = f"{self._ports.resolve_greenhouse_lease_owner(worker_owner=worker_owner)[:51]}:{self._ports.uuid4().hex[:12]}"
        await self._ports.ensure_state_row(greenhouse_id)

        claimed = await self._ports.fetch(
            """
            WITH c AS (
                SELECT id FROM greenhouse_automation_intents
                WHERE greenhouse_id = $1 AND idempotency_key = $2 AND status = 'pending'
                ORDER BY id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE greenhouse_automation_intents AS i
            SET status = 'running',
                claimed_at = now(),
                updated_at = now()
            FROM c
            WHERE i.id = c.id
            RETURNING i.id AS intent_id
            """,
            greenhouse_id,
            idempotency_key,
        )
        if not claimed:
            self._ports.record_tick_metric(tick_started, "skipped")
            return {"status": "skipped", "reason": "no_pending_intent", "greenhouse_id": greenhouse_id}

        intent_id = int(claimed[0]["intent_id"])
        lease_claimed = await self._ports.claim_greenhouse_lease(
            greenhouse_id,
            owner=lease_owner,
            ttl_sec=lease_ttl_sec,
        )
        if not lease_claimed:
            await self._ports.execute(
                """
                UPDATE greenhouse_automation_intents
                SET status = 'pending',
                    claimed_at = NULL,
                    updated_at = now(),
                    error_code = NULL,
                    error_message = NULL
                WHERE id = $1
                  AND status = 'running'
                """,
                intent_id,
            )
            self._ports.record_tick_metric(tick_started, "skipped")
            return {"status": "skipped", "reason": "greenhouse_climate_busy", "greenhouse_id": greenhouse_id}

        task_id: int | None = None
        try:
            task_rows = await self._ports.fetch(
                """
                INSERT INTO greenhouse_automation_tasks (
                    greenhouse_id, intent_id, task_type, status, idempotency_key, workflow_stage, created_at, updated_at
                )
                VALUES ($1, $2, 'greenhouse_climate_tick', 'running', $3, 'decision', now(), now())
                ON CONFLICT (greenhouse_id, idempotency_key) DO UPDATE
                SET status = 'running',
                    intent_id = EXCLUDED.intent_id,
                    workflow_stage = 'decision',
                    updated_at = now()
                RETURNING id
                """,
                greenhouse_id,
                intent_id,
                idempotency_key,
            )
            task_id = int(task_rows[0]["id"]) if task_rows else None

            bundle_rows = await self._ports.fetch(
                """
                SELECT config, status
                FROM automation_effective_bundles
                WHERE scope_type = 'greenhouse' AND scope_id = $1
                LIMIT 1
                """,
                greenhouse_id,
            )
            if not bundle_rows or str(bundle_rows[0].get("status") or "").lower() != "valid":
                return await self._ports.complete_missing_bundle(
                    greenhouse_id=greenhouse_id,
                    lease_owner=lease_owner,
                    intent_id=intent_id,
                    task_id=task_id,
                    tick_started=tick_started,
                )

            config = bundle_rows[0].get("config") or {}
            climate, _active_mode, _lp = self._ports.parse_bundle(config if isinstance(config, dict) else None)
            enabled = bool(climate.get("enabled") is True)
            control_mode = str(climate.get("control_mode") or "auto").strip().lower()
            execution = climate.get("execution") if isinstance(climate.get("execution"), dict) else {}

            state_rows = await self._ports.fetch(
                "SELECT * FROM greenhouse_automation_state WHERE greenhouse_id = $1 LIMIT 1",
                greenhouse_id,
            )
            state = dict(state_rows[0]) if state_rows else {}
            restored_mode = await self._ports.expired_manual_override_return_mode(greenhouse_id, state)
            if restored_mode is not None:
                state["control_mode"] = restored_mode
                state["active_manual_override_id"] = None
            db_control = str(state.get("control_mode") or "auto").strip().lower()
            if db_control in {"auto", "semi", "manual"}:
                control_mode = db_control

            if not enabled:
                return await self._ports.complete_disabled_tick(
                    greenhouse_id=greenhouse_id,
                    lease_owner=lease_owner,
                    intent_id=intent_id,
                    task_id=task_id,
                    tick_started=tick_started,
                    state=state,
                    control_mode=control_mode,
                    alert_publisher=alert_publisher,
                )

            (
                execution,
                snap,
                vents,
                active_override_id,
                decision,
                active_alerts,
                next_tick_active,
            ) = await self._ports.plan_active_tick(
                greenhouse_id=greenhouse_id, execution=execution, state=state, control_mode=control_mode
            )

            (
                left_cmd_id,
                right_cmd_id,
                left_done,
                right_done,
                command_failures,
            ) = await self._ports.execute_vent_commands(
                greenhouse_id=greenhouse_id,
                execution=execution,
                state=state,
                decision=decision,
                vents=vents,
                lease_owner=lease_owner,
                lease_ttl_sec=lease_ttl_sec,
                idempotency_key=idempotency_key,
                history_logger_client=history_logger_client,
            )

            return await self._ports.complete_active_tick(
                greenhouse_id=greenhouse_id,
                lease_owner=lease_owner,
                intent_id=intent_id,
                task_id=task_id,
                tick_started=tick_started,
                state=state,
                decision=decision,
                left_cmd_id=left_cmd_id,
                right_cmd_id=right_cmd_id,
                left_done=left_done,
                right_done=right_done,
                command_failures=command_failures,
                control_mode=control_mode,
                snap=snap,
                next_tick_active=next_tick_active,
                active_override_id=active_override_id,
                active_alerts=active_alerts,
                alert_publisher=alert_publisher,
            )
        except Exception as exc:
            self._ports.logger().error(
                "greenhouse_climate_tick failed gh=%s intent=%s", greenhouse_id, intent_id, exc_info=True
            )
            await self._ports.persist_tick_exception(
                greenhouse_id=greenhouse_id, lease_owner=lease_owner, intent_id=intent_id, task_id=task_id, exc=exc
            )
            self._ports.record_tick_metric(tick_started, "failed")
            raise
        finally:
            if lease_claimed:
                try:
                    await self._ports.release_greenhouse_lease(greenhouse_id, owner=lease_owner)
                except Exception:
                    # The TTL will release ownership even when cleanup is unavailable.
                    # Do not replace a committed outcome or its original exception.
                    self._ports.logger().warning(
                        "greenhouse_climate_tick lease release failed gh=%s", greenhouse_id, exc_info=True
                    )
