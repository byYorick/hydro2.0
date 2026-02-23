"""IRR-state snapshot and expected-vs-actual guard helpers for two-tank workflow."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from application.scheduler_executor_impl import *  # noqa: F401,F403

_logger = logging.getLogger(__name__)


def _to_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def _normalize_snapshot_created_at(created_at: Any) -> Optional[datetime]:
    if not isinstance(created_at, datetime):
        return None
    if created_at.tzinfo is None:
        return created_at
    return created_at.astimezone(timezone.utc).replace(tzinfo=None)


def _row_get_value(row: Any, key: str) -> Any:
    if hasattr(row, "get"):
        try:
            return row.get(key)
        except Exception:
            return None
    try:
        return row[key]
    except Exception:
        return None


async def _load_latest_irr_state_snapshot(
    self,
    *,
    zone_id: int,
) -> Optional[Dict[str, Any]]:
    try:
        rows = await self.fetch_fn(
            """
            SELECT payload_json, created_at
            FROM zone_events
            WHERE zone_id = $1
              AND type = 'IRR_STATE_SNAPSHOT'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
        )
    except Exception:
        _logger.warning(
            "Zone %s: failed to load latest IRR_STATE_SNAPSHOT",
            zone_id,
            exc_info=True,
        )
        return None

    if not rows:
        return None

    row = rows[0]
    payload_raw = _row_get_value(row, "payload_json")
    payload = payload_raw if isinstance(payload_raw, dict) else {}
    snapshot_raw = payload.get("snapshot")
    if not isinstance(snapshot_raw, dict):
        return None

    normalized_snapshot = {key: _to_optional_bool(value) for key, value in snapshot_raw.items()}
    return {
        "snapshot": normalized_snapshot,
        "created_at": _normalize_snapshot_created_at(_row_get_value(row, "created_at")),
        "cmd_id": str(payload.get("cmd_id") or "").strip() or None,
    }


