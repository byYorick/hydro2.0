"""Correction limits: explicit collaborators, per-call task context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Optional

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.correction_shared import _logger, _pid_entry_or_none
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.infrastructure.metrics import (
    CORRECTION_CAP_IGNORED,
    CORRECTION_EXHAUSTED,
    CORRECTION_NO_EFFECT,
)


@dataclass(frozen=True)
class CorrectionLimitsPorts:
    alert_service: Callable[[], Any]
    log_correction_event: Callable[..., Awaitable[Any]]
    require_runtime_plan: Callable[[], Any]
    runtime_config: Callable[[], Any]
    transition_policy: Callable[[], Any]
    transition_to_deactivate_or_return: Callable[..., Any]


class CorrectionLimits:
    def __init__(self, ports: CorrectionLimitsPorts) -> None:
        self._ports = ports

    async def correction_exhausted(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
    ) -> StageOutcome:
        stage = str(task.current_stage)
        topology = str(getattr(task, "topology", "") or "")
        runtime = self._ports.require_runtime_plan()(plan=plan)
        CORRECTION_EXHAUSTED.labels(topology=topology, stage=stage).inc()
        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_EXHAUSTED",
            task=task,
            corr=corr,
            payload={
                "attempt": corr.attempt,
                "max_attempts": corr.max_attempts,
                "ec_attempt": corr.ec_attempt,
                "ec_max_attempts": corr.ec_max_attempts,
                "ph_attempt": corr.ph_attempt,
                "ph_max_attempts": corr.ph_max_attempts,
                "stage": stage,
            },
        )
        await self._ports.alert_service().emit_correction_exhausted(task=task, corr=corr)
        if stage.strip().lower() == "irrigation_check":
            await self._ports.alert_service().emit_irrigation_correction_exhausted(
                task=task,
                corr=corr,
            )
        policy_outcome = self._ports.transition_policy().decide_exhausted_transition(
            current_stage=stage,
            stage_retry_count=task.workflow.stage_retry_count,
            level_poll_interval_sec=int(runtime.level_poll_interval_sec),
        )
        if policy_outcome is not None:
            return policy_outcome
        return self._ports.transition_to_deactivate_or_return(corr=corr, success=False)

    def enforce_attempt_caps(self, *, task: Any) -> bool:
        current_stage = str(getattr(task, "current_stage", "") or "").strip().lower()
        # During solution_fill we keep a single correction window alive for the
        # whole fill stage. Attempt-based exhaustion stays enabled for
        # recirculation windows; fill stops only by no-effect or stage timeout.
        return current_stage != "solution_fill_check"

    def check_no_effect_block(
        self,
        *,
        task: Any,
        correction_cfg: Mapping[str, Any],
        process_cfg: Mapping[str, Any],
        pid_state: Mapping[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Проверяет флаг safety.block_on_active_no_effect_alert.

        Возвращает payload события (dict) если коррекция должна быть
        заблокирована из-за активного no-effect alert, иначе None.
        "Active" определяется через persistent pid_state.no_effect_count
        против observe.no_effect_limit — тот же порог что триггерит alert.
        """
        safety_raw = self._ports.runtime_config().mapping_value(correction_cfg, "safety")
        safety = safety_raw if isinstance(safety_raw, Mapping) else {}
        if not bool(safety.get("block_on_active_no_effect_alert") or False):
            return None

        for pid_type in ("ph", "ec"):
            entry = _pid_entry_or_none(pid_state, pid_type)
            if not entry:
                continue
            count = int(entry.get("no_effect_count") or 0)
            if count <= 0:
                continue
            observe_cfg = self._ports.runtime_config().observation_config(
                kind=pid_type,
                correction_cfg=correction_cfg,
                process_cfg=process_cfg,
                pid_entry=entry,
            )
            limit = int(observe_cfg["no_effect_limit"])
            if limit > 0 and count >= limit:
                return {
                    "pid_type": pid_type,
                    "no_effect_count": count,
                    "no_effect_limit": limit,
                    "reason": "active_no_effect_alert_blocks_correction",
                }
        return None

    def should_reset_attempt_counters_on_reaction(self, *, task: Any) -> bool:
        # Попытки считаются только для последовательных no-effect циклов.
        # Любая наблюдаемая реакция должна сбрасывать окно попыток, независимо от stage.
        return True

    def should_log_limit_policy(self, *, task: Any, corr: CorrectionState) -> bool:
        if self.enforce_attempt_caps(task=task):
            return False
        return (
            not bool(getattr(corr, "limit_policy_logged", False))
            and corr.attempt == 0
            and corr.ec_attempt == 0
            and corr.ph_attempt == 0
            and corr.corr_step == "corr_check"
        )

    async def log_attempt_cap_ignored(
        self,
        *,
        task: Any,
        corr: CorrectionState,
        cap_type: str,
        current_value: int,
        limit_value: int,
    ) -> None:
        topology = str(getattr(task, "topology", "") or "")
        stage = str(getattr(task, "current_stage", "") or "")
        CORRECTION_CAP_IGNORED.labels(
            topology=topology,
            stage=stage,
            cap_type=cap_type,
        ).inc()
        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_ATTEMPT_CAP_IGNORED",
            task=task,
            corr=corr,
            payload={
                "cap_type": cap_type,
                "current_value": current_value,
                "limit_value": limit_value,
                "policy": "fill_continuous_until_no_effect_or_timeout",
            },
        )
        _logger.info(
            "zone %s: ignoring %s attempt cap in solution_fill (%s/%s); correction remains active until no-effect or stage timeout",
            task.zone_id,
            cap_type,
            current_value,
            limit_value,
        )

    async def no_effect_limit_reached(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        pid_type: str,
        baseline_value: float,
        observed_value: float,
        expected_effect: float,
        actual_effect: float,
        threshold_effect: float,
        no_effect_limit: int,
    ) -> StageOutcome:
        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_NO_EFFECT",
            task=task,
            corr=corr,
            payload={
                "pid_type": pid_type,
                "baseline_value": baseline_value,
                "observed_value": observed_value,
                "expected_effect": expected_effect,
                "actual_effect": actual_effect,
                "threshold_effect": threshold_effect,
                "no_effect_limit": no_effect_limit,
            },
        )
        CORRECTION_NO_EFFECT.labels(pid_type=pid_type).inc()
        await self._ports.alert_service().emit_no_effect(
            task=task,
            pid_type=pid_type,
            baseline_value=baseline_value,
            observed_value=observed_value,
            expected_effect=expected_effect,
            actual_effect=actual_effect,
            no_effect_limit=no_effect_limit,
        )
        policy_outcome = self._ports.transition_policy().decide_no_effect_transition(
            current_stage=str(task.current_stage),
            stage_retry_count=task.workflow.stage_retry_count,
        )
        if policy_outcome is not None:
            return policy_outcome
        return self._ports.transition_to_deactivate_or_return(corr=corr, success=False)
