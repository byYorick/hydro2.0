"""CycleStartPlanner validation: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ae3lite.application.dto import ZoneSnapshot
from ae3lite.config.errors import ConfigValidationError
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError
from ae3lite.domain.services.cycle_planning_shared import _logger
from ae3lite.infrastructure.metrics import SHADOW_CONFIG_VALIDATION


@dataclass(frozen=True)
class CyclePlanningValidationPorts:
    correction_precheck_keys: Callable[[], Any]
    shadow_warning_window_sec: Callable[[], Any]
    monotonic_clock: Callable[[], Any]
    shadow_warning_last_logged_at: Callable[[], Any]
    global_load_zone_correction: Callable[..., Any]


class CyclePlanningValidation:
    def __init__(self, ports: CyclePlanningValidationPorts) -> None:
        self._ports = ports

    def shadow_validate_correction(
        self,
        *,
        snapshot: ZoneSnapshot,
        task: AutomationTask,
    ) -> None:
        """Non-blocking validation of snapshot.correction_config against
        canonical Pydantic schema (`schemas/zone_correction.v1.json`).

        Non-blocking — result is only reported to Prometheus counter
        `ae3_shadow_config_validation_total{result, namespace}` and logged
        at WARNING on failure. Runtime currently keeps this hook in shadow mode
        rather than failing task planning.
        """
        correction_config = getattr(snapshot, "correction_config", None)
        if not isinstance(correction_config, Mapping):
            SHADOW_CONFIG_VALIDATION.labels(
                result="invalid",
                namespace="zone.correction",
            ).inc()
            return
        # snapshot.correction_config is the compiler-merged `resolved_config`
        # (has keys `base`, `phases`, `meta`). Validate both the base and
        # each phase — all three should match the same schema after merge.
        targets: list[tuple[str, Any]] = []
        base = correction_config.get("base")
        if isinstance(base, Mapping):
            targets.append(("base", base))
        phases = correction_config.get("phases")
        if isinstance(phases, Mapping):
            for phase_name in ("solution_fill", "tank_recirc", "irrigation"):
                phase_cfg = phases.get(phase_name)
                if isinstance(phase_cfg, Mapping):
                    targets.append((f"phases.{phase_name}", phase_cfg))
        if not targets:
            SHADOW_CONFIG_VALIDATION.labels(
                result="invalid",
                namespace="zone.correction",
            ).inc()
            return

        zone_id = getattr(task, "zone_id", None)
        invalid_namespaces: list[str] = []
        invalid_violations: list[dict[str, Any]] = []
        for label, payload in targets:
            try:
                self._ports.global_load_zone_correction(
                    payload,
                    zone_id=zone_id,
                    namespace=f"zone.correction:{label}",
                )
            except ConfigValidationError as exc:
                invalid_namespaces.append(exc.namespace)
                if not invalid_violations:
                    invalid_violations = exc.errors[:20]
        if invalid_namespaces:
            self.log_shadow_validation_failure(
                zone_id=zone_id,
                invalid_namespaces=invalid_namespaces,
                violations=invalid_violations,
            )
        SHADOW_CONFIG_VALIDATION.labels(
            result="invalid" if invalid_namespaces else "ok",
            namespace="zone.correction",
        ).inc()

    def log_shadow_validation_failure(
        self,
        *,
        zone_id: object,
        invalid_namespaces: Sequence[str],
        violations: Sequence[dict[str, Any]],
    ) -> None:
        if not invalid_namespaces:
            return
        rate_limit_key = zone_id if zone_id is not None else "__unknown_zone__"
        now = self._ports.monotonic_clock()()
        last_logged_at = self._ports.shadow_warning_last_logged_at().get(rate_limit_key)
        if last_logged_at is not None and (now - last_logged_at) < self._ports.shadow_warning_window_sec():
            return

        self._ports.shadow_warning_last_logged_at()[rate_limit_key] = now
        _logger.warning(
            "ae3_shadow_config_validation_failed",
            extra={
                "zone_id": zone_id,
                "namespace": invalid_namespaces[0],
                "invalid_namespaces": tuple(invalid_namespaces[:5]),
                "invalid_count": len(invalid_namespaces),
                "violations": list(violations[:20]),
                "rate_limit_window_sec": int(self._ports.shadow_warning_window_sec()),
            },
        )

    def validate_required_correction_calibrations(self, *, runtime: Mapping[str, Any]) -> None:
        seen_pairs: set[tuple[str, str]] = set()
        correction_candidates = []

        correction = runtime.get("correction")
        if isinstance(correction, Mapping):
            correction_candidates.append(correction)

        correction_by_phase = runtime.get("correction_by_phase")
        if isinstance(correction_by_phase, Mapping):
            correction_candidates.extend(cfg for cfg in correction_by_phase.values() if isinstance(cfg, Mapping))

        for correction_cfg in correction_candidates:
            actuators = correction_cfg.get("actuators")
            if not isinstance(actuators, Mapping):
                continue
            for key in self._ports.correction_precheck_keys():
                actuator = actuators.get(key)
                self.validate_preflight_calibration(
                    actuator=actuator,
                    actuator_key=key,
                    seen_pairs=seen_pairs,
                )

    def validate_preflight_calibration(
        self,
        *,
        actuator: Any,
        actuator_key: str,
        seen_pairs: set[tuple[str, str]],
    ) -> None:
        if not isinstance(actuator, Mapping):
            return

        node_uid = str(actuator.get("node_uid") or "").strip()
        channel = str(actuator.get("channel") or "").strip()
        if node_uid == "" or channel == "":
            return

        pair = (node_uid, channel.lower())
        if pair in seen_pairs:
            return
        seen_pairs.add(pair)

        calibration = actuator.get("calibration")
        kind = "EC" if actuator_key.startswith("ec") else "PH"
        if not isinstance(calibration, Mapping):
            raise PlannerConfigurationError(
                f"Для насоса дозирования {kind} требуется calibration (channel={channel}, node={node_uid})",
                code=ErrorCodes.ZONE_DOSING_CALIBRATION_MISSING_CRITICAL,
            )

        # Audit F6: the old check only asserted calibration was *some* Mapping,
        # so an empty dict or one missing ``ml_per_sec`` passed preflight and
        # blew up later in ``_dose_ml_to_ms`` with a non-actionable error
        # during the first dose attempt. Fail-close at cycle_start with an
        # explicit list of missing keys so operators know exactly which field
        # to fix in pump_calibrations.
        required_keys = ("ml_per_sec",)
        missing = [key for key in required_keys if calibration.get(key) in (None, "", 0)]
        if missing:
            raise PlannerConfigurationError(
                f"Для насоса дозирования {kind} calibration не содержит обязательные поля "
                f"{missing} (channel={channel}, node={node_uid})",
                code=ErrorCodes.ZONE_DOSING_CALIBRATION_MISSING_CRITICAL,
            )
