"""GetZoneAutomationStateUseCase failure overlay: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Optional


@dataclass(frozen=True)
class ZoneStateFailureOverlayPorts:
    normalize_utc_naive: Callable[..., Any]
    primary_automation_state_label: Callable[..., Any]


class ZoneStateFailureOverlay:
    def __init__(self, ports: ZoneStateFailureOverlayPorts) -> None:
        self._ports = ports

    def should_overlay_failed_task_on_workflow(
        self,
        *,
        workflow_state: Optional[Any],
        last_task: Any,
    ) -> bool:
        """Показывать terminal failed поверх workflow только если сбой не устарел относительно workflow."""
        scheduler_task_id = (
            str(getattr(workflow_state, "scheduler_task_id", "") or "").strip() if workflow_state is not None else ""
        )
        last_task_id = str(getattr(last_task, "id", "") or "").strip()
        if scheduler_task_id and last_task_id and scheduler_task_id == last_task_id:
            return True

        if workflow_state is None:
            return True

        workflow_updated_at = getattr(workflow_state, "updated_at", None)
        task_updated_at = getattr(last_task, "updated_at", None)
        if isinstance(workflow_updated_at, datetime) and isinstance(task_updated_at, datetime):
            wf_cmp = self._ports.normalize_utc_naive(workflow_updated_at)
            task_cmp = self._ports.normalize_utc_naive(task_updated_at)
            return task_cmp >= wf_cmp

        return True

    def observability_after_failure_rollback(
        self,
        observability: Any,
        *,
        last_task: Any,
        failed_stage: str,
    ) -> dict[str, Any]:
        if not isinstance(observability, dict):
            return {}
        obs = dict(observability)
        runtime = dict(obs.get("runtime") or {})
        wf = getattr(last_task, "workflow", None)
        stage_entered_at = getattr(wf, "stage_entered_at", None) if wf is not None else None
        completed_at = getattr(last_task, "completed_at", None)
        elapsed: int | None = None
        if isinstance(stage_entered_at, datetime) and isinstance(completed_at, datetime):
            elapsed = max(
                0,
                int(
                    (
                        self._ports.normalize_utc_naive(completed_at)
                        - self._ports.normalize_utc_naive(stage_entered_at)
                    ).total_seconds()
                ),
            )

        runtime["task_id"] = getattr(last_task, "id", None)
        runtime["task_status"] = "failed"
        runtime["task_is_active"] = False
        runtime["current_stage"] = None
        runtime["failed_stage"] = failed_stage or None
        runtime["correction_step"] = None
        runtime["correction_wait_until"] = None
        runtime["correction_wait_remaining_sec"] = None
        runtime["correction_stabilization_sec"] = None
        runtime["stage_deadline_at"] = None
        runtime["stage_deadline_remaining_sec"] = None
        if elapsed is not None:
            runtime["stage_elapsed_sec"] = elapsed
            runtime["waiting_elapsed_sec"] = elapsed

        obs["runtime"] = runtime
        obs["hang_hints"] = [
            hint
            for hint in (obs.get("hang_hints") or [])
            if isinstance(hint, dict)
            and hint.get("code") not in {"workflow_snapshot_stale", "no_active_task_during_workflow"}
        ]
        return obs

    def merge_last_failed_task_into_workflow_view(
        self,
        payload: dict[str, Any],
        last_task: Optional[Any],
        workflow_state: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Снимок workflow в БД может оставаться ready, пока последняя ae_task уже failed — не маскируем свежий сбой."""
        if last_task is None:
            return payload
        status = str(getattr(last_task, "status", "") or "").strip().lower()
        if status != "failed":
            return payload
        if not self.should_overlay_failed_task_on_workflow(
            workflow_state=workflow_state,
            last_task=last_task,
        ):
            return payload

        details = dict(payload.get("state_details") or {})
        details["failed"] = True
        details["error_code"] = getattr(last_task, "error_code", None)
        details["error_message"] = getattr(last_task, "error_message", None)
        details["failed_task_id"] = getattr(last_task, "id", None)
        payload["state_details"] = details

        wf = getattr(last_task, "workflow", None)
        failed_stage = str(getattr(wf, "current_stage", "") or "").strip() if wf is not None else ""

        if self.workflow_failure_rollback_applied(workflow_state):
            payload["state_label"] = self._ports.primary_automation_state_label(
                workflow_phase=str(payload.get("workflow_phase") or "idle"),
                mapped_macro_state=str(payload.get("state") or "IDLE"),
                current_stage=failed_stage,
                is_terminal_failed=True,
            )
            payload["observability"] = self.observability_after_failure_rollback(
                payload.get("observability"),
                last_task=last_task,
                failed_stage=failed_stage,
            )
            return payload

        wf_phase = (
            str(getattr(wf, "workflow_phase", "") or "").strip().lower()
            if wf is not None
            else str(payload.get("workflow_phase") or "").strip().lower()
        )

        payload["state_label"] = self._ports.primary_automation_state_label(
            workflow_phase=wf_phase,
            mapped_macro_state=str(payload.get("state") or "IDLE"),
            current_stage=failed_stage,
            is_terminal_failed=True,
        )
        return payload

    def workflow_failure_rollback_applied(self, workflow_state: Optional[Any]) -> bool:
        if workflow_state is None:
            return False
        payload = getattr(workflow_state, "payload", None)
        normalized_payload = payload if isinstance(payload, Mapping) else {}
        if bool(normalized_payload.get("ae3_failure_rollback")):
            return True
        workflow_phase = str(getattr(workflow_state, "workflow_phase", "") or "").strip().lower()
        rollback_stage = str(normalized_payload.get("ae3_cycle_start_stage") or "").strip().lower()
        return workflow_phase == "idle" and rollback_stage == "failed"
