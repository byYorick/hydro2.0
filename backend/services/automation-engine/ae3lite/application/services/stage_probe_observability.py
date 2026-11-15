"""Stage component: probe observability. Explicit ports; no handler dependency."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.infrastructure.metrics import (
    NODE_REBOOT_DETECTED,
)
from common.service_logs import send_service_log

_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageProbeObservabilityPorts:
    extract_irr_probe_node_uid: Callable[..., Any]
    runtime_monitor: Callable[[], Any]
    create_zone_event: Callable[..., Awaitable[Any]]


class StageProbeObservability:
    def __init__(self, ports: StageProbeObservabilityPorts) -> None:
        self._ports = ports

    @staticmethod
    def is_node_reboot_pattern(
        *,
        expected: Mapping[str, bool],
        snapshot: Mapping[str, Any],
    ) -> tuple[bool, list[str]]:
        """Эвристика: все ожидаемые truthy-поля стали ``False`` в snapshot.

        Это типичный паттерн boot defaults после перезагрузки ESP32 / firmware
        fail-safe (watchdog, brownout, сработавший firmware-side guard сбрасывает
        valves/pump в ``False``). Возвращает ``(is_reboot, diverged_keys)``.
        """
        truthy_expected = [k for k, v in expected.items() if bool(v)]
        if not truthy_expected:
            return False, []
        diverged = [k for k in truthy_expected if not bool(snapshot.get(k))]
        return len(diverged) == len(truthy_expected), diverged

    async def maybe_emit_node_reboot_event(
        self,
        *,
        task: Any,
        plan: Any,
        expected: Mapping[str, bool],
        snapshot: Mapping[str, Any],
    ) -> None:
        """Эмитит ``NODE_REBOOT_DETECTED`` zone-event при boot-defaults паттерне.

        НЕ подавляет последующий ``irr_state_mismatch`` fail-closed: это
        диагностический сигнал для post-mortem (operator/agronomist), а не
        замена safety boundary. Всегда вызывается перед ``raise``.
        """
        is_reboot, diverged_keys = self.is_node_reboot_pattern(
            expected=expected,
            snapshot=snapshot,
        )
        if not is_reboot:
            return
        node_uid = self._ports.extract_irr_probe_node_uid(plan=plan)
        liveness: Mapping[str, Any] = {}
        read_node_liveness = getattr(self._ports.runtime_monitor(), "read_node_liveness", None)
        if node_uid and callable(read_node_liveness):
            try:
                liveness = await read_node_liveness(node_uid=node_uid) or {}
            except Exception:
                _logger.warning(
                    "AE3 не смог прочитать node liveness для NODE_REBOOT_DETECTED node_uid=%s",
                    node_uid,
                    exc_info=True,
                )
        details = {
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
            "node_uid": node_uid,
            "expected": dict(expected),
            "snapshot": dict(snapshot) if isinstance(snapshot, Mapping) else {},
            "diverged_keys": list(diverged_keys),
            "detection_reason": "all_expected_truthy_diverged_to_false",
            "node_status": liveness.get("status") if isinstance(liveness, Mapping) else None,
            "heartbeat_age_sec": (liveness.get("heartbeat_age_sec") if isinstance(liveness, Mapping) else None),
            "last_seen_age_sec": (liveness.get("last_seen_age_sec") if isinstance(liveness, Mapping) else None),
            "irr_probe_failure_streak": int(getattr(task, "irr_probe_failure_streak", 0) or 0),
        }
        try:
            await self._ports.create_zone_event(
                int(task.zone_id),
                "NODE_REBOOT_DETECTED",
                with_runtime_event_contract(details),
            )
        except Exception:
            _logger.warning(
                "AE3 не смог записать NODE_REBOOT_DETECTED zone_id=%s task_id=%s node_uid=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                node_uid,
                exc_info=True,
            )
        NODE_REBOOT_DETECTED.labels(
            topology=str(getattr(task, "topology", "") or ""),
            stage=str(getattr(task, "current_stage", "") or ""),
            node_uid=str(node_uid or "unknown"),
        ).inc()
        try:
            send_service_log(
                service="automation-engine",
                level="warning",
                message="AE3 detected ESP32 reboot pattern during IRR state probe",
                context={
                    "zone_id": int(getattr(task, "zone_id", 0) or 0) or None,
                    "task_id": int(getattr(task, "id", 0) or 0) or None,
                    "node_uid": node_uid,
                    "stage": details["stage"],
                    "workflow_phase": details["workflow_phase"],
                    "diverged_keys": list(diverged_keys),
                    "node_status": details["node_status"],
                    "heartbeat_age_sec": details["heartbeat_age_sec"],
                    "irr_probe_failure_streak": details["irr_probe_failure_streak"],
                    "detection_reason": details["detection_reason"],
                },
            )
        except Exception:
            _logger.debug(
                "AE3 send_service_log failed для NODE_REBOOT_DETECTED zone_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                exc_info=True,
            )

    async def log_probe_failure_event(
        self,
        *,
        task: Any,
        expected: Mapping[str, bool],
        expected_cmd_id: str | None,
        state: Mapping[str, Any],
        reason: str,
    ) -> None:
        snapshot = state.get("snapshot") if isinstance(state.get("snapshot"), Mapping) else {}
        try:
            await self._ports.create_zone_event(
                int(task.zone_id),
                "IRR_STATE_PROBE_FAILED",
                with_runtime_event_contract(
                    {
                        "stage": str(getattr(task, "current_stage", "") or ""),
                        "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
                        "reason": str(reason or ""),
                        "expected": dict(expected),
                        "expected_cmd_id": expected_cmd_id,
                        "has_snapshot": bool(state.get("has_snapshot")),
                        "is_stale": bool(state.get("is_stale")),
                        "cmd_id": state.get("cmd_id"),
                        "snapshot": dict(snapshot) if isinstance(snapshot, Mapping) else {},
                    }
                ),
            )
        except Exception:
            _logger.warning(
                "AE3 не смог записать IRR_STATE_PROBE_FAILED zone_id=%s task_id=%s stage=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                str(getattr(task, "current_stage", "") or ""),
                exc_info=True,
            )
