"""Handler runtime-проверок во время полива."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler, _utc_naive_dt
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.domain.services.irrigation_actuation import (
    irrigation_start_uses_set_relay_pump,
    irrigation_start_uses_timed_run_pump,
)
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import (
    IRRIGATION_CORRECTION_ENTERED,
    IRRIGATION_DURATION,
    IRRIGATION_REPLAY,
    IRRIGATION_SOLUTION_MIN,
)
from ae3lite.hydraulics.failure_report import note_upward_report
from common.db import create_zone_event


# Sanity clamp for requested irrigation duration (protects against corrupt read-model).


from ae3lite.application.services.irrigation_check_coordination import (
    IrrigationCheckCoordinationPorts,
    IrrigationCheckCoordination,
)
from ae3lite.application.services.irrigation_check_expected_state import (
    IrrigationCheckExpectedStatePorts,
    IrrigationCheckExpectedState,
)
from ae3lite.application.services.irrigation_check_nutrient_baseline import (
    IrrigationCheckNutrientBaselinePorts,
    IrrigationCheckNutrientBaseline,
)
from ae3lite.application.services.irrigation_check_shared import _logger, _IRRIGATION_DURATION_MAX_SEC
from ae3lite.application.services.irrigation_check_solution_safety import (
    IrrigationCheckSolutionSafetyPorts,
    IrrigationCheckSolutionSafety,
)
from ae3lite.application.services.irrigation_check_timing import IrrigationCheckTimingPorts, IrrigationCheckTiming


class IrrigationCheckHandler(BaseStageHandler):
    _STALE_RECHECK_DELAY_SEC = 0.25

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        command_gateway: Any,
        task_repository: Any,
        live_reload_enabled: bool = False,
    ) -> None:
        super().__init__(
            runtime_monitor=runtime_monitor,
            command_gateway=command_gateway,
            live_reload_enabled=live_reload_enabled,
        )
        self._task_repository = task_repository
        self._irrigation_check_coordination = IrrigationCheckCoordination(
            IrrigationCheckCoordinationPorts(
                stale_recheck_delay_sec=lambda: self._STALE_RECHECK_DELAY_SEC,
                checkpoint=lambda: self._checkpoint,
                deadline_reached=lambda: self._deadline_reached,
                handle_control_mode_flow_path_interrupt=lambda: self._handle_control_mode_flow_path_interrupt,
                load_irrigation_nutrient_baseline=lambda *args, **kwargs: self._load_irrigation_nutrient_baseline(
                    *args, **kwargs
                ),
                maybe_stop_continuous_pump_after_duration=lambda *args, **kwargs: (
                    self._maybe_stop_continuous_pump_after_duration(*args, **kwargs)
                ),
                probe_irr_state=lambda: self._probe_irr_state,
                probe_irr_state_with_backoff=lambda: self._probe_irr_state_with_backoff,
                probe_snapshot_context=lambda: self._probe_snapshot_context,
                probe_snapshot_correction_fields=lambda: self._probe_snapshot_correction_fields,
                read_level=lambda: self._read_level,
                read_recent_storage_event=lambda: self._read_recent_storage_event,
                recent_solution_low_event_confirms_active_low=lambda *args, **kwargs: (
                    self._recent_solution_low_event_confirms_active_low(*args, **kwargs)
                ),
                reconcile_recent_emergency_stop=lambda: self._reconcile_recent_emergency_stop,
                record_deadline_target_outcome=lambda: self._record_deadline_target_outcome,
                require_runtime_plan=lambda: self._require_runtime_plan,
                resolve_expected_irrigation_state=lambda *args, **kwargs: self._resolve_expected_irrigation_state(
                    *args, **kwargs
                ),
                runtime_config=lambda: self._runtime_config,
                solution_min_low_outcome=lambda *args, **kwargs: self._solution_min_low_outcome(*args, **kwargs),
                target_outcome_on_deadline=lambda: self._target_outcome_on_deadline,
                targets_reached=lambda: self._targets_reached,
                global_irrigation_correction_entered=lambda: IRRIGATION_CORRECTION_ENTERED,
                global_irrigation_duration=lambda: IRRIGATION_DURATION,
                global_logger=lambda: _logger,
                global_create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            )
        )
        self._irrigation_check_nutrient_baseline = IrrigationCheckNutrientBaseline(
            IrrigationCheckNutrientBaselinePorts(
                global_logger=lambda: _logger,
            )
        )
        self._irrigation_check_solution_safety = IrrigationCheckSolutionSafety(
            IrrigationCheckSolutionSafetyPorts(
                observe_fail_safe_transition=lambda: self._observe_fail_safe_transition,
                storage_event_payload=lambda: self._storage_event_payload,
                task_repository=lambda: self._task_repository,
                global_irrigation_replay=lambda: IRRIGATION_REPLAY,
                global_irrigation_solution_min=lambda: IRRIGATION_SOLUTION_MIN,
                global_logger=lambda: _logger,
                global_create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            )
        )
        self._irrigation_check_timing = IrrigationCheckTiming(
            IrrigationCheckTimingPorts(
                runtime_monitor=lambda: self._runtime_monitor,
                global_logger=lambda: _logger,
            )
        )
        self._irrigation_check_expected_state = IrrigationCheckExpectedState(
            IrrigationCheckExpectedStatePorts(
                resolve_irrigation_duration_sec=lambda *args, **kwargs: self._resolve_irrigation_duration_sec(
                    *args, **kwargs
                ),
                resolve_irrigation_pump_stop_at=lambda *args, **kwargs: self._resolve_irrigation_pump_stop_at(
                    *args, **kwargs
                ),
            )
        )

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        return await self._irrigation_check_coordination.run(task=task, plan=plan, stage_def=stage_def, now=now)

    async def _load_irrigation_nutrient_baseline(
        self,
        *,
        task: Any,
    ) -> tuple[str | None, int | None, float | None, float | None, float | None]:
        return await self._irrigation_check_nutrient_baseline.load_irrigation_nutrient_baseline(task=task)

    def _recent_solution_low_event_confirms_active_low(
        self,
        *,
        event: Mapping[str, Any] | None,
        expected: Mapping[str, bool],
    ) -> bool:
        return self._irrigation_check_solution_safety.recent_solution_low_event_confirms_active_low(
            event=event, expected=expected
        )

    def _event_bool(
        self,
        mapping: Mapping[str, Any] | None,
        keys: tuple[str, ...],
    ) -> bool | None:
        return self._irrigation_check_solution_safety.event_bool(mapping=mapping, keys=keys)

    async def _solution_min_low_outcome(
        self,
        *,
        task: Any,
        topology: str,
        recovery: dict[str, Any],
        now: datetime,
        observe_duration: Any,
        source: str,
    ) -> StageOutcome:
        return await self._irrigation_check_solution_safety.solution_min_low_outcome(
            task=task, topology=topology, recovery=recovery, now=now, observe_duration=observe_duration, source=source
        )

    def _resolve_irrigation_duration_sec(self, *, task: Any, runtime: Any) -> int:
        return self._irrigation_check_timing.resolve_irrigation_duration_sec(task=task, runtime=runtime)

    def _resolve_irrigation_pump_stop_at(
        self,
        *,
        task: Any,
        runtime: Any,
        plan: Any,
        requested_sec: int,
    ) -> datetime | None:
        return self._irrigation_check_timing.resolve_irrigation_pump_stop_at(
            task=task, runtime=runtime, plan=plan, requested_sec=requested_sec
        )

    def _resolve_expected_irrigation_state(
        self,
        *,
        task: Any,
        plan: Any,
        runtime: Any,
        now: datetime,
    ) -> dict[str, bool]:
        return self._irrigation_check_expected_state.resolve_expected_irrigation_state(
            task=task, plan=plan, runtime=runtime, now=now
        )

    async def _maybe_stop_continuous_pump_after_duration(
        self,
        *,
        task: Any,
        plan: Any,
        runtime: Any,
        now: datetime,
        observe_duration: Any,
    ) -> StageOutcome | None:
        return await self._irrigation_check_timing.maybe_stop_continuous_pump_after_duration(
            task=task, plan=plan, runtime=runtime, now=now, observe_duration=observe_duration
        )
