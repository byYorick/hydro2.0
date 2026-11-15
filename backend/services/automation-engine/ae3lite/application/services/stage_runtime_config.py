"""Разрешение phase/targets/observe из RuntimePlan без SQL и команд.

Объект не кеширует runtime: каждый вызов получает актуальный plan после checkpoint.
"""

from __future__ import annotations
from functools import cached_property

import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError


from ae3lite.application.services.stage_config_shared import _MISSING_CONFIG

from ae3lite.application.services.stage_config_validation import StageConfigValidation, StageConfigValidationPorts
from ae3lite.application.services.stage_config_correction import StageConfigCorrection, StageConfigCorrectionPorts
from ae3lite.application.services.stage_config_observation import StageConfigObservation, StageConfigObservationPorts
from ae3lite.application.services.stage_config_targets import StageConfigTargets, StageConfigTargetsPorts
from ae3lite.application.services.stage_config_schedule import StageConfigSchedule, StageConfigSchedulePorts


class StageRuntimeConfig:
    """Приоритеты конфигурации, проверка обязательных полей и phase targets."""

    @cached_property
    def _stage_config_validation(self):
        return StageConfigValidation(StageConfigValidationPorts())

    @cached_property
    def _stage_config_correction(self):
        return StageConfigCorrection(
            StageConfigCorrectionPorts(
                mapping_value=lambda *args, **kwargs: self.mapping_value(*args, **kwargs),
                mapping_view=lambda *args, **kwargs: self.mapping_view(*args, **kwargs),
                required_config_float=lambda *args, **kwargs: self.required_config_float(*args, **kwargs),
                runtime_phase_key=lambda *args, **kwargs: self.runtime_phase_key(*args, **kwargs),
            )
        )

    @cached_property
    def _stage_config_observation(self):
        return StageConfigObservation(
            StageConfigObservationPorts(
                mapping_value=lambda *args, **kwargs: self.mapping_value(*args, **kwargs),
                required_config_float=lambda *args, **kwargs: self.required_config_float(*args, **kwargs),
                required_config_int=lambda *args, **kwargs: self.required_config_int(*args, **kwargs),
            )
        )

    @cached_property
    def _stage_config_targets(self):
        return StageConfigTargets(
            StageConfigTargetsPorts(
                coerce_float=lambda *args, **kwargs: self.coerce_float(*args, **kwargs),
                day_night_override=lambda *args, **kwargs: self.day_night_override(*args, **kwargs),
                day_night_override_scaled=lambda *args, **kwargs: self.day_night_override_scaled(*args, **kwargs),
                runtime_phase_key=lambda *args, **kwargs: self.runtime_phase_key(*args, **kwargs),
            )
        )

    @cached_property
    def _stage_config_schedule(self):
        return StageConfigSchedule(
            StageConfigSchedulePorts(
                is_day_now=lambda config: self.is_day_now(config),
                coerce_float=lambda *args, **kwargs: self.coerce_float(*args, **kwargs),
            )
        )

    mapping_value = staticmethod(StageConfigValidation.mapping_value)

    mapping_view = staticmethod(StageConfigValidation.mapping_view)

    def required_config_int(
        self,
        *,
        field_name: str,
        candidates: Sequence[tuple[str, Any]],
        minimum: int,
        error_code: str = ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
    ) -> int:
        return self._stage_config_validation.required_config_int(
            field_name=field_name, candidates=candidates, minimum=minimum, error_code=error_code
        )

    def required_config_float(
        self,
        *,
        field_name: str,
        candidates: Sequence[tuple[str, Any]],
        minimum: float,
        error_code: str = ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
    ) -> float:
        return self._stage_config_validation.required_config_float(
            field_name=field_name, candidates=candidates, minimum=minimum, error_code=error_code
        )

    def required_correction_int(
        self,
        *,
        correction_cfg: Mapping[str, Any],
        key: str,
        minimum: int = 1,
    ) -> int:
        return self._stage_config_validation.required_correction_int(
            correction_cfg=correction_cfg, key=key, minimum=minimum
        )

    def required_prepare_tolerance_pct(
        self,
        *,
        tolerance: Mapping[str, Any],
        key: str,
    ) -> float:
        return self._stage_config_correction.required_prepare_tolerance_pct(tolerance=tolerance, key=key)

    def prepare_tolerance_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        return self._stage_config_correction.prepare_tolerance_for_task(task=task, runtime=runtime)

    def correction_config_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        return self._stage_config_correction.correction_config_for_task(task=task, runtime=runtime)

    def full_ec_component_ratios(
        self,
        *,
        runtime: RuntimePlan,
        correction_cfg: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        return self._stage_config_correction.full_ec_component_ratios(runtime=runtime, correction_cfg=correction_cfg)

    def process_cfg_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        return self._stage_config_correction.process_cfg_for_task(task=task, runtime=runtime)

    def observation_config(
        self,
        *,
        kind: str,
        correction_cfg: Mapping[str, Any],
        process_cfg: Mapping[str, Any],
        pid_entry: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._stage_config_observation.observation_config(
            kind=kind, correction_cfg=correction_cfg, process_cfg=process_cfg, pid_entry=pid_entry
        )

    def adaptive_observation_timing(self, *, pid_entry: Mapping[str, Any] | None) -> dict[str, int]:
        return self._stage_config_observation.adaptive_observation_timing(pid_entry=pid_entry)

    def irrigation_ec_target(self, *, runtime: RuntimePlan) -> float:
        return self._stage_config_targets.irrigation_ec_target(runtime=runtime)

    def irrigation_ec_min(self, *, runtime: RuntimePlan) -> float | None:
        return self._stage_config_targets.irrigation_ec_min(runtime=runtime)

    def irrigation_ec_max(self, *, runtime: RuntimePlan) -> float | None:
        return self._stage_config_targets.irrigation_ec_max(runtime=runtime)

    def effective_ec_target(self, *, task: Any, runtime: RuntimePlan) -> float:
        return self._stage_config_targets.effective_ec_target(task=task, runtime=runtime)

    def effective_ec_min(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        return self._stage_config_targets.effective_ec_min(task=task, runtime=runtime)

    def effective_ec_max(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        return self._stage_config_targets.effective_ec_max(task=task, runtime=runtime)

    def effective_ph_target(self, *, task: Any, runtime: RuntimePlan) -> float:
        return self._stage_config_targets.effective_ph_target(task=task, runtime=runtime)

    def effective_ph_min(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        return self._stage_config_targets.effective_ph_min(task=task, runtime=runtime)

    def effective_ph_max(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        return self._stage_config_targets.effective_ph_max(task=task, runtime=runtime)

    def day_night_override(
        self,
        runtime: RuntimePlan,
        metric: str,
        kind: str,
        *,
        default: float,
    ) -> float:
        return self._stage_config_schedule.day_night_override(
            runtime=runtime, metric=metric, kind=kind, default=default
        )

    def day_night_override_scaled(
        self,
        runtime: RuntimePlan,
        metric: str,
        kind: str,
        *,
        default: float,
        phase_key: str,
    ) -> float | None:
        return self._stage_config_schedule.day_night_override_scaled(
            runtime=runtime, metric=metric, kind=kind, default=default, phase_key=phase_key
        )

    @staticmethod
    def is_day_now(day_night_config: Any) -> bool:
        return StageConfigSchedule.is_day_now(day_night_config, now_fn=lambda tz: datetime.now(tz))

    def runtime_phase_key(self, *, task: Any) -> str:
        return self._stage_config_schedule.runtime_phase_key(task=task)

    def coerce_float(self, value: Any) -> float | None:
        return self._stage_config_validation.coerce_float(value=value)
