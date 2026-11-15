"""StageRuntimeConfig targets: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ae3lite.config.schema import RuntimePlan


@dataclass(frozen=True)
class StageConfigTargetsPorts:
    coerce_float: Callable[..., Any]
    day_night_override: Callable[..., Any]
    day_night_override_scaled: Callable[..., Any]
    runtime_phase_key: Callable[..., Any]


class StageConfigTargets:
    def __init__(self, ports: StageConfigTargetsPorts) -> None:
        self._ports = ports

    def irrigation_ec_target(self, *, runtime: RuntimePlan) -> float:
        """Полный irrigation EC target (day/night), без NPK prepare-share."""
        base_full = float(runtime.target_ec)
        return self._ports.day_night_override(runtime, "ec", "target", default=base_full)

    def irrigation_ec_min(self, *, runtime: RuntimePlan) -> float | None:
        base_val = self._ports.coerce_float(runtime.target_ec_min)
        if base_val is None:
            return None
        return self._ports.day_night_override(runtime, "ec", "min", default=base_val)

    def irrigation_ec_max(self, *, runtime: RuntimePlan) -> float | None:
        base_val = self._ports.coerce_float(runtime.target_ec_max)
        if base_val is None:
            return None
        return self._ports.day_night_override(runtime, "ec", "max", default=base_val)

    def effective_ec_target(self, *, task: Any, runtime: RuntimePlan) -> float:
        """EC target с учётом фазы и water-baseline cumulative T_*.

        solution_fill / tank_recirc → T_step из corr.component_targets (если есть),
        иначе deprecated pre-baseline calcium share (target_ec_prepare).
        irrigation → full target; EC разрешается только выбранным
        irrigation_ec_component через pipeline dose flags.
        """
        from ae3lite.domain.services.nutrient_pipeline import (
            ComponentTargets,
            active_ec_target_for_corr,
        )

        phase = self._ports.runtime_phase_key(task=task)
        base_full = float(runtime.target_ec)
        full_target = self.irrigation_ec_target(runtime=runtime)
        corr = getattr(task, "correction", None)
        if corr is not None and phase in ("solution_fill", "tank_recirc"):
            targets = ComponentTargets.from_json(getattr(corr, "component_targets_json", None))
            if targets is not None:
                return active_ec_target_for_corr(
                    pipeline_phase=getattr(corr, "pipeline_phase", None),
                    active_component=getattr(corr, "active_component", None),
                    targets=targets,
                    fallback_target_ec=full_target,
                )
        if phase in ("solution_fill", "tank_recirc"):
            prepare = runtime.target_ec_prepare
            if prepare is not None:
                if full_target != base_full and base_full > 0:
                    share = float(runtime.npk_ec_share or (float(prepare) / base_full))
                    return round(full_target * share, 4)
                return float(prepare)
        return full_target

    def effective_ec_min(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        phase = self._ports.runtime_phase_key(task=task)
        if phase in ("solution_fill", "tank_recirc"):
            base = runtime.target_ec_prepare_min
            if base is not None:
                scaled = self._ports.day_night_override_scaled(
                    runtime,
                    "ec",
                    "min",
                    default=float(base),
                    phase_key="prepare",
                )
                return scaled if scaled is not None else float(base)
        return self.irrigation_ec_min(runtime=runtime)

    def effective_ec_max(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        phase = self._ports.runtime_phase_key(task=task)
        if phase in ("solution_fill", "tank_recirc"):
            base = runtime.target_ec_prepare_max
            if base is not None:
                scaled = self._ports.day_night_override_scaled(
                    runtime,
                    "ec",
                    "max",
                    default=float(base),
                    phase_key="prepare",
                )
                return scaled if scaled is not None else float(base)
        return self.irrigation_ec_max(runtime=runtime)

    def effective_ph_target(self, *, task: Any, runtime: RuntimePlan) -> float:
        base = float(runtime.target_ph)
        return self._ports.day_night_override(runtime, "ph", "target", default=base)

    def effective_ph_min(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        base_val = self._ports.coerce_float(runtime.target_ph_min)
        if base_val is None:
            return None
        return self._ports.day_night_override(runtime, "ph", "min", default=base_val)

    def effective_ph_max(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        base_val = self._ports.coerce_float(runtime.target_ph_max)
        if base_val is None:
            return None
        return self._ports.day_night_override(runtime, "ph", "max", default=base_val)
