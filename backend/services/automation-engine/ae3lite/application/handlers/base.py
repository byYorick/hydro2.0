"""Базовый handler с общими операциями probe, sensor и level."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Mapping, Optional, Sequence

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.config import live_reload as _live_reload
from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError
from ae3lite.application.level_monitor import level_snapshot_aliases
from ae3lite.domain.services.telemetry_window_summary import (
    decision_window_since_ts as _telemetry_decision_window_since_ts,
    summarize_window as _telemetry_summarize_window,
)
from ae3lite.infrastructure.metrics import (
    EMERGENCY_STOP_RECONCILE,
    FAIL_SAFE_TRANSITION,
    IRR_PROBE_DEFERRED,
    IRR_PROBE_STREAK_EXHAUSTED,
    NODE_REBOOT_DETECTED,
)
from common.biz_alerts import send_biz_alert
from common.db import create_zone_event
from common.service_logs import send_service_log


_MISSING_CONFIG = object()


_logger = logging.getLogger(__name__)


def _utc_naive_dt(dt: datetime) -> datetime:
    """Нормализует datetime к UTC-naive перед сравнениями."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo is not None else dt


class BaseStageHandler:
    """Предоставляет переиспользуемые helper'ы чтения сенсоров для check-handler'ов.

    Подклассы реализуют ``run()`` и возвращают :class:`StageOutcome`.
    """

    _IRR_STATE_PROBE_RETRY_COUNT = 1
    _IRR_STATE_PROBE_RETRY_DELAY_SEC = 0.5
    _IRR_PROBE_FAILURE_STREAK_LIMIT = 5
    _IRR_PROBE_NODE_UNREACHABLE_HEARTBEAT_AGE_SEC = 30.0

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        command_gateway: Any,
        task_repository: Any = None,
        live_reload_enabled: bool = False,
    ) -> None:
        self._runtime_monitor = runtime_monitor
        self._command_gateway = command_gateway
        self._task_repository = task_repository
        self._last_probe_state: dict[str, Any] | None = None
        self._reconciled_estop_event_ids: set[int] = set()
        # Phase 5: live-mode checkpoint toggle. Default False → handler tests
        # that don't wire a real DB pool see no live-reload noise. Production
        # `WorkflowRouter` enables it when constructing handlers.
        self._live_reload_enabled = live_reload_enabled

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        raise NotImplementedError

    async def _checkpoint(self, *, task: Any, plan: Any, now: datetime) -> Any:
        """Phase 5.5: live-mode config hot-swap.

        Returns either ``plan.runtime`` unchanged (locked / no advance / TTL
        expired) or a *new* ``RuntimePlan`` instance built from the current
        zone snapshot. Handlers should assign the result back to their local
        ``runtime`` variable:

            runtime = await self._checkpoint(task=task, plan=plan, now=now)

        Hot-swap is achieved by:
          1. Comparing `zones.config_revision` (DB) against
             `plan.runtime.bundle_revision` (in-flight)
          2. On advance + LIVE mode: re-loading the zone snapshot
             (`PgZoneSnapshotReadModel().load`) and re-resolving via
             `resolve_two_tank_runtime_plan` — same code path as
             cycle_start_planner, so the fresh plan is structurally
             identical to one built on a fresh task claim.
          3. Stamping the new revision onto `bundle_revision` so subsequent
             checkpoints in the same `run()` don't re-trigger.

        Emits `CONFIG_HOT_RELOADED` zone_event + `ae3_config_hot_reload_total`
        metric on apply. Failures degrade gracefully: returns original runtime
        with `result=error` metric label.
        """
        from ae3lite.infrastructure.metrics import (
            CONFIG_HOT_RELOAD,
            ZONE_CONFIG_LIVE_EDITS,
            ZONE_CONFIG_MODE,
        )

        runtime = plan.runtime
        if not self._live_reload_enabled:
            return runtime

        # Phase 5: compare integer `zones.config_revision` (DB) vs the
        # monotonic counter snapshot read at plan-build time. Do NOT use
        # `bundle_revision` — that's a content hash, not a counter.
        try:
            current_revision = int(getattr(runtime, "config_revision", None) or 0)
        except (TypeError, ValueError):
            current_revision = 0

        zone_id = int(getattr(task, "zone_id", 0) or 0)
        if zone_id <= 0:
            CONFIG_HOT_RELOAD.labels(result="disabled").inc()
            return runtime

        try:
            from common.db import get_pool
            pool = await get_pool()
        except Exception:
            _logger.warning("checkpoint: DB pool unavailable, skipping live-reload", exc_info=True)
            CONFIG_HOT_RELOAD.labels(result="error").inc()
            return runtime

        # Cheap pre-check: read zone's mode/revision/TTL only.
        try:
            async with pool.acquire() as conn:
                zone_row = await conn.fetchrow(
                    "SELECT config_mode, config_revision, live_until FROM zones WHERE id = $1",
                    zone_id,
                )
        except Exception:
            _logger.warning("checkpoint: zone read failed zone_id=%s", zone_id, exc_info=True)
            CONFIG_HOT_RELOAD.labels(result="error").inc()
            return runtime

        from ae3lite.config.modes import ConfigMode

        if zone_row is None:
            CONFIG_HOT_RELOAD.labels(result="no_change").inc()
            return runtime
        observed_mode = ConfigMode.parse(zone_row.get("config_mode"))
        # Phase 7 gauge: observer-style publish на каждом checkpoint. Дёшево
        # потому что уже читаем zone row ради revision сравнения.
        try:
            ZONE_CONFIG_MODE.labels(zone_id=str(zone_id)).set(
                1.0 if observed_mode is ConfigMode.LIVE else 0.0,
            )
        except Exception:  # pragma: no cover — metrics exporter issue
            pass
        if observed_mode is not ConfigMode.LIVE:
            CONFIG_HOT_RELOAD.labels(result="no_change").inc()
            return runtime
        live_until = zone_row.get("live_until")
        if isinstance(live_until, datetime):
            now_utc = datetime.now(timezone.utc)
            if live_until.tzinfo is None:
                live_until = live_until.replace(tzinfo=timezone.utc)
            if live_until < now_utc:
                CONFIG_HOT_RELOAD.labels(result="no_change").inc()
                return runtime
        new_revision = int(zone_row.get("config_revision") or 0)
        if new_revision <= current_revision:
            CONFIG_HOT_RELOAD.labels(result="no_change").inc()
            return runtime

        # Revision advanced — rebuild the full RuntimePlan via the canonical
        # planner path so the result is structurally identical to a fresh
        # task-claim plan.
        try:
            from ae3lite.infrastructure.read_models.zone_snapshot_read_model import (
                PgZoneSnapshotReadModel,
            )
            from ae3lite.config.runtime_plan_builder import (
                resolve_two_tank_runtime_plan,
            )

            snapshot = await PgZoneSnapshotReadModel().load(zone_id=zone_id)
            new_runtime = resolve_two_tank_runtime_plan(snapshot)
            # Stamp the observed revision so subsequent checkpoints in this
            # `run()` won't re-trigger. Keep the bundle_revision (content hash)
            # whatever the resolver chose.
            new_runtime = new_runtime.model_copy(update={"config_revision": int(new_revision)})
        except Exception:
            _logger.warning(
                "checkpoint: snapshot rebuild failed zone_id=%s rev=%s",
                zone_id, new_revision, exc_info=True,
            )
            CONFIG_HOT_RELOAD.labels(result="error").inc()
            return runtime

        try:
            await create_zone_event(
                zone_id,
                "CONFIG_HOT_RELOADED",
                with_runtime_event_contract({
                    "revision": new_revision,
                    "previous_revision": current_revision,
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "stage": str(getattr(task, "current_stage", "") or ""),
                }),
            )
        except Exception:
            _logger.warning(
                "checkpoint: failed to emit CONFIG_HOT_RELOADED event zone_id=%s",
                zone_id, exc_info=True,
            )

        CONFIG_HOT_RELOAD.labels(result="applied").inc()
        try:
            ZONE_CONFIG_LIVE_EDITS.labels(
                zone_id=str(zone_id),
                handler=str(getattr(task, "current_stage", "") or "unknown"),
            ).inc()
        except Exception:  # pragma: no cover — metrics exporter issue
            pass
        _logger.info(
            "config_hot_reload: applied zone_id=%s rev=%s→%s",
            zone_id, current_revision, new_revision,
        )
        return new_runtime

    def _deadline_reached(self, *, now: datetime, deadline: datetime | None) -> bool:
        if deadline is None:
            return False
        return _utc_naive_dt(now) >= _utc_naive_dt(deadline)

    def _stage_entered_at(self, *, task: Any) -> datetime | None:
        entered = getattr(getattr(task, "workflow", None), "stage_entered_at", None)
        return _utc_naive_dt(entered) if isinstance(entered, datetime) else None

    def _stage_elapsed_ms(self, *, task: Any, now: datetime) -> int:
        entered = self._stage_entered_at(task=task)
        if entered is None:
            return 0
        return max(0, int((_utc_naive_dt(now) - entered).total_seconds() * 1000.0))

    def _remaining_stage_time_sec(self, *, now: datetime, deadline: datetime | None) -> float | None:
        if deadline is None:
            return None
        remaining = (_utc_naive_dt(deadline) - _utc_naive_dt(now)).total_seconds()
        return max(0.0, remaining)

    def _require_runtime_plan(self, *, plan: Any) -> RuntimePlan:
        runtime = getattr(plan, "runtime", None)
        if isinstance(runtime, RuntimePlan):
            return runtime
        raise TaskExecutionError(
            ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
            "Отсутствует typed RuntimePlan в command plan",
        )

    def _irr_probe_deadline_budget_sec(self, *, runtime: RuntimePlan) -> float:
        # На реальном test-node roundtrip команды и состояния может занимать несколько секунд.
        # Если запускать новый IRR probe слишком близко к дедлайну stage, команда
        # может упасть уже на polling после дедлайна, а не пойти по ожидаемому stage path.
        wait_timeout = self._coerce_float(runtime.irr_state_wait_timeout_sec)
        attempts = 1 + self._IRR_STATE_PROBE_RETRY_COUNT
        # Бюджет должен покрывать и roundtrip команды storage_state, и последующее
        # ожидание snapshot. На реальном железе этот путь легко превышает 5 с,
        # и для transient-потери MQTT probe допускается один republish.
        single_attempt_budget = (wait_timeout if wait_timeout is not None else 0.0) + 2.0  # config-literal: fixed command roundtrip budget
        base_budget = (single_attempt_budget * attempts) + (
            self._IRR_STATE_PROBE_RETRY_DELAY_SEC * self._IRR_STATE_PROBE_RETRY_COUNT
        )
        return max(8.0, base_budget)  # config-literal: minimum safe IRR probe budget

    def _deadline_too_close_for_irr_probe(
        self,
        *,
        now: datetime,
        deadline: datetime | None,
        runtime: RuntimePlan,
    ) -> bool:
        remaining = self._remaining_stage_time_sec(now=now, deadline=deadline)
        if remaining is None:
            return False
        return remaining <= self._irr_probe_deadline_budget_sec(runtime=runtime)

    async def _read_recent_storage_event(
        self,
        *,
        task: Any,
        event_types: Sequence[str],
        max_age_sec: int = 3600,  # config-literal: default recent-event lookup window
    ) -> Mapping[str, Any] | None:
        read_latest_zone_event = getattr(self._runtime_monitor, "read_latest_zone_event", None)
        if not callable(read_latest_zone_event):
            return None
        return await read_latest_zone_event(
            zone_id=int(getattr(task, "zone_id", 0) or 0),
            event_types=event_types,
            max_age_sec=max_age_sec,
            since_ts=self._stage_entered_at(task=task),
            channel="storage_state",
        )

    def _storage_event_payload(self, event: Mapping[str, Any] | None) -> Mapping[str, Any]:
        payload = event.get("payload") if isinstance(event, Mapping) else None
        return payload if isinstance(payload, Mapping) else {}

    def _task_topology(self, *, task: Any) -> str:
        return str(getattr(task, "topology", "") or "").strip()

    def _task_stage(self, *, task: Any) -> str:
        workflow = getattr(task, "workflow", None)
        return str(
            getattr(workflow, "current_stage", None)
            or getattr(task, "current_stage", None)
            or ""
        ).strip()

    def _observe_fail_safe_transition(
        self,
        *,
        task: Any,
        reason: str,
        source: str,
        next_stage: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        topology = self._task_topology(task=task)
        stage = self._task_stage(task=task)
        FAIL_SAFE_TRANSITION.labels(
            topology=topology,
            stage=stage or "unknown",
            reason=str(reason or "unknown"),
            source=str(source or "unknown"),
        ).inc()
        context = {
            "zone_id": int(getattr(task, "zone_id", 0) or 0) or None,
            "task_id": int(getattr(task, "id", 0) or 0) or None,
            "topology": topology or None,
            "stage": stage or None,
            "reason": str(reason or "unknown"),
            "source": str(source or "unknown"),
            "next_stage": str(next_stage or "unknown"),
        }
        if isinstance(details, Mapping):
            context.update({str(k): v for k, v in details.items()})
        send_service_log(
            service="automation-engine",
            level="warning",
            message="AE3 fail-safe transition selected",
            context=context,
        )

    async def _reconcile_recent_emergency_stop(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        expected: Mapping[str, bool],
    ) -> None:
        event = await self._read_recent_storage_event(
            task=task,
            event_types=("EMERGENCY_STOP_ACTIVATED",),
            max_age_sec=86400,  # config-literal: one-day ESTOP replay window
        )
        if not isinstance(event, Mapping):
            return
        event_id = int(event.get("event_id") or 0)
        if event_id > 0 and event_id in self._reconciled_estop_event_ids:
            return

        try:
            await self._probe_irr_state(task=task, plan=plan, now=now, expected=expected)
        except TaskExecutionError as exc:
            EMERGENCY_STOP_RECONCILE.labels(
                topology=self._task_topology(task=task),
                stage=self._task_stage(task=task) or "unknown",
                outcome="failed",
            ).inc()
            send_service_log(
                service="automation-engine",
                level="error",
                message="AE3 emergency-stop reconcile failed",
                context={
                    "zone_id": int(getattr(task, "zone_id", 0) or 0) or None,
                    "task_id": int(getattr(task, "id", 0) or 0) or None,
                    "topology": self._task_topology(task=task) or None,
                    "stage": self._task_stage(task=task) or None,
                    "error_code": "emergency_stop_activated",
                    "error_message": str(exc),
                },
            )
            raise TaskExecutionError(
                "emergency_stop_activated",
                f"Физический E-Stop активирован и stage не восстановил ожидаемое состояние: {exc}",
            ) from exc

        EMERGENCY_STOP_RECONCILE.labels(
            topology=self._task_topology(task=task),
            stage=self._task_stage(task=task) or "unknown",
            outcome="restored",
        ).inc()
        send_service_log(
            service="automation-engine",
            level="info",
            message="AE3 emergency-stop reconcile restored expected state",
            context={
                "zone_id": int(getattr(task, "zone_id", 0) or 0) or None,
                "task_id": int(getattr(task, "id", 0) or 0) or None,
                "topology": self._task_topology(task=task) or None,
                "stage": self._task_stage(task=task) or None,
            },
        )
        if event_id > 0:
            self._reconciled_estop_event_ids.add(event_id)

    # ── Probe IRR state (hardware safety check) ─────────────────────

    async def _probe_irr_state(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        expected: Mapping[str, bool],
    ) -> None:
        """Отправляет probe-команду и проверяет, что состояние hardware совпадает с ожиданиями."""
        probe_cmds = plan.named_plans.get("irr_state_probe", ())
        if not probe_cmds:
            raise TaskExecutionError(
                "irr_state_probe_plan_missing",
                f"Для stage={getattr(task, 'current_stage', None)} отсутствует command plan зонда IRR state",
            )
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        last_state: Mapping[str, Any] = {}
        last_probe_cmd_id: str | None = None
        total_attempts = 1 + self._IRR_STATE_PROBE_RETRY_COUNT

        for attempt_index in range(total_attempts):
            result = await self._command_gateway.run_batch(
                task=task,
                commands=probe_cmds,
                now=now,
                track_task_state=False,
            )
            if not result["success"]:
                raise TaskExecutionError(
                    str(result["error_code"]), str(result["error_message"]),
                )
            probe_cmd_id = self._extract_probe_cmd_id(result=result)
            state = await self._read_probe_state_with_retry(
                task=task,
                runtime=runtime,
                expected=expected,
                expected_cmd_id=probe_cmd_id,
            )
            last_state = state
            last_probe_cmd_id = probe_cmd_id
            if not self._probe_state_needs_retry(
                state=state,
                expected=expected,
                expected_cmd_id=probe_cmd_id,
            ):
                self._remember_probe_state(task=task, state=state)
                return
            if attempt_index + 1 < total_attempts:
                await asyncio.sleep(self._IRR_STATE_PROBE_RETRY_DELAY_SEC)

        reason = self._classify_probe_failure_reason(
            state=last_state,
            expected=expected,
            expected_cmd_id=last_probe_cmd_id,
        )
        await self._log_probe_failure_event(
            task=task,
            expected=expected,
            expected_cmd_id=last_probe_cmd_id,
            state=last_state,
            reason=reason,
        )
        if reason == "stale":
            raise TaskExecutionError(
                "irr_state_stale", "Снимок состояния IRR-ноды устарел",
            )
        if reason == "mismatch":
            snapshot = last_state["snapshot"] if isinstance(last_state["snapshot"], Mapping) else {}
            await self._maybe_emit_node_reboot_event(
                task=task,
                plan=plan,
                expected=expected,
                snapshot=snapshot,
            )
            for key, value in expected.items():
                if bool(snapshot.get(key)) != bool(value):
                    raise TaskExecutionError(
                        "irr_state_mismatch",
                        f"Состояние IRR-ноды не совпало по признаку {key}: ожидалось={value}, получено={snapshot.get(key)}",
                    )
        raise TaskExecutionError(
            "irr_state_unavailable", "Снимок состояния IRR-ноды недоступен",
        )

    @staticmethod
    def _is_node_reboot_pattern(
        *,
        expected: Mapping[str, bool],
        snapshot: Mapping[str, Any],
    ) -> tuple[bool, list[str]]:
        """Эвристика: все ожидаемые truthy-поля стали ``False`` в snapshot.

        Это типичный паттерн boot defaults после перезагрузки ESP32 / firmware
        fail-safe (watchdog, brownout, сработавший firmware-side guard сбрасывает
        valves/pump в ``False``). Возвращает ``(is_reboot, diverged_keys)``.
        """
        truthy_expected = [k for k, v in expected.items() if bool(v)]
        if not truthy_expected:
            return False, []
        diverged = [k for k in truthy_expected if not bool(snapshot.get(k))]
        return len(diverged) == len(truthy_expected), diverged

    async def _maybe_emit_node_reboot_event(
        self,
        *,
        task: Any,
        plan: Any,
        expected: Mapping[str, bool],
        snapshot: Mapping[str, Any],
    ) -> None:
        """Эмитит ``NODE_REBOOT_DETECTED`` zone-event при boot-defaults паттерне.

        НЕ подавляет последующий ``irr_state_mismatch`` fail-closed: это
        диагностический сигнал для post-mortem (operator/agronomist), а не
        замена safety boundary. Всегда вызывается перед ``raise``.
        """
        is_reboot, diverged_keys = self._is_node_reboot_pattern(
            expected=expected, snapshot=snapshot,
        )
        if not is_reboot:
            return
        node_uid = self._extract_irr_probe_node_uid(plan=plan)
        liveness: Mapping[str, Any] = {}
        read_node_liveness = getattr(self._runtime_monitor, "read_node_liveness", None)
        if node_uid and callable(read_node_liveness):
            try:
                liveness = await read_node_liveness(node_uid=node_uid) or {}
            except Exception:
                _logger.warning(
                    "AE3 не смог прочитать node liveness для NODE_REBOOT_DETECTED node_uid=%s",
                    node_uid,
                    exc_info=True,
                )
        details = {
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
            "node_uid": node_uid,
            "expected": dict(expected),
            "snapshot": dict(snapshot) if isinstance(snapshot, Mapping) else {},
            "diverged_keys": list(diverged_keys),
            "detection_reason": "all_expected_truthy_diverged_to_false",
            "node_status": liveness.get("status") if isinstance(liveness, Mapping) else None,
            "heartbeat_age_sec": (
                liveness.get("heartbeat_age_sec") if isinstance(liveness, Mapping) else None
            ),
            "last_seen_age_sec": (
                liveness.get("last_seen_age_sec") if isinstance(liveness, Mapping) else None
            ),
            "irr_probe_failure_streak": int(getattr(task, "irr_probe_failure_streak", 0) or 0),
        }
        try:
            await create_zone_event(
                int(task.zone_id),
                "NODE_REBOOT_DETECTED",
                with_runtime_event_contract(details),
            )
        except Exception:
            _logger.warning(
                "AE3 не смог записать NODE_REBOOT_DETECTED zone_id=%s task_id=%s node_uid=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                node_uid,
                exc_info=True,
            )
        NODE_REBOOT_DETECTED.labels(
            topology=str(getattr(task, "topology", "") or ""),
            stage=str(getattr(task, "current_stage", "") or ""),
            node_uid=str(node_uid or "unknown"),
        ).inc()
        try:
            send_service_log(
                service="automation-engine",
                level="warning",
                message="AE3 detected ESP32 reboot pattern during IRR state probe",
                context={
                    "zone_id": int(getattr(task, "zone_id", 0) or 0) or None,
                    "task_id": int(getattr(task, "id", 0) or 0) or None,
                    "node_uid": node_uid,
                    "stage": details["stage"],
                    "workflow_phase": details["workflow_phase"],
                    "diverged_keys": list(diverged_keys),
                    "node_status": details["node_status"],
                    "heartbeat_age_sec": details["heartbeat_age_sec"],
                    "irr_probe_failure_streak": details["irr_probe_failure_streak"],
                    "detection_reason": details["detection_reason"],
                },
            )
        except Exception:
            _logger.debug(
                "AE3 send_service_log failed для NODE_REBOOT_DETECTED zone_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                exc_info=True,
            )

    def _extract_irr_probe_node_uid(self, *, plan: Any) -> str | None:
        named_plans = getattr(plan, "named_plans", None) if plan is not None else None
        if not isinstance(named_plans, Mapping):
            return None
        probe_cmds = named_plans.get("irr_state_probe", ())
        for cmd in probe_cmds or ():
            uid = str(getattr(cmd, "node_uid", "") or "").strip()
            if uid:
                return uid
        return None

    async def _probe_irr_state_with_backoff(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        expected: Mapping[str, bool],
        poll_delay_sec: int,
        exhausted_outcome: Any,
    ) -> StageOutcome | None:
        """Resilient probe для poll-based stages (irrigation_check, irrigation_recovery).

        Pre-probe (вариант C): если node offline или heartbeat stale — сразу poll,
        не тратим HL roundtrip. Probe (вариант B): при ``irr_state_unavailable``
        или ``irr_state_stale`` — не кидаем TaskExecutionError, а инкрементируем
        ``ae_tasks.irr_probe_failure_streak``. При достижении лимита — возвращаем
        ``exhausted_outcome`` (fail-closed). Иначе — возвращаем ``StageOutcome(poll)``.

        Hardware mismatch (``irr_state_mismatch``) и другие ошибки пробрасываем
        как TaskExecutionError — это safety-critical события.

        Returns:
            ``None`` если probe успешен (caller продолжает штатный flow).
            ``StageOutcome`` если нужно выйти из handler (poll / fail).
        """
        if self._task_repository is None:
            await self._probe_irr_state(task=task, plan=plan, now=now, expected=expected)
            return None

        node_uid = self._extract_irr_probe_node_uid(plan=plan)
        poll_delay = max(1, int(poll_delay_sec))

        read_node_liveness = getattr(self._runtime_monitor, "read_node_liveness", None)
        if node_uid and callable(read_node_liveness):
            liveness = await read_node_liveness(node_uid=node_uid)
            heartbeat_age = liveness.get("heartbeat_age_sec")
            status = str(liveness.get("status") or "").strip().lower()
            unreachable = (
                liveness.get("found") is True
                and (
                    status == "offline"
                    or (
                        heartbeat_age is not None
                        and float(heartbeat_age) > self._IRR_PROBE_NODE_UNREACHABLE_HEARTBEAT_AGE_SEC
                    )
                )
            )
            if unreachable:
                return await self._handle_probe_deferred(
                    task=task,
                    reason="node_unreachable",
                    expected=expected,
                    node_uid=node_uid,
                    liveness=liveness,
                    poll_delay_sec=poll_delay,
                    exhausted_outcome=exhausted_outcome,
                )

        try:
            await self._probe_irr_state(task=task, plan=plan, now=now, expected=expected)
        except TaskExecutionError as exc:
            if getattr(exc, "code", "") in {"irr_state_unavailable", "irr_state_stale"}:
                return await self._handle_probe_deferred(
                    task=task,
                    reason=str(getattr(exc, "code", "") or "irr_state_unavailable"),
                    expected=expected,
                    node_uid=node_uid,
                    liveness=None,
                    poll_delay_sec=poll_delay,
                    exhausted_outcome=exhausted_outcome,
                )
            raise

        # Успех: сбрасываем streak только если он ненулевой, чтобы избежать
        # лишнего UPDATE и не требовать наличия метода в legacy stub'ах.
        current_streak = int(getattr(task, "irr_probe_failure_streak", 0) or 0)
        if current_streak > 0:
            reset_fn = getattr(self._task_repository, "reset_irr_probe_failure_streak", None)
            if callable(reset_fn):
                try:
                    await reset_fn(task_id=int(task.id))
                except Exception:
                    _logger.warning(
                        "AE3 не смог сбросить irr_probe_failure_streak task_id=%s zone_id=%s",
                        int(getattr(task, "id", 0) or 0),
                        int(getattr(task, "zone_id", 0) or 0),
                        exc_info=True,
                    )
        return None

    async def _handle_probe_deferred(
        self,
        *,
        task: Any,
        reason: str,
        expected: Mapping[str, bool],
        node_uid: str | None,
        liveness: Mapping[str, Any] | None,
        poll_delay_sec: int,
        exhausted_outcome: Any,
    ) -> StageOutcome:
        streak = await self._task_repository.increment_irr_probe_failure_streak(
            task_id=int(task.id),
        )
        topology_label = str(getattr(task, "topology", "") or "")
        stage_label = str(getattr(task, "current_stage", "") or "")
        IRR_PROBE_DEFERRED.labels(
            topology=topology_label, stage=stage_label, reason=str(reason or "unknown"),
        ).inc()
        details: dict[str, Any] = {
            "stage": stage_label,
            "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
            "reason": reason,
            "streak": int(streak),
            "streak_limit": int(self._IRR_PROBE_FAILURE_STREAK_LIMIT),
            "expected": dict(expected),
            "node_uid": node_uid,
        }
        if isinstance(liveness, Mapping):
            details["node_status"] = liveness.get("status")
            details["heartbeat_age_sec"] = liveness.get("heartbeat_age_sec")
            details["last_seen_age_sec"] = liveness.get("last_seen_age_sec")
        exhausted = streak >= self._IRR_PROBE_FAILURE_STREAK_LIMIT
        event_type = "IRR_STATE_PROBE_STREAK_EXHAUSTED" if exhausted else "IRR_STATE_PROBE_DEFERRED"
        try:
            await create_zone_event(
                int(task.zone_id),
                event_type,
                with_runtime_event_contract(details),
            )
        except Exception:
            _logger.warning(
                "AE3 не смог записать %s zone_id=%s task_id=%s",
                event_type,
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                exc_info=True,
            )
        if exhausted:
            IRR_PROBE_STREAK_EXHAUSTED.labels(
                topology=topology_label, stage=stage_label,
            ).inc()
            try:
                await send_biz_alert(
                    code="biz_irr_probe_streak_exhausted",
                    alert_type="AE3 IRR Probe Streak Exhausted",
                    message=(
                        "IRR-нода недоступна: исчерпан лимит подряд идущих "
                        f"probe-deferrals ({self._IRR_PROBE_FAILURE_STREAK_LIMIT})."
                    ),
                    severity="warning",
                    zone_id=int(getattr(task, "zone_id", 0) or 0) or None,
                    node_uid=node_uid,
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "stage": str(getattr(task, "current_stage", "") or ""),
                        "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
                        "reason": reason,
                        "streak": int(streak),
                        "streak_limit": int(self._IRR_PROBE_FAILURE_STREAK_LIMIT),
                        "expected": dict(expected),
                        "node_uid": node_uid,
                        "component": "handler:irr_probe_backoff",
                    },
                    scope_parts=("irr_probe_streak_exhausted",),
                )
            except Exception:
                _logger.warning(
                    "AE3 не смог отправить biz_irr_probe_streak_exhausted alert "
                    "zone_id=%s task_id=%s",
                    int(getattr(task, "zone_id", 0) or 0),
                    int(getattr(task, "id", 0) or 0),
                    exc_info=True,
                )
            return exhausted_outcome
        return StageOutcome(kind="poll", due_delay_sec=int(poll_delay_sec))

    def _classify_probe_failure_reason(
        self,
        *,
        state: Mapping[str, Any],
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> str:
        if not state.get("has_snapshot"):
            return "unavailable"
        if state.get("is_stale"):
            return "stale"
        if expected_cmd_id is not None and str(state.get("cmd_id") or "").strip() != expected_cmd_id:
            return "cmd_id_mismatch"
        snapshot = state.get("snapshot")
        if not isinstance(snapshot, Mapping):
            return "unavailable"
        for key, value in expected.items():
            if bool(snapshot.get(key)) != bool(value):
                return "mismatch"
        return "unavailable"

    async def _read_probe_state_with_retry(
        self,
        *,
        task: Any,
        runtime: RuntimePlan,
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> Mapping[str, Any]:
        max_age_sec = int(runtime.irr_state_max_age_sec)
        wait_timeout = self._coerce_float(runtime.irr_state_wait_timeout_sec)
        poll_interval = self._coerce_float(getattr(runtime, "irr_state_wait_poll_interval_sec", None))
        timeout_sec = max(0.0, wait_timeout if wait_timeout is not None else 5.0)  # config-literal: fallback probe wait budget
        interval_sec = max(0.05, poll_interval if poll_interval is not None else 0.5)

        state = await self._runtime_monitor.read_latest_irr_state(
            zone_id=task.zone_id,
            max_age_sec=max_age_sec,
            expected_cmd_id=expected_cmd_id,
        )
        if not self._probe_state_needs_retry(
            state=state,
            expected=expected,
            expected_cmd_id=expected_cmd_id,
        ) or timeout_sec <= 0.0:
            return state

        deadline = monotonic() + timeout_sec
        while monotonic() < deadline:
            await asyncio.sleep(min(interval_sec, max(0.0, deadline - monotonic())))
            state = await self._runtime_monitor.read_latest_irr_state(
                zone_id=task.zone_id,
                max_age_sec=max_age_sec,
                expected_cmd_id=expected_cmd_id,
            )
            if not self._probe_state_needs_retry(
                state=state,
                expected=expected,
                expected_cmd_id=expected_cmd_id,
            ):
                return state
        return state

    def _probe_state_needs_retry(
        self,
        *,
        state: Mapping[str, Any],
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> bool:
        if not state.get("has_snapshot") or state.get("is_stale"):
            return True
        if expected_cmd_id is not None and str(state.get("cmd_id") or "").strip() != expected_cmd_id:
            return True
        snapshot = state.get("snapshot")
        if not isinstance(snapshot, Mapping):
            return True
        for key, value in expected.items():
            if bool(snapshot.get(key)) != bool(value):
                return True
        return False

    def _extract_probe_cmd_id(self, *, result: Mapping[str, Any]) -> str | None:
        statuses = result.get("command_statuses")
        if not isinstance(statuses, Sequence):
            return None
        for item in reversed(statuses):
            if not isinstance(item, Mapping):
                continue
            probe_cmd_id = str(item.get("legacy_cmd_id") or "").strip()
            if probe_cmd_id:
                return probe_cmd_id
        return None

    async def _log_probe_failure_event(
        self,
        *,
        task: Any,
        expected: Mapping[str, bool],
        expected_cmd_id: str | None,
        state: Mapping[str, Any],
        reason: str,
    ) -> None:
        snapshot = state.get("snapshot") if isinstance(state.get("snapshot"), Mapping) else {}
        try:
            await create_zone_event(
                int(task.zone_id),
                "IRR_STATE_PROBE_FAILED",
                with_runtime_event_contract({
                    "stage": str(getattr(task, "current_stage", "") or ""),
                    "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
                    "reason": str(reason or ""),
                    "expected": dict(expected),
                    "expected_cmd_id": expected_cmd_id,
                    "has_snapshot": bool(state.get("has_snapshot")),
                    "is_stale": bool(state.get("is_stale")),
                    "cmd_id": state.get("cmd_id"),
                    "snapshot": dict(snapshot) if isinstance(snapshot, Mapping) else {},
                }),
            )
        except Exception:
            _logger.warning(
                "AE3 не смог записать IRR_STATE_PROBE_FAILED zone_id=%s task_id=%s stage=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                str(getattr(task, "current_stage", "") or ""),
                exc_info=True,
            )

    # ── Level switch reading ────────────────────────────────────────

    def _remember_probe_state(self, *, task: Any, state: Mapping[str, Any]) -> None:
        snapshot = state.get("snapshot")
        stored_snapshot = dict(snapshot) if isinstance(snapshot, Mapping) else None
        self._last_probe_state = {
            "zone_id": int(getattr(task, "zone_id", 0) or 0),
            "task_id": int(getattr(task, "id", 0) or 0),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "state": {
                "has_snapshot": bool(state.get("has_snapshot")),
                "is_stale": bool(state.get("is_stale")),
                "snapshot": stored_snapshot,
                "sample_age_sec": state.get("sample_age_sec"),
                "created_at": state.get("created_at"),
                "cmd_id": state.get("cmd_id"),
                "event_id": state.get("event_id"),
            },
        }

    def _probe_state_for_task(self, *, task: Any) -> Mapping[str, Any] | None:
        probe_ctx = self._last_probe_state
        if not isinstance(probe_ctx, Mapping):
            return None
        if int(probe_ctx.get("zone_id", 0) or 0) != int(getattr(task, "zone_id", 0) or 0):
            return None
        if int(probe_ctx.get("task_id", 0) or 0) != int(getattr(task, "id", 0) or 0):
            return None
        if str(probe_ctx.get("stage", "") or "") != str(getattr(task, "current_stage", "") or ""):
            return None
        state = probe_ctx.get("state")
        return state if isinstance(state, Mapping) else None

    def _probe_snapshot_context(self, *, task: Any) -> Mapping[str, Any] | None:
        state = self._probe_state_for_task(task=task)
        if not isinstance(state, Mapping):
            return None
        if not bool(state.get("has_snapshot")) or bool(state.get("is_stale")):
            return None

        event_id_raw = state.get("event_id")
        try:
            event_id = int(event_id_raw) if event_id_raw is not None else None
        except (TypeError, ValueError):
            event_id = None

        created_at = state.get("created_at")
        created_at_iso = created_at.isoformat() if isinstance(created_at, datetime) else None
        cmd_id = str(state.get("cmd_id") or "").strip() or None

        context = {
            "snapshot_event_id": event_id if event_id and event_id > 0 else None,
            "snapshot_created_at": created_at_iso,
            "snapshot_cmd_id": cmd_id,
            "snapshot_source_event_type": "IRR_STATE_SNAPSHOT",
        }
        return {key: value for key, value in context.items() if value is not None}

    def _probe_snapshot_correction_fields(self, *, task: Any) -> Mapping[str, Any]:
        state = self._probe_state_for_task(task=task)
        if not isinstance(state, Mapping):
            return {}
        if not bool(state.get("has_snapshot")) or bool(state.get("is_stale")):
            return {}

        event_id_raw = state.get("event_id")
        try:
            event_id = int(event_id_raw) if event_id_raw is not None else None
        except (TypeError, ValueError):
            event_id = None

        created_at = state.get("created_at")
        cmd_id = str(state.get("cmd_id") or "").strip() or None
        fields = {
            "snapshot_event_id": event_id if event_id and event_id > 0 else None,
            "snapshot_created_at": created_at if isinstance(created_at, datetime) else None,
            "snapshot_cmd_id": cmd_id,
            "snapshot_source_event_type": "IRR_STATE_SNAPSHOT",
        }
        return {key: value for key, value in fields.items() if value is not None}

    def _read_probe_level_snapshot(
        self,
        *,
        task: Any,
        labels: Sequence[str],
        threshold: float,
        telemetry_max_age_sec: int,
    ) -> Mapping[str, Any] | None:
        state = self._probe_state_for_task(task=task)
        if not isinstance(state, Mapping):
            return None
        if not bool(state.get("has_snapshot")) or bool(state.get("is_stale")):
            return None
        snapshot = state.get("snapshot")
        if not isinstance(snapshot, Mapping):
            return None
        age_sec = self._coerce_float(state.get("sample_age_sec"))
        if age_sec is not None and age_sec > max(0, int(telemetry_max_age_sec)):
            return None
        lookup = self._lookup_level_value_in_probe_snapshot(snapshot=snapshot, labels=labels)
        if lookup is None:
            return None
        resolved_label, is_triggered = lookup
        sample_ts = state.get("created_at")
        return {
            "sensor_label": resolved_label,
            "level": 1.0 if is_triggered else 0.0,
            "sample_ts": sample_ts,
            "sample_age_sec": age_sec,
            "has_level": True,
            "is_stale": False,
            "is_triggered": is_triggered,
            "expected_labels": list(labels),
            "source": "irr_state_snapshot",
        }

    def _lookup_level_value_in_probe_snapshot(
        self,
        *,
        snapshot: Mapping[str, Any],
        labels: Sequence[str],
    ) -> tuple[str, bool] | None:
        normalized_snapshot = {
            str(key or "").strip().lower(): value
            for key, value in snapshot.items()
            if str(key or "").strip()
        }
        for label in labels:
            normalized_label = str(label or "").strip().lower()
            if normalized_label == "":
                continue
            aliases = self._level_snapshot_aliases(normalized_label)
            for alias in aliases:
                if alias not in normalized_snapshot:
                    continue
                coerced_value = self._coerce_probe_level_switch_value(normalized_snapshot[alias])
                if coerced_value is None:
                    continue
                return alias, coerced_value
        return None

    def _level_snapshot_aliases(self, label: str) -> tuple[str, ...]:
        return level_snapshot_aliases(label)

    def _coerce_probe_level_switch_value(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value) != 0.0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "on", "yes"}:
                return True
            if normalized in {"0", "false", "off", "no"}:
                return False
        return None

    async def _read_level(
        self,
        *,
        task: Any,
        zone_id: int,
        labels: Sequence[str],
        threshold: float,
        telemetry_max_age_sec: int,
        unavailable_error: str,
        stale_error: str,
        stale_recheck_delay_sec: float | None = None,
        prefer_probe_snapshot: bool = False,
    ) -> Mapping[str, Any]:
        level = await self._runtime_monitor.read_level_switch(
            zone_id=zone_id,
            sensor_labels=labels,
            threshold=threshold,
            telemetry_max_age_sec=telemetry_max_age_sec,
            allow_initial_event_fallback=True,
        )
        if prefer_probe_snapshot:
            probe_level = self._read_probe_level_snapshot(
                task=task,
                labels=labels,
                threshold=threshold,
                telemetry_max_age_sec=telemetry_max_age_sec,
            )
            if probe_level is not None and self._should_use_probe_level(
                probe_level=probe_level,
                runtime_level=level,
            ):
                self._log_level_state(
                    task=task,
                    labels=labels,
                    level=probe_level,
                    telemetry_max_age_sec=telemetry_max_age_sec,
                    reason="probe_snapshot_used",
                    log_method=_logger.info,
                )
                return probe_level
        if not level["has_level"]:
            raise TaskExecutionError(
                unavailable_error, f"Недоступен датчик уровня: {labels}",
            )
        if level["is_stale"]:
            self._log_level_state(
                task=task,
                labels=labels,
                level=level,
                telemetry_max_age_sec=telemetry_max_age_sec,
                reason="stale_first_read",
            )
            if stale_recheck_delay_sec is not None and stale_recheck_delay_sec > 0:
                await asyncio.sleep(stale_recheck_delay_sec)
                refreshed_level = await self._runtime_monitor.read_level_switch(
                    zone_id=zone_id,
                    sensor_labels=labels,
                    threshold=threshold,
                    telemetry_max_age_sec=telemetry_max_age_sec,
                    allow_initial_event_fallback=True,
                )
                if refreshed_level["has_level"] and not refreshed_level["is_stale"]:
                    self._log_level_state(
                        task=task,
                        labels=labels,
                        level=refreshed_level,
                        telemetry_max_age_sec=telemetry_max_age_sec,
                        reason="stale_recheck_recovered",
                        log_method=_logger.info,
                    )
                    return refreshed_level
                self._log_level_state(
                    task=task,
                    labels=labels,
                    level=refreshed_level,
                    telemetry_max_age_sec=telemetry_max_age_sec,
                    reason="stale_recheck_failed",
                )
            raise TaskExecutionError(
                stale_error, f"Данные датчика уровня устарели: {labels}",
            )
        return level

    def _should_use_probe_level(
        self,
        *,
        probe_level: Mapping[str, Any],
        runtime_level: Mapping[str, Any],
    ) -> bool:
        if not bool(probe_level.get("has_level")) or bool(probe_level.get("is_stale")):
            return False
        if not bool(runtime_level.get("has_level")) or bool(runtime_level.get("is_stale")):
            return True

        probe_ts = probe_level.get("sample_ts")
        runtime_ts = runtime_level.get("sample_ts")
        if isinstance(probe_ts, datetime) and isinstance(runtime_ts, datetime):
            return probe_ts > runtime_ts
        if isinstance(probe_ts, datetime) and runtime_ts is None:
            return True
        return False

    def _log_level_state(
        self,
        *,
        task: Any,
        labels: Sequence[str],
        level: Mapping[str, Any],
        telemetry_max_age_sec: int,
        reason: str,
        log_method: Any = _logger.warning,
    ) -> None:
        sample_ts = level.get("sample_ts")
        serialized_sample_ts = sample_ts.isoformat() if hasattr(sample_ts, "isoformat") else sample_ts
        log_method(
            "AE3 level read zone_id=%s task_id=%s stage=%s reason=%s labels=%s sample_ts=%s sample_age_sec=%s "
            "telemetry_max_age_sec=%s has_level=%s is_stale=%s is_triggered=%s source=%s",
            int(getattr(task, "zone_id", 0) or 0),
            int(getattr(task, "id", 0) or 0),
            str(getattr(task, "current_stage", "") or ""),
            str(reason or ""),
            list(labels),
            serialized_sample_ts,
            level.get("sample_age_sec"),
            int(telemetry_max_age_sec),
            bool(level.get("has_level")),
            bool(level.get("is_stale")),
            bool(level.get("is_triggered")),
            str(level.get("source") or "telemetry_last"),
        )

    # ── PH/EC target evaluation ─────────────────────────────────────

    async def _targets_reached(
        self, *, task: Any, plan: Any, now: datetime, runtime: Any = None,
    ) -> bool:
        # Phase 5: accept hot-swapped runtime override.
        if runtime is None:
            runtime = self._require_runtime_plan(plan=plan)
        max_age = int(runtime.telemetry_max_age_sec)
        correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
        process_cfg = self._process_cfg_for_task(task=task, runtime=runtime)
        ph = await self._read_target_metric_window(
            zone_id=task.zone_id,
            sensor_type="PH",
            telemetry_max_age_sec=max_age,
            config=self._observation_config(kind="ph", correction_cfg=correction_cfg, process_cfg=process_cfg),
            unavailable_error="two_tank_prepare_targets_unavailable",
            stale_error="two_tank_prepare_targets_stale",
            now=now,
        )
        ec = await self._read_target_metric_window(
            zone_id=task.zone_id,
            sensor_type="EC",
            telemetry_max_age_sec=max_age,
            config=self._observation_config(kind="ec", correction_cfg=correction_cfg, process_cfg=process_cfg),
            unavailable_error="two_tank_prepare_targets_unavailable",
            stale_error="two_tank_prepare_targets_stale",
            now=now,
        )
        if not ph["ready"] or not ec["ready"]:
            return False
        tolerance = self._prepare_tolerance_for_task(task=task, runtime=runtime)
        ph_target = self._effective_ph_target(task=task, runtime=runtime)
        ec_target = self._effective_ec_target(task=task, runtime=runtime)
        current_ph = float(ph["value"])
        current_ec = float(ec["value"])
        # Correction success stays aligned with the canonical target tolerance.
        ph_tol = abs(ph_target) * (
            self._required_prepare_tolerance_pct(tolerance=tolerance, key="ph_pct") / 100.0
        )
        ec_tol = abs(ec_target) * (
            self._required_prepare_tolerance_pct(tolerance=tolerance, key="ec_pct") / 100.0
        )
        ph_min = ph_target - ph_tol
        ph_max = ph_target + ph_tol
        ec_min = ec_target - ec_tol
        ec_max = ec_target + ec_tol
        return ph_min <= current_ph <= ph_max and ec_min <= current_ec <= ec_max

    async def _workflow_ready_reached(
        self, *, task: Any, plan: Any, now: datetime, runtime: Any = None,
    ) -> bool:
        # Phase 5: accept hot-swapped runtime from handler. Falls back to
        # plan.runtime when caller didn't opt into live-mode reassignment.
        if runtime is None:
            runtime = self._require_runtime_plan(plan=plan)
        max_age = int(runtime.telemetry_max_age_sec)
        correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
        process_cfg = self._process_cfg_for_task(task=task, runtime=runtime)
        ph = await self._read_target_metric_window(
            zone_id=task.zone_id,
            sensor_type="PH",
            telemetry_max_age_sec=max_age,
            config=self._observation_config(kind="ph", correction_cfg=correction_cfg, process_cfg=process_cfg),
            unavailable_error="two_tank_prepare_targets_unavailable",
            stale_error="two_tank_prepare_targets_stale",
            now=now,
        )
        ec = await self._read_target_metric_window(
            zone_id=task.zone_id,
            sensor_type="EC",
            telemetry_max_age_sec=max_age,
            config=self._observation_config(kind="ec", correction_cfg=correction_cfg, process_cfg=process_cfg),
            unavailable_error="two_tank_prepare_targets_unavailable",
            stale_error="two_tank_prepare_targets_stale",
            now=now,
        )
        if not ph["ready"] or not ec["ready"]:
            return False
        return self._workflow_ready_values_match(
            task=task,
            runtime=runtime,
            current_ph=float(ph["value"]),
            current_ec=float(ec["value"]),
        )

    def _workflow_ready_values_match(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
    ) -> bool:
        tolerance = self._prepare_tolerance_for_task(task=task, runtime=runtime)
        ph_target = self._effective_ph_target(task=task, runtime=runtime)
        ec_target = self._effective_ec_target(task=task, runtime=runtime)
        ph_ok = self._value_matches_ready_band(
            current=current_ph,
            target=ph_target,
            tolerance_pct=self._required_prepare_tolerance_pct(tolerance=tolerance, key="ph_pct"),
            explicit_min=self._effective_ph_min(task=task, runtime=runtime),
            explicit_max=self._effective_ph_max(task=task, runtime=runtime),
        )
        ec_ok = self._value_matches_ready_band(
            current=current_ec,
            target=ec_target,
            tolerance_pct=self._required_prepare_tolerance_pct(tolerance=tolerance, key="ec_pct"),
            explicit_min=self._effective_ec_min(task=task, runtime=runtime),
            explicit_max=self._effective_ec_max(task=task, runtime=runtime),
        )
        return ph_ok and ec_ok

    def _value_matches_ready_band(
        self,
        *,
        current: float,
        target: float,
        tolerance_pct: float,
        explicit_min: float | None,
        explicit_max: float | None,
    ) -> bool:
        if (
            explicit_min is not None
            and explicit_max is not None
            and math.isfinite(explicit_min)
            and math.isfinite(explicit_max)
            and explicit_min <= explicit_max
        ):
            return explicit_min <= current <= explicit_max
        tolerance = abs(target) * (float(tolerance_pct) / 100.0)
        return (target - tolerance) <= current <= (target + tolerance)

    async def _read_target_metric_window(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        telemetry_max_age_sec: int,
        config: Mapping[str, Any],
        unavailable_error: str,
        stale_error: str,
        now: datetime,
    ) -> Mapping[str, Any]:
        since_ts = self._decision_window_since_ts(now=now, config=config)
        window = await self._runtime_monitor.read_metric_window(
            zone_id=zone_id,
            sensor_type=sensor_type,
            since_ts=since_ts,
            telemetry_max_age_sec=telemetry_max_age_sec,
        )
        if not window["has_sensor"]:
            raise TaskExecutionError(
                unavailable_error,
                f"Телеметрия {sensor_type} недоступна для оценки target",
            )
        if window["is_stale"]:
            raise TaskExecutionError(
                stale_error,
                f"Телеметрия {sensor_type} устарела для оценки target",
            )
        summary = self._summarize_metric_window(
            samples=window["samples"],
            window_min_samples=int(config["window_min_samples"]),
            stability_max_slope=float(config["stability_max_slope"]),
        )
        if not summary["ready"]:
            return {"ready": False, "reason": summary.get("reason")}
        # Sanity bounds на абсолютные значения: если датчик вернул error code
        # (например, pH=-1 при disconnect или EC=999 при short-circuit), не
        # передаём это в PID — иначе integrator накопит спайк и выдаст runaway
        # dose. Возвращаем ready=False с reason, handler сделает retry на
        # следующем tick (те же механики, что у stale/window_not_ready).
        if not self._sensor_value_in_bounds(sensor_type=sensor_type, value=summary["value"]):
            _logger.warning(
                "Sensor value out of sanity bounds: sensor_type=%s value=%s zone_id=%s",
                sensor_type, summary["value"], zone_id,
            )
            return {"ready": False, "reason": "sensor_out_of_bounds"}
        return {
            "ready": True,
            "value": summary["value"],
            "sample_count": summary["sample_count"],
            "slope": summary["slope"],
        }

    @staticmethod
    def _sensor_value_in_bounds(*, sensor_type: str, value: Any) -> bool:
        """Возвращает True если значение физически валидно для данного типа.

        Bounds — абсолютные sanity-пределы, не пересекаются с recipe-таргетами.
        Отсеивают явные error codes от датчиков (pH=-1 при disconnect,
        EC=999 при short-circuit и т.п.), которые иначе прошли бы stability-
        фильтр и сломали PID integrator.
        """
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(numeric):
            return False
        key = (sensor_type or "").strip().upper()
        if key == "PH":
            return 0.0 <= numeric <= 14.0
        if key == "EC":
            return 0.0 <= numeric <= 20.0
        return True

    def _decision_window_since_ts(self, *, now: datetime, config: Mapping[str, Any]) -> datetime:
        return _telemetry_decision_window_since_ts(now=now, config=config)

    @staticmethod
    def _mapping_value(mapping: Any, key: str) -> Any:
        if isinstance(mapping, Mapping):
            if key not in mapping:
                return _MISSING_CONFIG
            return mapping[key]
        if mapping is None or not hasattr(mapping, key):
            return _MISSING_CONFIG
        return getattr(mapping, key)

    def _required_config_int(
        self,
        *,
        field_name: str,
        candidates: Sequence[tuple[str, Any]],
        minimum: int,
        error_code: str = ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
    ) -> int:
        for source_name, raw in candidates:
            if raw is _MISSING_CONFIG:
                continue
            if raw is None or isinstance(raw, bool):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                )
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                ) from None
            if value < minimum:
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}: требуется >= {minimum}",
                )
            return value

        raise TaskExecutionError(
            error_code,
            f"Отсутствует обязательный параметр {field_name}",
        )

    def _required_config_float(
        self,
        *,
        field_name: str,
        candidates: Sequence[tuple[str, Any]],
        minimum: float,
        error_code: str = ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
    ) -> float:
        for source_name, raw in candidates:
            if raw is _MISSING_CONFIG:
                continue
            if raw is None or isinstance(raw, bool):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                )
            try:
                value = float(raw)
            except (TypeError, ValueError):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                ) from None
            if not math.isfinite(value) or value < minimum:
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}: требуется >= {minimum}",
                )
            return value

        raise TaskExecutionError(
            error_code,
            f"Отсутствует обязательный параметр {field_name}",
        )

    def _required_correction_int(
        self,
        *,
        correction_cfg: Mapping[str, Any],
        key: str,
        minimum: int = 1,
    ) -> int:
        return self._required_config_int(
            field_name=f"correction.{key}",
            candidates=((f"correction.{key}", self._mapping_value(correction_cfg, key)),),
            minimum=minimum,
        )

    def _required_prepare_tolerance_pct(
        self,
        *,
        tolerance: Mapping[str, Any],
        key: str,
    ) -> float:
        return self._required_config_float(
            field_name=f"prepare_tolerance.{key}",
            candidates=((f"prepare_tolerance.{key}", self._mapping_value(tolerance, key)),),
            minimum=0.1,
        )

    def _prepare_tolerance_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        phase_key = self._runtime_phase_key(task=task)
        phase_cfg = runtime.prepare_tolerance_by_phase.get(phase_key)
        if phase_cfg is not None:
            return phase_cfg
        generic_cfg = runtime.prepare_tolerance_by_phase.get("generic")
        if generic_cfg is not None:
            return generic_cfg
        if runtime.prepare_tolerance is not None:
            return runtime.prepare_tolerance
        raise TaskExecutionError(
            ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
            f"Отсутствует обязательный prepare_tolerance для phase={self._runtime_phase_key(task=task)}",
        )

    def _correction_config_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        phase_key = self._runtime_phase_key(task=task)
        phase_cfg = runtime.correction_by_phase.get(phase_key)
        if phase_cfg is not None:
            return phase_cfg
        generic_cfg = runtime.correction_by_phase.get("generic")
        if generic_cfg is not None:
            return generic_cfg
        if runtime.correction is not None:
            return runtime.correction
        raise TaskExecutionError(
            ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
            f"Отсутствует обязательный correction runtime для phase={self._runtime_phase_key(task=task)}",
        )

    def _process_cfg_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        process_calibrations = runtime.process_calibrations
        phase_key = self._runtime_phase_key(task=task)
        process_cfg = process_calibrations.get(phase_key)
        if process_cfg is not None:
            return process_cfg
        generic_cfg = process_calibrations.get("generic")
        if generic_cfg is not None:
            return generic_cfg
        if phase_key == "irrigation":
            solution_fill_cfg = process_calibrations.get("solution_fill")
            if solution_fill_cfg is not None:
                return solution_fill_cfg
        return {}

    def _observation_config(
        self,
        *,
        kind: str,
        correction_cfg: Mapping[str, Any],
        process_cfg: Mapping[str, Any],
        pid_entry: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        controllers = correction_cfg.get("controllers") if isinstance(correction_cfg.get("controllers"), Mapping) else {}
        controller_cfg = controllers.get(kind) if isinstance(controllers.get(kind), Mapping) else {}
        controller_observe_cfg = (
            controller_cfg.get("observe") if isinstance(controller_cfg.get("observe"), Mapping) else {}
        )
        process_meta = process_cfg.get("meta") if isinstance(process_cfg.get("meta"), Mapping) else {}
        observe_cfg = process_meta.get("observe") if isinstance(process_meta.get("observe"), Mapping) else {}

        telemetry_period_sec = self._required_config_int(
            field_name=f"{kind}.observe.telemetry_period_sec",
            candidates=(
                ("process_calibration.meta.observe.telemetry_period_sec", self._mapping_value(observe_cfg, "telemetry_period_sec")),
                (f"correction.controllers.{kind}.observe.telemetry_period_sec", self._mapping_value(controller_observe_cfg, "telemetry_period_sec")),
                (f"correction.controllers.{kind}.telemetry_period_sec", self._mapping_value(controller_cfg, "telemetry_period_sec")),
            ),
            minimum=1,
        )
        window_min_samples = self._required_config_int(
            field_name=f"{kind}.observe.window_min_samples",
            candidates=(
                ("process_calibration.meta.observe.window_min_samples", self._mapping_value(observe_cfg, "window_min_samples")),
                (f"correction.controllers.{kind}.observe.window_min_samples", self._mapping_value(controller_observe_cfg, "window_min_samples")),
                (f"correction.controllers.{kind}.window_min_samples", self._mapping_value(controller_cfg, "window_min_samples")),
            ),
            minimum=2,  # config-literal: decision window needs at least two samples
        )
        explicit_decision_window_sec = self._required_config_int(
            field_name=f"{kind}.observe.decision_window_sec",
            candidates=(
                ("process_calibration.meta.observe.decision_window_sec", self._mapping_value(observe_cfg, "decision_window_sec")),
                (f"correction.controllers.{kind}.observe.decision_window_sec", self._mapping_value(controller_observe_cfg, "decision_window_sec")),
                (f"correction.controllers.{kind}.decision_window_sec", self._mapping_value(controller_cfg, "decision_window_sec")),
            ),
            minimum=1,
        )
        decision_window_sec = max(
            telemetry_period_sec * window_min_samples,
            explicit_decision_window_sec,
        )
        transport_delay_sec = self._required_config_int(
            field_name=f"{kind}.process_calibration.transport_delay_sec",
            candidates=(
                ("process_calibration.transport_delay_sec", self._mapping_value(process_cfg, "transport_delay_sec")),
                (f"correction.controllers.{kind}.observe.transport_delay_sec", self._mapping_value(controller_observe_cfg, "transport_delay_sec")),
                (f"correction.controllers.{kind}.transport_delay_sec", self._mapping_value(controller_cfg, "transport_delay_sec")),
            ),
            minimum=1,
            error_code="corr_process_calibration_missing",
        )
        settle_sec = self._required_config_int(
            field_name=f"{kind}.process_calibration.settle_sec",
            candidates=(
                ("process_calibration.settle_sec", self._mapping_value(process_cfg, "settle_sec")),
                (f"correction.controllers.{kind}.observe.settle_sec", self._mapping_value(controller_observe_cfg, "settle_sec")),
                (f"correction.controllers.{kind}.settle_sec", self._mapping_value(controller_cfg, "settle_sec")),
            ),
            minimum=1,
            error_code="corr_process_calibration_missing",
        )

        adaptive_timing = self._adaptive_observation_timing(pid_entry=pid_entry)
        learned_transport = adaptive_timing.get("transport_delay_sec")
        learned_settle = adaptive_timing.get("settle_sec")
        if learned_transport is not None:
            transport_delay_sec = max(transport_delay_sec, learned_transport)
        if learned_settle is not None:
            settle_sec = max(settle_sec, learned_settle)
        return {
            "transport_delay_sec": transport_delay_sec,
            "settle_sec": settle_sec,
            "hold_window_sec": transport_delay_sec + settle_sec,
            "telemetry_period_sec": telemetry_period_sec,
            "window_min_samples": window_min_samples,
            "decision_window_sec": decision_window_sec,
            "observe_poll_sec": self._required_config_int(
                field_name=f"{kind}.observe.observe_poll_sec",
                candidates=(
                    ("process_calibration.meta.observe.observe_poll_sec", self._mapping_value(observe_cfg, "observe_poll_sec")),
                    (f"correction.controllers.{kind}.observe.observe_poll_sec", self._mapping_value(controller_observe_cfg, "observe_poll_sec")),
                    (f"correction.controllers.{kind}.observe_poll_sec", self._mapping_value(controller_cfg, "observe_poll_sec")),
                ),
                minimum=1,
            ),
            "min_effect_fraction": self._required_config_float(
                field_name=f"{kind}.observe.min_effect_fraction",
                candidates=(
                    ("process_calibration.meta.observe.min_effect_fraction", self._mapping_value(observe_cfg, "min_effect_fraction")),
                    (f"correction.controllers.{kind}.observe.min_effect_fraction", self._mapping_value(controller_observe_cfg, "min_effect_fraction")),
                    (f"correction.controllers.{kind}.min_effect_fraction", self._mapping_value(controller_cfg, "min_effect_fraction")),
                ),
                minimum=0.01,
            ),
            "stability_max_slope": self._required_config_float(
                field_name=f"{kind}.observe.stability_max_slope",
                candidates=(
                    ("process_calibration.meta.observe.stability_max_slope", self._mapping_value(observe_cfg, "stability_max_slope")),
                    (f"correction.controllers.{kind}.observe.stability_max_slope", self._mapping_value(controller_observe_cfg, "stability_max_slope")),
                    (f"correction.controllers.{kind}.stability_max_slope", self._mapping_value(controller_cfg, "stability_max_slope")),
                ),
                minimum=0.0001,
            ),
            "no_effect_limit": self._required_config_int(
                field_name=f"{kind}.observe.no_effect_consecutive_limit",
                candidates=(
                    ("process_calibration.meta.observe.no_effect_consecutive_limit", self._mapping_value(observe_cfg, "no_effect_consecutive_limit")),
                    (f"correction.controllers.{kind}.observe.no_effect_consecutive_limit", self._mapping_value(controller_observe_cfg, "no_effect_consecutive_limit")),
                    (f"correction.controllers.{kind}.no_effect_consecutive_limit", self._mapping_value(controller_cfg, "no_effect_consecutive_limit")),
                ),
                minimum=1,
            ),
        }

    def _adaptive_observation_timing(self, *, pid_entry: Mapping[str, Any] | None) -> dict[str, int]:
        if not isinstance(pid_entry, Mapping):
            return {}
        stats = pid_entry.get("stats")
        if not isinstance(stats, Mapping):
            return {}
        adaptive = stats.get("adaptive")
        if not isinstance(adaptive, Mapping):
            return {}
        timing = adaptive.get("timing")
        if not isinstance(timing, Mapping):
            return {}
        try:
            observations = int(timing.get("observations") or adaptive.get("observations") or 0)
        except (TypeError, ValueError):
            observations = 0
        if observations < 3:
            return {}

        result: dict[str, int] = {}
        for key in ("transport_delay_sec", "settle_sec"):
            raw = timing.get(f"{key}_ema")
            try:
                value = int(round(float(raw)))
            except (TypeError, ValueError):
                continue
            if value > 0:
                result[key] = value
        return result

    def _summarize_metric_window(
        self,
        *,
        samples: Any,
        window_min_samples: int,
        stability_max_slope: float,
    ) -> dict[str, Any]:
        return _telemetry_summarize_window(
            samples=samples,
            window_min_samples=window_min_samples,
            stability_max_slope=stability_max_slope,
        )

    # ── Per-phase EC target (NPK share для подготовки) ────────────

    def _effective_ec_target(self, *, task: Any, runtime: RuntimePlan) -> float:
        """EC target с учётом текущей фазы workflow и day/night overlay.

        solution_fill / tank_recirc → target_ec_prepare (NPK-доля от полного EC)
        irrigation / irrig_recirc   → target_ec (полный, кумулятивный)

        При day_night_enabled и night-интервале полный target (irrigation-фаза)
        подменяется на day_night.ec.night; prepare target пересчитывается
        пропорционально из runtime["npk_ec_share"] — соотношение NPK сохраняется.
        """
        phase = self._runtime_phase_key(task=task)
        base_full = float(runtime.target_ec)
        full_target = self._day_night_override(runtime, "ec", "target", default=base_full)
        if phase in ("solution_fill", "tank_recirc"):
            prepare = runtime.target_ec_prepare
            if prepare is not None:
                if full_target != base_full and base_full > 0:
                    share = float(runtime.npk_ec_share or (float(prepare) / base_full))
                    return round(full_target * share, 4)
                return float(prepare)
        return full_target

    def _effective_ec_min(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        phase = self._runtime_phase_key(task=task)
        if phase in ("solution_fill", "tank_recirc"):
            base = runtime.target_ec_prepare_min
            if base is not None:
                scaled = self._day_night_override_scaled(
                    runtime, "ec", "min", default=float(base), phase_key="prepare",
                )
                return scaled if scaled is not None else float(base)
        base_val = self._coerce_float(runtime.target_ec_min)
        if base_val is None:
            return None
        return self._day_night_override(runtime, "ec", "min", default=base_val)

    def _effective_ec_max(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        phase = self._runtime_phase_key(task=task)
        if phase in ("solution_fill", "tank_recirc"):
            base = runtime.target_ec_prepare_max
            if base is not None:
                scaled = self._day_night_override_scaled(
                    runtime, "ec", "max", default=float(base), phase_key="prepare",
                )
                return scaled if scaled is not None else float(base)
        base_val = self._coerce_float(runtime.target_ec_max)
        if base_val is None:
            return None
        return self._day_night_override(runtime, "ec", "max", default=base_val)

    def _effective_ph_target(self, *, task: Any, runtime: RuntimePlan) -> float:
        base = float(runtime.target_ph)
        return self._day_night_override(runtime, "ph", "target", default=base)

    def _effective_ph_min(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        base_val = self._coerce_float(runtime.target_ph_min)
        if base_val is None:
            return None
        return self._day_night_override(runtime, "ph", "min", default=base_val)

    def _effective_ph_max(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        base_val = self._coerce_float(runtime.target_ph_max)
        if base_val is None:
            return None
        return self._day_night_override(runtime, "ph", "max", default=base_val)

    # ── Day/Night helpers ────────────────────────────────────────────

    def _day_night_override(
        self,
        runtime: RuntimePlan,
        metric: str,
        kind: str,
        *,
        default: float,
    ) -> float:
        """Возвращает day- или night-значение для metric (ph/ec) и kind (target/min/max).

        Если day_night_enabled=False или значение не задано — возвращает default.
        Day-значение из day_night также используется если задано; иначе — default (что
        соответствует base-таргету фазы, т.е. конвенция: базовый target == day).
        """
        config = runtime.day_night_config
        if config is None or not bool(config.enabled):
            return default
        section = getattr(config, metric, None)
        if not section:
            return default
        is_day = self._is_day_now(config)
        if is_day:
            if kind == "target":
                key = "day"
            else:
                key = f"day_{kind}"
        else:
            if kind == "target":
                key = "night"
            else:
                key = f"night_{kind}"
        value = getattr(section, key, None)
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _day_night_override_scaled(
        self,
        runtime: RuntimePlan,
        metric: str,
        kind: str,
        *,
        default: float,
        phase_key: str,
    ) -> float | None:
        """Для prepare-фазы (solution_fill/tank_recirc) возвращает min/max, масштабированный NPK share."""
        if phase_key != "prepare":
            return default
        base_full = self._coerce_float(getattr(runtime, f"target_ec_{kind}", None))
        if base_full is None or base_full <= 0:
            return default
        overridden_full = self._day_night_override(runtime, metric, kind, default=base_full)
        if overridden_full == base_full:
            return default
        share = float(runtime.npk_ec_share or (default / base_full))
        return round(overridden_full * share, 4)

    @staticmethod
    def _is_day_now(day_night_config: Any) -> bool:
        """Возвращает True если текущее локальное время теплицы попадает в
        дневной интервал.

        Использует day_start_time (HH:MM) + day_hours + timezone (IANA-имя,
        например "Europe/Moscow") из config. Если timezone не задан — fallback
        на UTC. Если day_start_time/day_hours невалидны — возвращает True.
        """
        lighting = getattr(day_night_config, "lighting", None)
        raw_start = getattr(lighting, "day_start_time", None)
        day_hours = getattr(lighting, "day_hours", None)
        if not isinstance(raw_start, str) or not raw_start.strip() or day_hours is None:
            return True
        parts = raw_start.strip().split(":")
        if len(parts) < 2:
            return True
        try:
            start_h = int(parts[0])
            start_m = int(parts[1])
            hours = float(day_hours)
        except (TypeError, ValueError):
            return True
        if not (0 <= start_h <= 23 and 0 <= start_m <= 59):
            return True
        if hours <= 0:
            return False
        if hours >= 24:
            return True

        # Резолвим now в локальном TZ теплицы. `day_start_time` хранится как
        # HH:MM в локальном времени teplicy, поэтому сравнение должно идти в
        # том же TZ. Иначе при UTC-контейнере и TZ=МСК night-targets смещаются
        # на часы разницы.
        tz_name = getattr(lighting, "timezone", None) if isinstance(getattr(lighting, "timezone", None), str) else None
        tz: Any = timezone.utc
        if tz_name:
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = timezone.utc
        now_local = datetime.now(tz)

        start_min = start_h * 60 + start_m
        end_min = (start_min + int(round(hours * 60))) % (24 * 60)
        now_min = now_local.hour * 60 + now_local.minute
        if start_min == end_min:
            return True
        if start_min < end_min:
            return start_min <= now_min < end_min
        return now_min >= start_min or now_min < end_min

    def _runtime_phase_key(self, *, task: Any) -> str:
        workflow = getattr(task, "workflow", None)
        workflow_phase = getattr(workflow, "workflow_phase", None)
        phase = str(workflow_phase or getattr(task, "workflow_phase", "") or "").strip().lower()
        if phase in {"tank_filling", "solution_fill"}:
            return "solution_fill"
        if phase in {"tank_recirc", "prepare_recirculation"}:
            return "tank_recirc"
        if phase in {"irrigating", "irrigation", "irrig_recirc"}:
            return "irrigation"
        stage = str(getattr(task, "current_stage", "") or "").strip().lower()
        if stage.startswith("solution_fill"):
            return "solution_fill"
        if stage.startswith("prepare_recirculation"):
            return "tank_recirc"
        return "generic"

    # ── Sensor consistency check (max=1, min=0 → error) ────────────

    async def _check_sensor_consistency(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        min_labels_key: str,
        min_unavailable_error: str,
        min_stale_error: str,
        stale_recheck_delay_sec: float | None = None,
        prefer_probe_snapshot: bool = False,
    ) -> None:
        """Read min-level sensor and assert it's triggered (consistency with max)."""
        level = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime[min_labels_key],
            threshold=runtime["level_switch_on_threshold"],
            telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
            unavailable_error=min_unavailable_error,
            stale_error=min_stale_error,
            stale_recheck_delay_sec=stale_recheck_delay_sec,
            prefer_probe_snapshot=prefer_probe_snapshot,
        )
        if not level["is_triggered"]:
            raise TaskExecutionError(
                "sensor_state_inconsistent",
                f"Датчики бака противоречат друг другу: max=1 min=0 ({min_labels_key})",
            )

    def _coerce_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
