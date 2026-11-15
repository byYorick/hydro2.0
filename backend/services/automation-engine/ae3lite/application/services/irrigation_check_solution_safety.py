"""IrrigationCheckHandler solution safety: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.hydraulics.failure_report import note_upward_report


@dataclass(frozen=True)
class IrrigationCheckSolutionSafetyPorts:
    observe_fail_safe_transition: Callable[[], Any]
    storage_event_payload: Callable[[], Any]
    task_repository: Callable[[], Any]
    global_irrigation_replay: Callable[..., Any]
    global_irrigation_solution_min: Callable[..., Any]
    global_logger: Callable[..., Any]
    global_create_zone_event: Callable[..., Any]


class IrrigationCheckSolutionSafety:
    def __init__(self, ports: IrrigationCheckSolutionSafetyPorts) -> None:
        self._ports = ports

    def recent_solution_low_event_confirms_active_low(
        self,
        *,
        event: Mapping[str, Any] | None,
        expected: Mapping[str, bool],
    ) -> bool:
        """Decide whether a recorded storage event confirms an actively-low level.

        Audit F11: the fallback chain used for ``level_min_state`` is
        intentional, not redundant. Older MQTT event payloads wrote the
        level-switch flags into the top-level ``state`` key, newer ones moved
        them into the ``snapshot`` sub-dict. We prefer ``state`` because it
        reflects the instantaneous reading, and fall back to ``snapshot`` so
        events serialised by the legacy path still trigger the low-level
        branch. If neither carries the flag we treat it as "not confirmed"
        (the explicit ``False`` return below).
        """
        payload = self._ports.storage_event_payload()(event)
        snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), Mapping) else None
        state = payload.get("state") if isinstance(payload.get("state"), Mapping) else None
        if not isinstance(snapshot, Mapping):
            return False
        for key, value in expected.items():
            if key not in snapshot or bool(snapshot.get(key)) != bool(value):
                return False
        # Preferred source: live state block. Fallback: snapshot block.
        level_min_state = self.event_bool(state, ("level_solution_min", "solution_level_min"))
        if level_min_state is None:
            level_min_state = self.event_bool(snapshot, ("level_solution_min", "solution_level_min"))
        # runtime трактует low-condition как деактивированный нижний switch.
        # If neither payload shape carried the flag at all, level_min_state
        # remains None and we return False — "not confirmed".
        return level_min_state is False

    def event_bool(
        self,
        mapping: Mapping[str, Any] | None,
        keys: tuple[str, ...],
    ) -> bool | None:
        if not isinstance(mapping, Mapping):
            return None
        for key in keys:
            if key in mapping:
                return bool(mapping.get(key))
        return None

    async def solution_min_low_outcome(
        self,
        *,
        task: Any,
        topology: str,
        recovery: dict[str, Any],
        now: datetime,
        observe_duration: Any,
        source: str,
    ) -> StageOutcome:
        self._ports.observe_fail_safe_transition()(
            task=task,
            reason="irrigation_solution_low",
            source=source,
            next_stage="irrigation_stop_to_setup",
        )
        self._ports.global_irrigation_solution_min().labels(topology=topology).inc()
        # Audit F2 fix: compute and check the replay-budget BEFORE any alert or
        # event emission. Order of operations:
        #   1. Detect exhausted → persist+fail immediately
        #   2. Persist incremented counter
        #   3. Only then fire non-critical alerts and observability events
        # Previously alerts were sent before the counter was persisted, so a
        # mid-flow crash (after alert, before persist) would leave the task with
        # stale counter and re-enter the same branch on the next tick — a
        # runaway loop that manifested as repeated solution_min alerts without
        # the replay budget ever actually decrementing.
        max_replays = int(recovery.max_setup_replays or 0)
        next_replay_count = int(getattr(task, "irrigation_replay_count", 0) or 0) + 1
        if next_replay_count > max_replays:
            try:
                await note_upward_report(
                    code="biz_irrigation_replay_exhausted",
                    alert_type="AE3 Irrigation Replay Exhausted",
                    message="Исчерпан бюджет повторов после повторных срабатываний нижнего уровня раствора.",
                    severity="error",
                    zone_id=int(task.zone_id),
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "topology": topology,
                        "stage": "irrigation_check",
                        "next_replay_count": next_replay_count,
                        "max_setup_replays": max_replays,
                    },
                    scope_parts=("stage:irrigation_check",),
                )
            except Exception:
                self._ports.global_logger().warning(
                    "AE3 не смог отправить alert biz_irrigation_replay_exhausted zone_id=%s task_id=%s",
                    int(getattr(task, "zone_id", 0) or 0),
                    int(getattr(task, "id", 0) or 0),
                    exc_info=True,
                )
            return StageOutcome(
                kind="fail",
                error_code="irrigation_solution_min_replay_exhausted",
                error_message="Нижний уровень раствора снова сработал после исчерпания бюджета повторов setup",
            )

        # Persist the incremented counter BEFORE emitting observability. If the
        # persist fails we raise and never send alerts (repository error must
        # not be masked). If alerts later fail, the counter is already safely
        # recorded — next tick sees the updated value and will not loop.
        updated = await self._ports.task_repository().update_irrigation_runtime(
            task_id=int(task.id),
            owner=str(task.claimed_by or ""),
            now=now,
            irrigation_replay_count=next_replay_count,
            claim_generation=int(getattr(task, "claim_generation", 0) or 0),
        )
        if updated is None:
            raise TaskExecutionError("irrigation_replay_persist_failed", "Не удалось сохранить счётчик повторов полива")

        try:
            await self._ports.global_create_zone_event(
                int(task.zone_id),
                "IRRIGATION_SOLUTION_MIN_DETECTED",
                {
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "stage": "irrigation_check",
                    "topology": topology,
                },
            )
        except Exception:
            self._ports.global_logger().warning(
                "AE3 не смог записать IRRIGATION_SOLUTION_MIN_DETECTED zone_id=%s task_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                exc_info=True,
            )
        try:
            await note_upward_report(
                code="biz_irrigation_solution_min",
                alert_type="AE3 Irrigation Solution Min",
                message="Во время полива сработал нижний датчик уровня раствора.",
                severity="warning",
                zone_id=int(task.zone_id),
                details={
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "topology": topology,
                    "stage": "irrigation_check",
                    "irrigation_replay_count": next_replay_count,
                },
                scope_parts=("stage:irrigation_check",),
            )
        except Exception:
            self._ports.global_logger().warning(
                "AE3 не смог отправить alert biz_irrigation_solution_min zone_id=%s task_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                exc_info=True,
            )

        self._ports.global_irrigation_replay().labels(topology=topology).inc()
        observe_duration("setup")
        return StageOutcome(
            kind="transition",
            next_stage="irrigation_stop_to_setup",
            task_override=updated,
        )
