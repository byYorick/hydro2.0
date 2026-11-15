"""Correction runtime context: explicit collaborators, per-call task context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ae3lite.application.services.correction_shared import _pid_entry_or_none
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError


@dataclass(frozen=True)
class CorrectionRuntimeContextPorts:
    require_runtime_plan: Callable[[], Any]
    runtime_config: Callable[[], Any]


class CorrectionRuntimeContext:
    def __init__(self, ports: CorrectionRuntimeContextPorts) -> None:
        self._ports = ports

    def correction_config(self, *, plan: Any, task: Any) -> Mapping[str, Any]:
        runtime = self._ports.require_runtime_plan()(plan=plan)
        return self._ports.runtime_config().correction_config_for_task(task=task, runtime=runtime)

    def resolve_actuators(self, *, runtime: Mapping[str, Any], task: Any, plan: Any) -> dict:
        corr = self.correction_config(plan=plan, task=task)
        actuators_raw = self._ports.runtime_config().mapping_value(corr, "actuators")
        actuators = actuators_raw if isinstance(actuators_raw, Mapping) else {}
        return {
            "ec": actuators.get("ec"),
            "ec_actuators": actuators.get("ec_actuators"),
            "ph_up": actuators.get("ph_up"),
            "ph_down": actuators.get("ph_down"),
        }

    def dose_accounting_context(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        pid_type: str,
    ) -> Mapping[str, Any]:
        """Persist hold policy with the command before the physical effect.

        Only cmd/params are sent to HL; this local metadata survives a crash
        after DONE even when the task correction fields are already cleared.
        """
        runtime = self._ports.require_runtime_plan()(plan=plan)
        observe = self._ports.runtime_config().observation_config(
            kind=pid_type,
            correction_cfg=self.correction_config(plan=plan, task=task),
            process_cfg=self._ports.runtime_config().process_cfg_for_task(task=task, runtime=runtime),
            pid_entry=_pid_entry_or_none(runtime.pid_state, pid_type),
        )
        return {
            "pid_type": pid_type,
            "last_correction_kind": ("ec" if pid_type == "ec" else "ph_up" if corr.needs_ph_up else "ph_down"),
            "hold_sec": int(observe["hold_window_sec"]),
        }

    def correction_retry_delay_sec(
        self,
        *,
        correction_cfg: Any,
        key: str,
    ) -> float:
        """Phase 3.1 / B-5e: returns a typed retry-delay from correction config.

        `correction_cfg` is either a `CorrectionPhaseRuntime` Pydantic model
        or a legacy dict fixture. The value is guaranteed positive int by the
        schema (`Annotated[int, Field(ge=1, le=3600)]`).

        Hardcoded `default` parameter removed (was 30.0/60.0) — Pydantic
        enforces presence; missing field is a fail-closed config bug.
        """
        raw_value = self._ports.runtime_config().mapping_value(correction_cfg, key)
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise PlannerConfigurationError(
                f"correction_cfg.{key} отсутствует или некорректно; поле обязательно по схеме",
                code=ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
            ) from exc
        if value <= 0:
            raise PlannerConfigurationError(
                f"correction_cfg.{key}={value!r} должно быть > 0",
                code=ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
            )
        return value