async def _load_irr_state_snapshot_by_cmd_id(
    self,
    *,
    zone_id: int,
    cmd_id: str,
) -> Optional[Dict[str, Any]]:
    resolved_cmd_id = str(cmd_id or "").strip()
    if not resolved_cmd_id:
        return None

    try:
        rows = await self.fetch_fn(
            """
            SELECT payload_json, created_at
            FROM zone_events
            WHERE zone_id = $1
              AND type = 'IRR_STATE_SNAPSHOT'
              AND payload_json->>'cmd_id' = $2
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
            resolved_cmd_id,
        )
    except Exception:
        _logger.warning(
            "Zone %s: failed to load IRR_STATE_SNAPSHOT by cmd_id=%s",
            zone_id,
            resolved_cmd_id,
            exc_info=True,
        )
        return None

    if not rows:
        return None

    row = rows[0]
    payload_raw = _row_get_value(row, "payload_json")
    payload = payload_raw if isinstance(payload_raw, dict) else {}
    snapshot_raw = payload.get("snapshot")
    if not isinstance(snapshot_raw, dict):
        return None

    normalized_snapshot = {key: _to_optional_bool(value) for key, value in snapshot_raw.items()}
    return {
        "snapshot": normalized_snapshot,
        "created_at": _normalize_snapshot_created_at(_row_get_value(row, "created_at")),
        "cmd_id": resolved_cmd_id,
    }


def _build_irr_state_mismatch_result(
    *,
    workflow: str,
    expected: Dict[str, bool],
    snapshot: Dict[str, Optional[bool]],
    mismatches: List[Dict[str, Any]],
    updated_at: Optional[str],
) -> Dict[str, Any]:
    return {
        "success": False,
        "task_type": "diagnostics",
        "mode": "two_tank_irr_state_mismatch",
        "workflow": workflow,
        "commands_total": 0,
        "commands_failed": 0,
        "action_required": True,
        "decision": "run",
        "reason_code": REASON_IRR_STATE_MISMATCH,
        "reason": "Фактическое состояние irr-ноды не совпадает с ожидаемым на critical этапе",
        "error": ERR_TWO_TANK_IRR_STATE_MISMATCH,
        "error_code": ERR_TWO_TANK_IRR_STATE_MISMATCH,
        "expected_state": expected,
        "actual_state": {field: snapshot.get(field) for field in expected.keys()},
        "snapshot_updated_at": updated_at,
        "expected_vs_actual": {
            "matches": False,
            "mismatches": mismatches,
        },
    }


def _build_irr_state_unavailable_result(
    *,
    workflow: str,
    expected: Dict[str, bool],
) -> Dict[str, Any]:
    return {
        "success": False,
        "task_type": "diagnostics",
        "mode": "two_tank_irr_state_unavailable",
        "workflow": workflow,
        "commands_total": 0,
        "commands_failed": 0,
        "action_required": True,
        "decision": "run",
        "reason_code": REASON_IRR_STATE_UNAVAILABLE,
        "reason": "Нет snapshot состояния irr-ноды для expected-vs-actual проверки",
        "error": ERR_TWO_TANK_IRR_STATE_UNAVAILABLE,
        "error_code": ERR_TWO_TANK_IRR_STATE_UNAVAILABLE,
        "expected_state": expected,
    }


def _build_irr_state_stale_result(
    *,
    workflow: str,
    expected: Dict[str, bool],
    age_sec: Optional[float],
    max_age_sec: int,
    updated_at: Optional[str],
) -> Dict[str, Any]:
    return {
        "success": False,
        "task_type": "diagnostics",
        "mode": "two_tank_irr_state_stale",
        "workflow": workflow,
        "commands_total": 0,
        "commands_failed": 0,
        "action_required": True,
        "decision": "run",
        "reason_code": REASON_IRR_STATE_STALE,
        "reason": "Snapshot состояния irr-ноды устарел для expected-vs-actual проверки",
        "error": ERR_TWO_TANK_IRR_STATE_STALE,
        "error_code": ERR_TWO_TANK_IRR_STATE_STALE,
        "expected_state": expected,
        "snapshot_age_sec": age_sec,
        "snapshot_max_age_sec": max_age_sec,
        "snapshot_updated_at": updated_at,
    }


async def validate_irr_state_expected_vs_actual(
    self,
    *,
    zone_id: int,
    workflow: str,
    runtime_cfg: Dict[str, Any],
    critical_expectations: Dict[str, Dict[str, bool]],
    requested_state_cmd_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    expected = critical_expectations.get(workflow)
    if not expected:
        return None

    validation_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    cmd_id_filter = str(requested_state_cmd_id or "").strip()
    wait_timeout_sec = self._resolve_int(runtime_cfg.get("irr_state_wait_timeout_sec"), 2, 0)
    if cmd_id_filter:
        snapshot_entry = await _load_irr_state_snapshot_by_cmd_id(self, zone_id=zone_id, cmd_id=cmd_id_filter)
    else:
        snapshot_entry = await _load_latest_irr_state_snapshot(self, zone_id=zone_id)
    if snapshot_entry is None:
        if cmd_id_filter and wait_timeout_sec <= 0:
            wait_timeout_sec = 2
        if wait_timeout_sec > 0:
            deadline = asyncio.get_running_loop().time() + float(wait_timeout_sec)
            while snapshot_entry is None and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.2)
                if cmd_id_filter:
                    snapshot_entry = await _load_irr_state_snapshot_by_cmd_id(
                        self,
                        zone_id=zone_id,
                        cmd_id=cmd_id_filter,
                    )
                else:
                    snapshot_entry = await _load_latest_irr_state_snapshot(self, zone_id=zone_id)
    if snapshot_entry is None and cmd_id_filter:
        latest_snapshot = await _load_latest_irr_state_snapshot(self, zone_id=zone_id)
        latest_created_at = latest_snapshot.get("created_at") if isinstance(latest_snapshot, dict) else None
        recent_window_sec = max(2, wait_timeout_sec)
        if isinstance(latest_created_at, datetime):
            oldest_allowed = validation_started_at - timedelta(seconds=recent_window_sec)
            if latest_created_at >= oldest_allowed:
                snapshot_entry = latest_snapshot
    if snapshot_entry is None:
        return _build_irr_state_unavailable_result(workflow=workflow, expected=expected)

    snapshot_created_at = snapshot_entry.get("created_at")
    snapshot_updated_at = snapshot_created_at.isoformat() if isinstance(snapshot_created_at, datetime) else None
    age_sec: Optional[float] = None
    if isinstance(snapshot_created_at, datetime):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        age_sec = max(0.0, (now - snapshot_created_at).total_seconds())

    max_age_sec = self._resolve_int(runtime_cfg.get("irr_state_max_age_sec"), 30, 5)
    if age_sec is not None and age_sec > float(max_age_sec) and not cmd_id_filter:
        stale_created_at = snapshot_created_at if isinstance(snapshot_created_at, datetime) else None
        if wait_timeout_sec > 0:
            deadline = asyncio.get_running_loop().time() + float(wait_timeout_sec)
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.2)
                candidate = await _load_latest_irr_state_snapshot(self, zone_id=zone_id)
                candidate_created_at = candidate.get("created_at") if isinstance(candidate, dict) else None
                if not isinstance(candidate_created_at, datetime):
                    continue
                if stale_created_at is not None and candidate_created_at <= stale_created_at:
                    continue
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                candidate_age_sec = max(0.0, (now - candidate_created_at).total_seconds())
                if candidate_age_sec <= float(max_age_sec):
                    snapshot_entry = candidate
                    snapshot_created_at = candidate_created_at
                    snapshot_updated_at = snapshot_created_at.isoformat()
                    age_sec = candidate_age_sec
                    break
    if age_sec is None or age_sec > float(max_age_sec):
        return _build_irr_state_stale_result(
            workflow=workflow,
            expected=expected,
            age_sec=age_sec,
            max_age_sec=max_age_sec,
            updated_at=snapshot_updated_at,
        )

    snapshot = snapshot_entry.get("snapshot") if isinstance(snapshot_entry.get("snapshot"), dict) else {}
    mismatches: List[Dict[str, Any]] = []
    for field, expected_value in expected.items():
        actual_value = _to_optional_bool(snapshot.get(field))
        if actual_value is None or actual_value != bool(expected_value):
            mismatches.append(
                {
                    "field": field,
                    "expected": bool(expected_value),
                    "actual": actual_value,
                    "severity": "critical",
                }
            )

    if mismatches:
        return _build_irr_state_mismatch_result(
            workflow=workflow,
            expected=expected,
            snapshot=snapshot,
            mismatches=mismatches,
            updated_at=snapshot_updated_at,
        )
    return None


async def request_irr_state_snapshot_best_effort(
    self,
    *,
    zone_id: int,
    workflow: str,
) -> Optional[str]:
    try:
        irrig_nodes = await self._get_zone_nodes(zone_id, ("irrig",))
    except Exception:
        _logger.warning(
            "Zone %s: failed to resolve irrig node for irr/state request (workflow=%s)",
            zone_id,
            workflow,
            exc_info=True,
        )
        return None

    irrig_node_uid = ""
    for node in irrig_nodes:
        node_uid = str(node.get("node_uid") or "").strip()
        if node_uid:
            irrig_node_uid = node_uid
            break

    if not irrig_node_uid:
        return None

    try:
        cmd_id = f"ae-irr-state-{zone_id}-{uuid4().hex[:12]}"
        published = await self.command_gateway.publish_command(
            zone_id=zone_id,
            node_uid=irrig_node_uid,
            channel="storage_state",
            cmd="state",
            params={"dedupe_ttl_sec": 10},
            cmd_id=cmd_id,
        )
        if not published:
            _logger.warning(
                "Zone %s: irr/state command was not submitted (workflow=%s node_uid=%s)",
                zone_id,
                workflow,
                irrig_node_uid,
            )
            return None
        return cmd_id
    except Exception:
        _logger.warning(
            "Zone %s: irr/state request failed (workflow=%s node_uid=%s)",
            zone_id,
            workflow,
            irrig_node_uid,
            exc_info=True,
        )
        return None


__all__ = [
    "request_irr_state_snapshot_best_effort",
    "validate_irr_state_expected_vs_actual",
]
