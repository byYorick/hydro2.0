"""StageRuntimeConfig observation: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class StageConfigObservationPorts:
    mapping_value: Callable[..., Any]
    required_config_float: Callable[..., Any]
    required_config_int: Callable[..., Any]


class StageConfigObservation:
    def __init__(self, ports: StageConfigObservationPorts) -> None:
        self._ports = ports

    def observation_config(
        self,
        *,
        kind: str,
        correction_cfg: Mapping[str, Any],
        process_cfg: Mapping[str, Any],
        pid_entry: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        controllers_raw = self._ports.mapping_value(correction_cfg, "controllers")
        controllers = controllers_raw if isinstance(controllers_raw, Mapping) else {}
        controller_raw = controllers.get(kind)
        controller_cfg = controller_raw if isinstance(controller_raw, Mapping) else {}
        controller_observe_raw = self._ports.mapping_value(controller_cfg, "observe")
        controller_observe_cfg = controller_observe_raw if isinstance(controller_observe_raw, Mapping) else {}
        process_meta_raw = self._ports.mapping_value(process_cfg, "meta")
        process_meta = process_meta_raw if isinstance(process_meta_raw, Mapping) else {}
        observe_cfg = process_meta.get("observe") if isinstance(process_meta.get("observe"), Mapping) else {}

        telemetry_period_sec = self._ports.required_config_int(
            field_name=f"{kind}.observe.telemetry_period_sec",
            candidates=(
                (
                    "process_calibration.meta.observe.telemetry_period_sec",
                    self._ports.mapping_value(observe_cfg, "telemetry_period_sec"),
                ),
                (
                    f"correction.controllers.{kind}.observe.telemetry_period_sec",
                    self._ports.mapping_value(controller_observe_cfg, "telemetry_period_sec"),
                ),
                (
                    f"correction.controllers.{kind}.telemetry_period_sec",
                    self._ports.mapping_value(controller_cfg, "telemetry_period_sec"),
                ),
            ),
            minimum=1,
        )
        window_min_samples = self._ports.required_config_int(
            field_name=f"{kind}.observe.window_min_samples",
            candidates=(
                (
                    "process_calibration.meta.observe.window_min_samples",
                    self._ports.mapping_value(observe_cfg, "window_min_samples"),
                ),
                (
                    f"correction.controllers.{kind}.observe.window_min_samples",
                    self._ports.mapping_value(controller_observe_cfg, "window_min_samples"),
                ),
                (
                    f"correction.controllers.{kind}.window_min_samples",
                    self._ports.mapping_value(controller_cfg, "window_min_samples"),
                ),
            ),
            minimum=2,  # config-literal: decision window needs at least two samples
        )
        explicit_decision_window_sec = self._ports.required_config_int(
            field_name=f"{kind}.observe.decision_window_sec",
            candidates=(
                (
                    "process_calibration.meta.observe.decision_window_sec",
                    self._ports.mapping_value(observe_cfg, "decision_window_sec"),
                ),
                (
                    f"correction.controllers.{kind}.observe.decision_window_sec",
                    self._ports.mapping_value(controller_observe_cfg, "decision_window_sec"),
                ),
                (
                    f"correction.controllers.{kind}.decision_window_sec",
                    self._ports.mapping_value(controller_cfg, "decision_window_sec"),
                ),
            ),
            minimum=1,
        )
        decision_window_sec = max(
            telemetry_period_sec * window_min_samples,
            explicit_decision_window_sec,
        )
        transport_delay_sec = self._ports.required_config_int(
            field_name=f"{kind}.process_calibration.transport_delay_sec",
            candidates=(
                (
                    "process_calibration.transport_delay_sec",
                    self._ports.mapping_value(process_cfg, "transport_delay_sec"),
                ),
                (
                    f"correction.controllers.{kind}.observe.transport_delay_sec",
                    self._ports.mapping_value(controller_observe_cfg, "transport_delay_sec"),
                ),
                (
                    f"correction.controllers.{kind}.transport_delay_sec",
                    self._ports.mapping_value(controller_cfg, "transport_delay_sec"),
                ),
            ),
            minimum=1,
            error_code="corr_process_calibration_missing",
        )
        settle_sec = self._ports.required_config_int(
            field_name=f"{kind}.process_calibration.settle_sec",
            candidates=(
                ("process_calibration.settle_sec", self._ports.mapping_value(process_cfg, "settle_sec")),
                (
                    f"correction.controllers.{kind}.observe.settle_sec",
                    self._ports.mapping_value(controller_observe_cfg, "settle_sec"),
                ),
                (f"correction.controllers.{kind}.settle_sec", self._ports.mapping_value(controller_cfg, "settle_sec")),
            ),
            minimum=1,
            error_code="corr_process_calibration_missing",
        )

        adaptive_timing = self.adaptive_observation_timing(pid_entry=pid_entry)
        learned_transport = adaptive_timing.get("transport_delay_sec")
        learned_settle = adaptive_timing.get("settle_sec")
        if learned_transport is not None:
            transport_delay_sec = max(transport_delay_sec, learned_transport)
        if learned_settle is not None:
            settle_sec = max(settle_sec, learned_settle)
        return {
            "transport_delay_sec": transport_delay_sec,
            "settle_sec": settle_sec,
            "hold_window_sec": transport_delay_sec + settle_sec,
            "telemetry_period_sec": telemetry_period_sec,
            "window_min_samples": window_min_samples,
            "decision_window_sec": decision_window_sec,
            "observe_poll_sec": self._ports.required_config_int(
                field_name=f"{kind}.observe.observe_poll_sec",
                candidates=(
                    (
                        "process_calibration.meta.observe.observe_poll_sec",
                        self._ports.mapping_value(observe_cfg, "observe_poll_sec"),
                    ),
                    (
                        f"correction.controllers.{kind}.observe.observe_poll_sec",
                        self._ports.mapping_value(controller_observe_cfg, "observe_poll_sec"),
                    ),
                    (
                        f"correction.controllers.{kind}.observe_poll_sec",
                        self._ports.mapping_value(controller_cfg, "observe_poll_sec"),
                    ),
                ),
                minimum=1,
            ),
            "min_effect_fraction": self._ports.required_config_float(
                field_name=f"{kind}.observe.min_effect_fraction",
                candidates=(
                    (
                        "process_calibration.meta.observe.min_effect_fraction",
                        self._ports.mapping_value(observe_cfg, "min_effect_fraction"),
                    ),
                    (
                        f"correction.controllers.{kind}.observe.min_effect_fraction",
                        self._ports.mapping_value(controller_observe_cfg, "min_effect_fraction"),
                    ),
                    (
                        f"correction.controllers.{kind}.min_effect_fraction",
                        self._ports.mapping_value(controller_cfg, "min_effect_fraction"),
                    ),
                ),
                minimum=0.01,
            ),
            "stability_max_slope": self._ports.required_config_float(
                field_name=f"{kind}.observe.stability_max_slope",
                candidates=(
                    (
                        "process_calibration.meta.observe.stability_max_slope",
                        self._ports.mapping_value(observe_cfg, "stability_max_slope"),
                    ),
                    (
                        f"correction.controllers.{kind}.observe.stability_max_slope",
                        self._ports.mapping_value(controller_observe_cfg, "stability_max_slope"),
                    ),
                    (
                        f"correction.controllers.{kind}.stability_max_slope",
                        self._ports.mapping_value(controller_cfg, "stability_max_slope"),
                    ),
                ),
                minimum=0.0001,
            ),
            "no_effect_limit": self._ports.required_config_int(
                field_name=f"{kind}.observe.no_effect_consecutive_limit",
                candidates=(
                    (
                        "process_calibration.meta.observe.no_effect_consecutive_limit",
                        self._ports.mapping_value(observe_cfg, "no_effect_consecutive_limit"),
                    ),
                    (
                        f"correction.controllers.{kind}.observe.no_effect_consecutive_limit",
                        self._ports.mapping_value(controller_observe_cfg, "no_effect_consecutive_limit"),
                    ),
                    (
                        f"correction.controllers.{kind}.no_effect_consecutive_limit",
                        self._ports.mapping_value(controller_cfg, "no_effect_consecutive_limit"),
                    ),
                ),
                minimum=1,
            ),
        }

    def adaptive_observation_timing(self, *, pid_entry: Mapping[str, Any] | None) -> dict[str, int]:
        if not isinstance(pid_entry, Mapping):
            return {}
        stats = pid_entry.get("stats")
        if not isinstance(stats, Mapping):
            return {}
        adaptive = stats.get("adaptive")
        if not isinstance(adaptive, Mapping):
            return {}
        timing = adaptive.get("timing")
        if not isinstance(timing, Mapping):
            return {}
        try:
            observations = int(timing.get("observations") or adaptive.get("observations") or 0)
        except (TypeError, ValueError):
            observations = 0
        if observations < 3:
            return {}

        result: dict[str, int] = {}
        for key in ("transport_delay_sec", "settle_sec"):
            raw = timing.get(f"{key}_ema")
            try:
                value = int(round(float(raw)))
            except (TypeError, ValueError):
                continue
            if value > 0:
                result[key] = value
        return result
