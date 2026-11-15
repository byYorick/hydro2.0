"""GetZoneAutomationStateUseCase doses: explicit collaborators and invocation context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from ae3lite.application.services.zone_state_shared import _EC_CORRECTION_STEPS, _PH_CORRECTION_STEPS


@dataclass(frozen=True)
class ZoneStateDosesPorts:
    pass


class ZoneStateDoses:
    def __init__(self, ports: ZoneStateDosesPorts) -> None:
        self._ports = ports

    def build_active_processes(
        self,
        *,
        workflow_phase: str,
        is_active: bool,
        correction: Any | None,
    ) -> dict[str, Any]:
        corr_step = str(getattr(correction, "corr_step", "") or "").strip().lower()
        return {
            "pump_in": is_active and workflow_phase == "tank_filling",
            "circulation_pump": is_active and workflow_phase == "tank_recirc",
            "ph_correction": is_active and corr_step in _PH_CORRECTION_STEPS,
            "ec_correction": is_active and corr_step in _EC_CORRECTION_STEPS,
            "active_doses": self.build_active_doses(
                is_active=is_active,
                correction=correction,
                corr_step=corr_step,
            ),
        }

    def build_active_doses(
        self,
        *,
        is_active: bool,
        correction: Any | None,
        corr_step: str,
    ) -> list[dict[str, Any]]:
        """Live dosing pumps for UI — only during corr_dose_* (not wait steps)."""
        if not is_active or correction is None:
            return []
        if corr_step == "corr_dose_ec":
            return self.build_active_ec_doses(correction)
        if corr_step == "corr_dose_ph":
            return self.build_active_ph_doses(correction)
        return []

    def build_active_ec_doses(self, correction: Any) -> list[dict[str, Any]]:
        ec_component = str(getattr(correction, "ec_component", "") or "").strip().lower() or None
        sequence = self.parse_ec_dose_sequence(getattr(correction, "ec_dose_sequence_json", None))

        if ec_component == "multi_parallel" and sequence:
            doses: list[dict[str, Any]] = []
            for item in sequence:
                channel = str(item.get("channel") or "").strip()
                if not channel:
                    continue
                component = str(item.get("component") or "").strip().lower() or None
                doses.append(
                    self.dose_entry(
                        kind="ec",
                        channel=channel,
                        component=component,
                        node_uid=str(item.get("node_uid") or "").strip() or None,
                        amount_ml=item.get("amount_ml"),
                        duration_ms=item.get("duration_ms"),
                    )
                )
            return doses

        if sequence:
            try:
                idx = int(getattr(correction, "ec_current_seq_index", 0) or 0)
            except (TypeError, ValueError):
                idx = 0
            if 0 <= idx < len(sequence):
                item = sequence[idx]
                channel = str(item.get("channel") or "").strip()
                if channel:
                    component = str(item.get("component") or "").strip().lower() or None
                    return [
                        self.dose_entry(
                            kind="ec",
                            channel=channel,
                            component=component or ec_component,
                            node_uid=str(item.get("node_uid") or "").strip() or None,
                            amount_ml=item.get("amount_ml"),
                            duration_ms=item.get("duration_ms"),
                        )
                    ]

        channel = str(getattr(correction, "ec_channel", "") or "").strip()
        if not channel:
            return []
        return [
            self.dose_entry(
                kind="ec",
                channel=channel,
                component=ec_component if ec_component != "multi_parallel" else None,
                node_uid=str(getattr(correction, "ec_node_uid", "") or "").strip() or None,
                amount_ml=getattr(correction, "ec_amount_ml", None),
                duration_ms=getattr(correction, "ec_duration_ms", None),
            )
        ]

    def build_active_ph_doses(self, correction: Any) -> list[dict[str, Any]]:
        channel = str(getattr(correction, "ph_channel", "") or "").strip()
        if not channel:
            return []
        needs_ph_up = bool(getattr(correction, "needs_ph_up", False))
        kind = "ph_up" if needs_ph_up else "ph_down"
        return [
            self.dose_entry(
                kind=kind,
                channel=channel,
                component=None,
                node_uid=str(getattr(correction, "ph_node_uid", "") or "").strip() or None,
                amount_ml=getattr(correction, "ph_amount_ml", None),
                duration_ms=getattr(correction, "ph_duration_ms", None),
            )
        ]

    @staticmethod
    def parse_ec_dose_sequence(raw: Any) -> list[dict[str, Any]]:
        if raw is None:
            return []
        try:
            if isinstance(raw, str):
                parsed = json.loads(raw)
            else:
                parsed = raw
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if isinstance(parsed, Mapping):
            # Some paths wrap sequence under a key; prefer list payloads.
            for key in ("sequence", "doses", "items"):
                candidate = parsed.get(key)
                if isinstance(candidate, list):
                    parsed = candidate
                    break
            else:
                return []
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, Mapping)]

    @staticmethod
    def dose_entry(
        *,
        kind: str,
        channel: str,
        component: str | None,
        node_uid: str | None,
        amount_ml: Any,
        duration_ms: Any,
    ) -> dict[str, Any]:
        ml: float | None
        try:
            ml = float(amount_ml) if amount_ml is not None else None
        except (TypeError, ValueError):
            ml = None
        ms: int | None
        try:
            ms = int(duration_ms) if duration_ms is not None else None
        except (TypeError, ValueError):
            ms = None
        normalized_component: str | None
        if isinstance(component, str):
            normalized_component = component.strip().lower() or None
        else:
            normalized_component = None
        return {
            "kind": kind,
            "channel": str(channel).strip().lower(),
            "component": normalized_component,
            "node_uid": node_uid,
            "amount_ml": ml,
            "duration_ms": ms,
        }
