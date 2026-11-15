"""Stage component: probe backoff. Explicit ports; no handler dependency."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.hydraulics.failure_report import note_upward_report
from ae3lite.infrastructure.metrics import (
    IRR_PROBE_DEFERRED,
    IRR_PROBE_STREAK_EXHAUSTED,
)

_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageProbeBackoffPorts:
    irr_probe_failure_streak_limit: Callable[[], Any]
    irr_probe_node_unreachable_heartbeat_age_sec: Callable[[], Any]
    extract_irr_probe_node_uid: Callable[..., Any]
    probe_irr_state: Callable[..., Awaitable[Any]]
    runtime_monitor: Callable[[], Any]
    task_repository: Callable[[], Any]
    create_zone_event: Callable[..., Awaitable[Any]]


class StageProbeBackoff:
    def __init__(self, ports: StageProbeBackoffPorts) -> None:
        self._ports = ports

    async def probe_irr_state_with_backoff(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        expected: Mapping[str, bool],
        poll_delay_sec: int,
        exhausted_outcome: Any,
    ) -> StageOutcome | None:
        """Resilient probe для poll-based stages (irrigation_check и др.).

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
        if self._ports.task_repository() is None:
            await self._ports.probe_irr_state(task=task, plan=plan, now=now, expected=expected)
            return None

        node_uid = self._ports.extract_irr_probe_node_uid(plan=plan)
        poll_delay = max(1, int(poll_delay_sec))

        read_node_liveness = getattr(self._ports.runtime_monitor(), "read_node_liveness", None)
        if node_uid and callable(read_node_liveness):
            liveness = await read_node_liveness(node_uid=node_uid)
            heartbeat_age = liveness.get("heartbeat_age_sec")
            status = str(liveness.get("status") or "").strip().lower()
            unreachable = liveness.get("found") is True and (
                status == "offline"
                or (
                    heartbeat_age is not None
                    and float(heartbeat_age) > self._ports.irr_probe_node_unreachable_heartbeat_age_sec()
                )
            )
            if unreachable:
                return await self.handle_probe_deferred(
                    task=task,
                    reason="node_unreachable",
                    expected=expected,
                    node_uid=node_uid,
                    liveness=liveness,
                    poll_delay_sec=poll_delay,
                    exhausted_outcome=exhausted_outcome,
                )

        try:
            await self._ports.probe_irr_state(task=task, plan=plan, now=now, expected=expected)
        except TaskExecutionError as exc:
            if getattr(exc, "code", "") in {"irr_state_unavailable", "irr_state_stale"}:
                return await self.handle_probe_deferred(
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
            reset_fn = getattr(self._ports.task_repository(), "reset_irr_probe_failure_streak", None)
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

    async def handle_probe_deferred(
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
        streak = await self._ports.task_repository().increment_irr_probe_failure_streak(
            task_id=int(task.id),
        )
        topology_label = str(getattr(task, "topology", "") or "")
        stage_label = str(getattr(task, "current_stage", "") or "")
        IRR_PROBE_DEFERRED.labels(
            topology=topology_label,
            stage=stage_label,
            reason=str(reason or "unknown"),
        ).inc()
        details: dict[str, Any] = {
            "stage": stage_label,
            "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
            "reason": reason,
            "streak": int(streak),
            "streak_limit": int(self._ports.irr_probe_failure_streak_limit()),
            "expected": dict(expected),
            "node_uid": node_uid,
        }
        if isinstance(liveness, Mapping):
            details["node_status"] = liveness.get("status")
            details["heartbeat_age_sec"] = liveness.get("heartbeat_age_sec")
            details["last_seen_age_sec"] = liveness.get("last_seen_age_sec")
        exhausted = streak >= self._ports.irr_probe_failure_streak_limit()
        event_type = "IRR_STATE_PROBE_STREAK_EXHAUSTED" if exhausted else "IRR_STATE_PROBE_DEFERRED"
        try:
            await self._ports.create_zone_event(
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
                topology=topology_label,
                stage=stage_label,
            ).inc()
            if reason in {"node_unreachable", "irr_state_unavailable", "irr_state_stale"} and node_uid:
                from ae3lite.domain.services.zone_node_availability import offline_failure_from_liveness

                failure = offline_failure_from_liveness(
                    zone_id=int(getattr(task, "zone_id", 0) or 0),
                    node_uid=node_uid,
                    liveness=liveness if isinstance(liveness, Mapping) else {},
                )
                return StageOutcome(
                    kind="fail",
                    error_code=failure.code,
                    error_message=failure.message,
                )
            try:
                await note_upward_report(
                    code="biz_irr_probe_streak_exhausted",
                    alert_type="AE3 IRR Probe Streak Exhausted",
                    message=(
                        "IRR-нода недоступна: исчерпан лимит подряд идущих "
                        f"probe-deferrals ({self._ports.irr_probe_failure_streak_limit()})."
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
                        "streak_limit": int(self._ports.irr_probe_failure_streak_limit()),
                        "expected": dict(expected),
                        "node_uid": node_uid,
                        "component": "handler:irr_probe_backoff",
                    },
                    scope_parts=("irr_probe_streak_exhausted",),
                )
            except Exception:
                _logger.warning(
                    "AE3 не смог отправить biz_irr_probe_streak_exhausted alert zone_id=%s task_id=%s",
                    int(getattr(task, "zone_id", 0) or 0),
                    int(getattr(task, "id", 0) or 0),
                    exc_info=True,
                )
            return exhausted_outcome
        return StageOutcome(kind="poll", due_delay_sec=int(poll_delay_sec))
