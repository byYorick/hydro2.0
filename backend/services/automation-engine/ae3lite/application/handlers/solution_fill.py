"""SolutionFillCheckHandler: in-flow correction во время заполнения бака раствора."""

from __future__ import annotations
from functools import cached_property

import logging
from dataclasses import replace
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import STAGE_DEADLINE_EXCEEDED
from ae3lite.hydraulics.failure_report import note_upward_report


from ae3lite.application.services.solution_fill_completion import SolutionFillCompletionPorts, SolutionFillCompletion
from ae3lite.application.services.solution_fill_coordination import (
    SolutionFillCoordinationPorts,
    SolutionFillCoordination,
)
from ae3lite.application.services.solution_fill_correction import SolutionFillCorrectionPorts, SolutionFillCorrection
from ae3lite.application.services.solution_fill_ec_baseline import SolutionFillEcBaselinePorts, SolutionFillEcBaseline
from ae3lite.application.services.solution_fill_shared import _logger


class SolutionFillCheckHandler(BaseStageHandler):
    """Обрабатывает ``solution_fill_check``: окно заполнения и in-flow correction.

    Исходы:
    1. Бак полон и target'ы достигнуты → ``solution_fill_stop_to_ready``
    2. Бак полон, но target'ы не достигнуты → ``solution_fill_stop_to_prepare``
    3. Бак ещё заполняется и target'ы не достигнуты → коррекция внутри ``solution_fill_check``
    4. Бак ещё заполняется и target'ы достигнуты → ``poll``
    5. Дедлайн превышен → ``solution_fill_timeout_stop``
    """

    @cached_property
    def _solution_fill_coordination(self):
        return SolutionFillCoordination(
            SolutionFillCoordinationPorts(
                stale_recheck_delay_sec=lambda: self._STALE_RECHECK_DELAY_SEC,
                checkpoint=lambda: self._checkpoint,
                completed_outcome=lambda *args, **kwargs: self._completed_outcome(*args, **kwargs),
                deadline_reached=lambda: self._deadline_reached,
                enter_fill_calcium_correction=lambda *args, **kwargs: self._enter_fill_calcium_correction(
                    *args, **kwargs
                ),
                fill_ec_target_reached=lambda *args, **kwargs: self._fill_ec_target_reached(*args, **kwargs),
                handle_control_mode_flow_path_interrupt=lambda: self._handle_control_mode_flow_path_interrupt,
                observe_fail_safe_transition=lambda: self._observe_fail_safe_transition,
                probe_irr_state=lambda: self._probe_irr_state,
                read_level=lambda: self._read_level,
                read_recent_storage_event=lambda: self._read_recent_storage_event,
                reconcile_recent_emergency_stop=lambda: self._reconcile_recent_emergency_stop,
                require_runtime_plan=lambda: self._require_runtime_plan,
                should_finish_to_ready=lambda *args, **kwargs: self._should_finish_to_ready(*args, **kwargs),
                stage_elapsed_ms=lambda: self._stage_elapsed_ms,
                global_stage_deadline_exceeded=lambda: STAGE_DEADLINE_EXCEEDED,
                global_logger=lambda: _logger,
            )
        )

    @cached_property
    def _solution_fill_completion(self):
        return SolutionFillCompletion(
            SolutionFillCompletionPorts(
                stale_recheck_delay_sec=lambda: self._STALE_RECHECK_DELAY_SEC,
                check_sensor_consistency=lambda: self._check_sensor_consistency,
                finish_ready_or_irrigation_short_circuit=lambda: self._finish_ready_or_irrigation_short_circuit,
                read_level=lambda: self._read_level,
                global_logger=lambda: _logger,
            )
        )

    @cached_property
    def _solution_fill_correction(self):
        return SolutionFillCorrection(
            SolutionFillCorrectionPorts(
                load_existing_fill_baseline=lambda *args, **kwargs: self._load_existing_fill_baseline(*args, **kwargs),
                probe_snapshot_correction_fields=lambda: self._probe_snapshot_correction_fields,
                read_target_metric_window=lambda: self._read_target_metric_window,
                runtime_config=lambda: self._runtime_config,
                global_logger=lambda: _logger,
            )
        )

    @cached_property
    def _solution_fill_ec_baseline(self):
        return SolutionFillEcBaseline(
            SolutionFillEcBaselinePorts(
                load_existing_fill_baseline=lambda *args, **kwargs: self._load_existing_fill_baseline(*args, **kwargs),
                read_target_metric_window=lambda: self._read_target_metric_window,
                require_runtime_plan=lambda: self._require_runtime_plan,
                runtime_config=lambda: self._runtime_config,
                global_logger=lambda: _logger,
            )
        )

    _STALE_RECHECK_DELAY_SEC = 0.25

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        return await self._solution_fill_coordination.run(task=task, plan=plan, stage_def=stage_def, now=now)

    async def _should_finish_to_ready(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        return await self._solution_fill_completion.should_finish_to_ready(
            task=task, plan=plan, now=now, runtime=runtime
        )

    async def _completed_outcome(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> StageOutcome:
        return await self._solution_fill_completion.completed_outcome(task=task, plan=plan, now=now, runtime=runtime)

    def _build_correction_state(
        self,
        *,
        task: Any,
        runtime: Any,
        sensors_already_active: bool,
        return_stage_success: str,
        return_stage_fail: str,
    ) -> CorrectionState:
        return self._solution_fill_correction.build_correction_state(
            task=task,
            runtime=runtime,
            sensors_already_active=sensors_already_active,
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
        )

    async def _fill_ec_target_reached(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        return await self._solution_fill_ec_baseline.fill_ec_target_reached(
            task=task, plan=plan, now=now, runtime=runtime
        )

    async def _resolve_fill_ec_target(self, *, task: Any, runtime: Any) -> float:
        return await self._solution_fill_ec_baseline.resolve_fill_ec_target(task=task, runtime=runtime)

    _corr_has_fill_baseline = staticmethod(SolutionFillEcBaseline.corr_has_fill_baseline)

    async def _load_existing_fill_baseline(
        self,
        *,
        task: Any,
    ) -> tuple[Any, int | None] | None:
        return await self._solution_fill_ec_baseline.load_existing_fill_baseline(task=task)

    async def _enter_fill_calcium_correction(
        self,
        *,
        task: Any,
        plan: Any,
        runtime: Any,
        now: datetime,
        return_stage_success: str,
        return_stage_fail: str,
    ) -> CorrectionState:
        return await self._solution_fill_correction.enter_fill_calcium_correction(
            task=task,
            plan=plan,
            runtime=runtime,
            now=now,
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
        )
