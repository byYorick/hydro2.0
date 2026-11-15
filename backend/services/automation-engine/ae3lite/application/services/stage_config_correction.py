"""StageRuntimeConfig correction: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError


@dataclass(frozen=True)
class StageConfigCorrectionPorts:
    mapping_value: Callable[..., Any]
    mapping_view: Callable[..., Any]
    required_config_float: Callable[..., Any]
    runtime_phase_key: Callable[..., Any]


class StageConfigCorrection:
    def __init__(self, ports: StageConfigCorrectionPorts) -> None:
        self._ports = ports

    def required_prepare_tolerance_pct(
        self,
        *,
        tolerance: Mapping[str, Any],
        key: str,
    ) -> float:
        return self._ports.required_config_float(
            field_name=f"prepare_tolerance.{key}",
            candidates=((f"prepare_tolerance.{key}", self._ports.mapping_value(tolerance, key)),),
            minimum=0.1,
        )

    def prepare_tolerance_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        phase_key = self._ports.runtime_phase_key(task=task)
        phase_cfg = runtime.prepare_tolerance_by_phase.get(phase_key)
        if phase_cfg is not None:
            return self._ports.mapping_view(phase_cfg)
        generic_cfg = runtime.prepare_tolerance_by_phase.get("generic")
        if generic_cfg is not None:
            return self._ports.mapping_view(generic_cfg)
        if runtime.prepare_tolerance is not None:
            return self._ports.mapping_view(runtime.prepare_tolerance)
        raise TaskExecutionError(
            ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
            f"Отсутствует обязательный prepare_tolerance для phase={self._ports.runtime_phase_key(task=task)}",
        )

    def correction_config_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        phase_key = self._ports.runtime_phase_key(task=task)
        phase_cfg = runtime.correction_by_phase.get(phase_key)
        if phase_cfg is not None:
            return self._ports.mapping_view(phase_cfg)
        generic_cfg = runtime.correction_by_phase.get("generic")
        if generic_cfg is not None:
            return self._ports.mapping_view(generic_cfg)
        if runtime.correction is not None:
            return self._ports.mapping_view(runtime.correction)
        raise TaskExecutionError(
            ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
            f"Отсутствует обязательный correction runtime для phase={self._ports.runtime_phase_key(task=task)}",
        )

    def full_ec_component_ratios(
        self,
        *,
        runtime: RuntimePlan,
        correction_cfg: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Full recipe Ca/Mg/NPK/Micro ratios for cumulative T_* / dilute math.

        Prefer tank_recirc ratios over fill calcium-only and runtime fallback.
        """
        by_phase = getattr(runtime, "correction_by_phase", None) or {}
        tank_recirc = by_phase.get("tank_recirc") if isinstance(by_phase, Mapping) else None
        if tank_recirc is not None:
            ratios = getattr(tank_recirc, "ec_component_ratios", None)
            if isinstance(tank_recirc, Mapping):
                ratios = tank_recirc.get("ec_component_ratios")
            if isinstance(ratios, Mapping) and ratios:
                return ratios
            view = self._ports.mapping_view(tank_recirc)
            ratios = view.get("ec_component_ratios") if isinstance(view, Mapping) else None
            if isinstance(ratios, Mapping) and ratios:
                return ratios
        ratios = getattr(runtime, "ec_component_ratios", None) or {}
        if isinstance(ratios, Mapping) and ratios:
            return ratios
        if isinstance(correction_cfg, Mapping):
            ratios = correction_cfg.get("ec_component_ratios") or {}
            if isinstance(ratios, Mapping) and ratios:
                return ratios
        return {}

    def process_cfg_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        process_calibrations = runtime.process_calibrations
        phase_key = self._ports.runtime_phase_key(task=task)
        process_cfg = process_calibrations.get(phase_key)
        if process_cfg is not None:
            return self._ports.mapping_view(process_cfg)
        generic_cfg = process_calibrations.get("generic")
        if generic_cfg is not None:
            return self._ports.mapping_view(generic_cfg)
        if phase_key == "irrigation":
            solution_fill_cfg = process_calibrations.get("solution_fill")
            if solution_fill_cfg is not None:
                return self._ports.mapping_view(solution_fill_cfg)
        return {}
