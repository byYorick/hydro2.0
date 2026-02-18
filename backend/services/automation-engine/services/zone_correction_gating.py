"""Correction gating helpers extracted from ZoneAutomationService."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Set


def normalize_optional_bool(raw: Any) -> Optional[bool]:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        if raw == 1:
            return True
        if raw == 0:
            return False
        return None
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def parse_optional_timestamp(raw: Any) -> Optional[datetime]:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str) and raw.strip():
        normalized = raw.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def collect_stale_correction_flags(
    *,
    normalized_flags: Dict[str, Any],
    now: datetime,
    required_flag_names: Sequence[str],
    max_age_seconds: int,
    require_timestamps: Optional[bool] = None,
    default_require_timestamps: bool,
) -> List[str]:
    require_ts = default_require_timestamps if require_timestamps is None else bool(require_timestamps)
    stale_flags: List[str] = []
    for flag_name in required_flag_names:
        raw_ts = normalized_flags.get(f"{flag_name}_ts")
        parsed_ts = parse_optional_timestamp(raw_ts)
        if parsed_ts is None:
            if require_ts:
                stale_flags.append(flag_name)
            continue
        if parsed_ts.tzinfo is None:
            parsed_ts = parsed_ts.replace(tzinfo=now.tzinfo)
        age_seconds = (now - parsed_ts).total_seconds()
        if age_seconds > max_age_seconds:
            stale_flags.append(flag_name)
    return stale_flags


def collect_correction_flag_ages_seconds(
    *,
    normalized_flags: Dict[str, Any],
    now: datetime,
    required_flag_names: Sequence[str],
) -> Dict[str, float]:
    ages: Dict[str, float] = {}
    for flag_name in required_flag_names:
        parsed_ts = parse_optional_timestamp(normalized_flags.get(f"{flag_name}_ts"))
        if parsed_ts is None:
            continue
        if parsed_ts.tzinfo is None:
            parsed_ts = parsed_ts.replace(tzinfo=now.tzinfo)
        age_seconds = max(0.0, (now - parsed_ts).total_seconds())
        ages[flag_name] = round(age_seconds, 3)
    return ages


def collect_correction_flag_timestamp_diagnostics(
    *,
    normalized_flags: Dict[str, Any],
    now: datetime,
    required_flag_names: Sequence[str],
    max_age_seconds: int,
) -> Dict[str, Dict[str, Any]]:
    diagnostics: Dict[str, Dict[str, Any]] = {}
    for flag_name in required_flag_names:
        raw_ts = normalized_flags.get(f"{flag_name}_ts")
        has_timestamp = not (raw_ts is None or (isinstance(raw_ts, str) and not raw_ts.strip()))
        parsed_ts = parse_optional_timestamp(raw_ts)
        invalid_timestamp = bool(has_timestamp and parsed_ts is None)
        age_seconds: Optional[float] = None
        if parsed_ts is not None:
            if parsed_ts.tzinfo is None:
                parsed_ts = parsed_ts.replace(tzinfo=now.tzinfo)
            age_seconds = round(max(0.0, (now - parsed_ts).total_seconds()), 3)
        diagnostics[flag_name] = {
            "has_timestamp": has_timestamp,
            "invalid_timestamp": invalid_timestamp,
            "age_seconds": age_seconds,
            "max_age_seconds": max_age_seconds,
        }
    return diagnostics


def build_stale_flag_reasons(
    *,
    stale_flags: List[str],
    timestamp_diagnostics: Dict[str, Dict[str, Any]],
    require_timestamps: bool,
) -> Dict[str, Dict[str, Any]]:
    reasons: Dict[str, Dict[str, Any]] = {}
    for flag_name in stale_flags:
        diag = timestamp_diagnostics.get(flag_name) if isinstance(timestamp_diagnostics, dict) else {}
        if not isinstance(diag, dict):
            diag = {}

        has_ts = bool(diag.get("has_timestamp"))
        invalid_ts = bool(diag.get("invalid_timestamp"))
        age_seconds = diag.get("age_seconds")
        max_age_seconds = diag.get("max_age_seconds")

        reason = "stale_by_age"
        if invalid_ts:
            reason = "invalid_timestamp"
        elif require_timestamps and not has_ts:
            reason = "missing_timestamp"

        reasons[flag_name] = {
            "reason": reason,
            "has_timestamp": has_ts,
            "invalid_timestamp": invalid_ts,
            "age_seconds": age_seconds,
            "max_age_seconds": max_age_seconds,
        }
    return reasons


def build_correction_gating_state(
    *,
    telemetry: Dict[str, Optional[float]],
    telemetry_timestamps: Dict[str, Any],
    correction_flags: Dict[str, Any],
    workflow_phase: str,
    normalize_workflow_phase_fn: Callable[[Any], str],
    utcnow_fn: Callable[[], datetime],
    correction_open_phases: Set[str],
    required_flag_names: Sequence[str],
    flags_max_age_seconds: int,
    flags_require_timestamps: bool,
    logger: Any,
) -> Dict[str, Any]:
    normalized_workflow_phase = normalize_workflow_phase_fn(workflow_phase)
    workflow_phase_open = normalized_workflow_phase in correction_open_phases
    flags = correction_flags if isinstance(correction_flags, dict) else {}
    flow_active_raw = flags.get("flow_active", telemetry.get("FLOW_ACTIVE"))
    stable_raw = flags.get("stable", telemetry.get("STABLE"))
    corrections_allowed_raw = flags.get("corrections_allowed", telemetry.get("CORRECTIONS_ALLOWED"))
    flow_active = normalize_optional_bool(flow_active_raw)
    stable = normalize_optional_bool(stable_raw)
    corrections_allowed = normalize_optional_bool(corrections_allowed_raw)
    normalized_flags = {
        "flow_active": flow_active,
        "stable": stable,
        "corrections_allowed": corrections_allowed,
        "flow_active_ts": flags.get("flow_active_ts", telemetry_timestamps.get("FLOW_ACTIVE")),
        "stable_ts": flags.get("stable_ts", telemetry_timestamps.get("STABLE")),
        "corrections_allowed_ts": flags.get("corrections_allowed_ts", telemetry_timestamps.get("CORRECTIONS_ALLOWED")),
    }
    now = utcnow_fn()
    require_timestamps = bool(flags_require_timestamps)

    flag_age_seconds = collect_correction_flag_ages_seconds(
        normalized_flags=normalized_flags,
        now=now,
        required_flag_names=required_flag_names,
    )
    timestamp_diagnostics = collect_correction_flag_timestamp_diagnostics(
        normalized_flags=normalized_flags,
        now=now,
        required_flag_names=required_flag_names,
        max_age_seconds=flags_max_age_seconds,
    )

    if workflow_phase_open:
        stale_flags = collect_stale_correction_flags(
            normalized_flags=normalized_flags,
            now=now,
            required_flag_names=required_flag_names,
            max_age_seconds=flags_max_age_seconds,
            require_timestamps=False,
            default_require_timestamps=flags_require_timestamps,
        )
        if stale_flags:
            stale_flag_reasons = build_stale_flag_reasons(
                stale_flags=stale_flags,
                timestamp_diagnostics=timestamp_diagnostics,
                require_timestamps=False,
            )
            return {
                "can_run": False,
                "reason_code": "stale_flags",
                "missing_flags": [],
                "stale_flags": stale_flags,
                "stale_flag_reasons": stale_flag_reasons,
                "flags": normalized_flags,
                "flag_age_seconds": flag_age_seconds,
                "require_timestamps": False,
                "timestamp_diagnostics": timestamp_diagnostics,
            }

        logger.info(
            "Zone correction gating overridden by workflow phase",
            extra={
                "workflow_phase": normalized_workflow_phase,
                "open_phases": sorted(correction_open_phases),
                "flags_snapshot": normalized_flags,
            },
        )
        return {
            "can_run": True,
            "reason_code": "workflow_phase_open",
            "missing_flags": [],
            "stale_flags": [],
            "stale_flag_reasons": {},
            "flags": normalized_flags,
            "flag_age_seconds": flag_age_seconds,
            "require_timestamps": False,
            "timestamp_diagnostics": timestamp_diagnostics,
            "workflow_phase_override": normalized_workflow_phase,
        }

    missing_flags = [name for name in required_flag_names if normalized_flags[name] is None]
    if missing_flags:
        return {
            "can_run": False,
            "reason_code": "missing_flags",
            "missing_flags": missing_flags,
            "stale_flags": [],
            "stale_flag_reasons": {},
            "flags": normalized_flags,
            "flag_age_seconds": flag_age_seconds,
            "require_timestamps": require_timestamps,
            "timestamp_diagnostics": timestamp_diagnostics,
        }

    stale_flags = collect_stale_correction_flags(
        normalized_flags=normalized_flags,
        now=now,
        required_flag_names=required_flag_names,
        max_age_seconds=flags_max_age_seconds,
        require_timestamps=require_timestamps,
        default_require_timestamps=flags_require_timestamps,
    )
    if stale_flags:
        stale_flag_reasons = build_stale_flag_reasons(
            stale_flags=stale_flags,
            timestamp_diagnostics=timestamp_diagnostics,
            require_timestamps=require_timestamps,
        )
        return {
            "can_run": False,
            "reason_code": "stale_flags",
            "missing_flags": [],
            "stale_flags": stale_flags,
            "stale_flag_reasons": stale_flag_reasons,
            "flags": normalized_flags,
            "flag_age_seconds": flag_age_seconds,
            "require_timestamps": require_timestamps,
            "timestamp_diagnostics": timestamp_diagnostics,
        }

    if not normalized_flags["flow_active"]:
        return {
            "can_run": False,
            "reason_code": "flow_inactive",
            "missing_flags": [],
            "stale_flags": [],
            "stale_flag_reasons": {},
            "flags": normalized_flags,
            "flag_age_seconds": flag_age_seconds,
            "require_timestamps": require_timestamps,
            "timestamp_diagnostics": timestamp_diagnostics,
        }
    if not normalized_flags["stable"]:
        return {
            "can_run": False,
            "reason_code": "sensor_unstable",
            "missing_flags": [],
            "stale_flags": [],
            "stale_flag_reasons": {},
            "flags": normalized_flags,
            "flag_age_seconds": flag_age_seconds,
            "require_timestamps": require_timestamps,
            "timestamp_diagnostics": timestamp_diagnostics,
        }
    if not normalized_flags["corrections_allowed"]:
        return {
            "can_run": False,
            "reason_code": "corrections_not_allowed",
            "missing_flags": [],
            "stale_flags": [],
            "stale_flag_reasons": {},
            "flags": normalized_flags,
            "flag_age_seconds": flag_age_seconds,
            "require_timestamps": require_timestamps,
            "timestamp_diagnostics": timestamp_diagnostics,
        }

    return {
        "can_run": True,
        "reason_code": "gating_passed",
        "missing_flags": [],
        "stale_flags": [],
        "stale_flag_reasons": {},
        "flags": normalized_flags,
        "flag_age_seconds": flag_age_seconds,
        "require_timestamps": require_timestamps,
        "timestamp_diagnostics": timestamp_diagnostics,
    }


__all__ = [
    "build_correction_gating_state",
    "build_stale_flag_reasons",
    "collect_correction_flag_ages_seconds",
    "collect_correction_flag_timestamp_diagnostics",
    "collect_stale_correction_flags",
    "normalize_optional_bool",
    "parse_optional_timestamp",
]
