"""Ae3RuntimeWorker correction recovery: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.runtime.worker_runtime_state import WorkerRuntimeState


@dataclass(frozen=True)
class WorkerRuntimeCorrectionRecoveryPorts:
    command_gateway: Callable[[], Any]
    correction_interrupt_irr_state_max_age_sec: Callable[[], Any]
    correction_interrupt_replay_irrigation: Callable[[], Any]
    create_task_from_intent_use_case: Callable[[], Any]
    ensure_waiting_command_reconcile_loop: Callable[..., Any]
    logger: Callable[[], Any]
    now_fn: Callable[..., Any]
    runtime_monitor: Callable[[], Any]
    safe_mark_intent_terminal_result: Callable[..., Awaitable[Any]]
    startup_recovery_use_case: Callable[[], Any]
    task_repository: Callable[[], Any]
    zone_intent_repository: Callable[[], Any]
    kick: Callable[..., Any]
    optional_safe_mark_intent_terminal_result: Callable[[], Any]


class WorkerRuntimeCorrectionRecovery:
    def __init__(self, ports: WorkerRuntimeCorrectionRecoveryPorts, state: WorkerRuntimeState) -> None:
        self._ports = ports
        self._state = state

    async def recover_on_startup(self) -> Any:
        now = self._ports.now_fn()
        from ae3lite.greenhouse_climate.recovery import recover_stale_greenhouse_automation

        await recover_stale_greenhouse_automation(now=now)
        result = await self._ports.startup_recovery_use_case().run(now=now)
        terminal_outcomes = getattr(result, "terminal_outcomes", ()) or ()
        for outcome in terminal_outcomes:
            intent_id = int(getattr(outcome, "intent_id", 0) or 0)
            if intent_id <= 0:
                continue
            await self._ports.safe_mark_intent_terminal_result(
                intent_id=intent_id,
                now=now,
                success=bool(getattr(outcome, "success", False)),
                error_code=getattr(outcome, "error_code", None),
                error_message=getattr(outcome, "error_message", None),
                task_id=int(getattr(outcome, "task_id", 0) or 0) or None,
            )
        pending_checks = getattr(result, "pending_correction_safety_checks", ()) or ()
        if pending_checks:
            self.enqueue_correction_safety_checks(pending_checks)
            self._ports.logger().info(
                "AE3 startup recovery: queued %s correction-interrupt safety checks",
                len(pending_checks),
            )
        # Повторный reload из zone_events — защита от потери in-memory очереди
        # при рестарте AE в grace-window (даже если use-case вернул пустой tuple).
        await self.reload_persisted_correction_safety_checks(now=now)
        self._ports.ensure_waiting_command_reconcile_loop()
        return result

    def enqueue_correction_safety_checks(self, checks: Any) -> int:
        known = {int(getattr(item, "task_id", 0) or 0) for item in self._state.pending_correction_safety_checks}
        added = 0
        for check in list(checks or ()):
            task_id = int(getattr(check, "task_id", 0) or 0)
            if task_id <= 0 or task_id in known:
                continue
            self._state.pending_correction_safety_checks.append(check)
            known.add(task_id)
            added += 1
        return added

    async def reload_persisted_correction_safety_checks(self, *, now: datetime) -> int:
        from ae3lite.application.services.correction_interrupt_safety import (
            load_open_pending_correction_interrupt_checks,
        )

        try:
            persisted = await load_open_pending_correction_interrupt_checks(now=now)
        except Exception:
            self._ports.logger().warning(
                "AE3 startup recovery: failed to reload persisted correction-interrupt checks",
                exc_info=True,
            )
            return 0
        added = self.enqueue_correction_safety_checks(persisted)
        if added:
            self._ports.logger().info(
                "AE3 startup recovery: restored %s persisted correction-interrupt checks",
                added,
            )
        return added

    async def maybe_run_correction_interrupt_safety_once(self) -> None:
        if not self._state.pending_correction_safety_checks:
            return
        if self._ports.runtime_monitor() is None:
            return

        from ae3lite.application.services.correction_interrupt_safety import (
            emit_correction_interrupt_hardware_safe,
            evaluate_correction_interrupt_safety,
        )

        now = self._ports.now_fn()
        remaining: list[Any] = []
        kick_needed = False
        for check in list(self._state.pending_correction_safety_checks):
            try:
                verdict = await evaluate_correction_interrupt_safety(
                    check=check,
                    now=now,
                    runtime_monitor=self._ports.runtime_monitor(),
                    irr_state_max_age_sec=self._ports.correction_interrupt_irr_state_max_age_sec(),
                )
            except Exception:
                self._ports.logger().warning(
                    "AE3 correction-interrupt safety evaluate failed zone_id=%s task_id=%s",
                    getattr(check, "zone_id", None),
                    getattr(check, "task_id", None),
                    exc_info=True,
                )
                deadline = getattr(check, "deadline_at", None)
                past_deadline = isinstance(deadline, datetime) and now >= deadline
                if past_deadline:
                    # Не крутим check вечно после grace — fail-safe + escalate unsafe.
                    await self.handle_correction_interrupt_unsafe(
                        check=check,
                        now=now,
                        reason="evaluate_exception_after_grace",
                    )
                else:
                    remaining.append(check)
                continue

            status = str(getattr(verdict, "status", "") or "").strip().lower()
            if status == "pending":
                remaining.append(check)
                continue
            if status == "safe":
                await emit_correction_interrupt_hardware_safe(
                    check=check,
                    now=now,
                    reason=str(getattr(verdict, "reason", "") or "safe"),
                    snapshot=getattr(verdict, "snapshot", None),
                )
                if self._ports.correction_interrupt_replay_irrigation():
                    replayed = await self.replay_irrigation_after_correction_interrupt(
                        check=check,
                        now=now,
                    )
                    kick_needed = kick_needed or replayed
                continue
            # unsafe: сначала fail-safe stop irrig через HL, затем escalate critical
            await self.handle_correction_interrupt_unsafe(
                check=check,
                now=now,
                reason=str(getattr(verdict, "reason", "") or "unconfirmed"),
            )

        self._state.pending_correction_safety_checks = remaining
        if kick_needed and not self._state.shutting_down:
            self._ports.kick()

    async def handle_correction_interrupt_unsafe(
        self,
        *,
        check: Any,
        now: datetime,
        reason: str,
    ) -> None:
        from ae3lite.application.services.correction_interrupt_safety import (
            attempt_correction_interrupt_fail_safe_stop,
            escalate_correction_interrupt_hardware_risk,
        )

        stop_result = await attempt_correction_interrupt_fail_safe_stop(
            check=check,
            now=now,
            command_gateway=self._ports.command_gateway(),
        )
        if not stop_result.success:
            self._ports.logger().warning(
                "AE3 correction-interrupt unsafe: fail-safe stop skipped/failed "
                "zone_id=%s task_id=%s stop_reason=%s verdict=%s",
                getattr(check, "zone_id", None),
                getattr(check, "task_id", None),
                stop_result.reason,
                reason,
            )
        await escalate_correction_interrupt_hardware_risk(
            check=check,
            now=now,
            reason=reason,
        )

    async def fail_irrigation_replay_intent(
        self,
        *,
        intent_id: int,
        zone_id: int,
        now: datetime,
        error_code: str,
        error_message: str,
    ) -> None:
        """Terminal-fail claimed replay intent после create-task failure (TOCTOU guard)."""
        mark = self._ports.optional_safe_mark_intent_terminal_result()
        if not callable(mark):
            mark_terminal = getattr(self._ports.zone_intent_repository(), "mark_terminal", None)
            if not callable(mark_terminal):
                self._ports.logger().warning(
                    "AE3 correction-interrupt irrigation replay: cannot mark intent terminal "
                    "intent_id=%s zone_id=%s code=%s",
                    intent_id,
                    zone_id,
                    error_code,
                )
                return
            try:
                await mark_terminal(
                    intent_id=intent_id,
                    now=now,
                    success=False,
                    error_code=error_code,
                    error_message=error_message,
                )
            except Exception:
                self._ports.logger().warning(
                    "AE3 correction-interrupt irrigation replay mark_terminal failed intent_id=%s zone_id=%s",
                    intent_id,
                    zone_id,
                    exc_info=True,
                )
            return
        await mark(
            intent_id=intent_id,
            now=now,
            success=False,
            error_code=error_code,
            error_message=error_message,
            task_id=None,
            zone_id=zone_id,
        )

    async def replay_irrigation_after_correction_interrupt(
        self,
        *,
        check: Any,
        now: datetime,
    ) -> bool:
        if str(getattr(check, "task_type", "") or "").strip().lower() != "irrigation_start":
            return False
        if self._ports.create_task_from_intent_use_case() is None:
            return False
        upsert = getattr(self._ports.zone_intent_repository(), "upsert_irrigation_replay_intent", None)
        claim = getattr(self._ports.zone_intent_repository(), "claim_pending_intent_by_id", None)
        if not callable(upsert) or not callable(claim):
            return False

        zone_id = int(getattr(check, "zone_id", 0) or 0)
        failed_task_id = int(getattr(check, "task_id", 0) or 0)
        if zone_id <= 0 or failed_task_id <= 0:
            return False

        # Не стартуем, если зона уже занята другой задачей.
        get_active = getattr(self._ports.task_repository(), "get_active_for_zone", None)
        if callable(get_active):
            try:
                active = await get_active(zone_id=zone_id)
            except Exception:
                active = None
            if active is not None:
                self._ports.logger().info(
                    "AE3 correction-interrupt irrigation replay skipped: zone busy zone_id=%s",
                    zone_id,
                )
                return False

        idempotency_key = f"ae3-recovery-irr-replay-{failed_task_id}"
        try:
            intent_id = await upsert(
                zone_id=zone_id,
                idempotency_key=idempotency_key,
                topology=str(getattr(check, "topology", "") or "two_tank_drip_substrate_trays"),
                now=now,
                mode=str(getattr(check, "irrigation_mode", None) or "normal"),
                requested_duration_sec=getattr(check, "irrigation_requested_duration_sec", None),
                source="ae3_startup_recovery",
                failed_task_id=failed_task_id,
            )
        except Exception:
            self._ports.logger().warning(
                "AE3 correction-interrupt irrigation replay upsert failed zone_id=%s task_id=%s",
                zone_id,
                failed_task_id,
                exc_info=True,
            )
            return False
        if intent_id is None:
            return False

        try:
            claim_result = await claim(zone_id=zone_id, intent_id=int(intent_id), now=now)
        except Exception:
            self._ports.logger().warning(
                "AE3 correction-interrupt irrigation replay claim failed zone_id=%s intent_id=%s",
                zone_id,
                intent_id,
                exc_info=True,
            )
            return False
        if str(claim_result.get("decision") or "") != "claimed":
            self._ports.logger().info(
                "AE3 correction-interrupt irrigation replay not claimed zone_id=%s intent_id=%s decision=%s",
                zone_id,
                intent_id,
                claim_result.get("decision"),
            )
            return False

        intent_row = dict(claim_result.get("intent") or {})
        try:
            creation = await self._ports.create_task_from_intent_use_case().run(
                zone_id=zone_id,
                source="ae3_startup_recovery",
                idempotency_key=idempotency_key,
                intent_row=intent_row,
                now=now,
            )
        except Exception as exc:
            self._ports.logger().warning(
                "AE3 correction-interrupt irrigation replay create-task failed zone_id=%s intent_id=%s",
                zone_id,
                intent_id,
                exc_info=True,
            )
            await self.fail_irrigation_replay_intent(
                intent_id=int(intent_id),
                zone_id=zone_id,
                now=now,
                error_code="ae3_irrigation_replay_create_failed",
                error_message=str(exc)[:500] or "create_task_from_intent failed",
            )
            return False

        created = bool(getattr(creation, "created", False))
        task = getattr(creation, "task", None)
        if not created:
            task_intent_id = int(getattr(task, "intent_id", 0) or 0) if task is not None else 0
            linked_to_this_intent = task is not None and task_intent_id == int(intent_id)
            self._ports.logger().warning(
                "AE3 correction-interrupt irrigation replay create-task returned created=False "
                "zone_id=%s intent_id=%s task_id=%s linked=%s",
                zone_id,
                intent_id,
                getattr(task, "id", None),
                linked_to_this_intent,
            )
            # Claimed intent без новой/связанной task — terminal fail, иначе stuck claimed (TOCTOU).
            if not linked_to_this_intent:
                await self.fail_irrigation_replay_intent(
                    intent_id=int(intent_id),
                    zone_id=zone_id,
                    now=now,
                    error_code="ae3_irrigation_replay_create_failed",
                    error_message="create_task_from_intent returned created=False",
                )
            return False

        self._ports.logger().info(
            "AE3 correction-interrupt irrigation replay dispatched zone_id=%s intent_id=%s task_id=%s created=%s",
            zone_id,
            intent_id,
            getattr(task, "id", None),
            created,
        )
        return True
