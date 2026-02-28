"""Direct SQL read-model for effective targets runtime path."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from common.db import fetch
from repositories.effective_targets_sql_utils import (
    apply_overrides,
    build_base_targets,
    clean_null_values,
    merge_runtime_profile,
    resolve_phase_due_at,
    to_iso,
)

logger = logging.getLogger(__name__)

_ACTIVE_CYCLE_STATUSES = ["RUNNING", "PAUSED", "PLANNED"]


class EffectiveTargetsSqlReadModel:
    """Resolves effective targets directly from PostgreSQL."""

    def __init__(self, cache_ttl_sec: float = 30.0):
        self._cache_ttl_sec = max(0.0, float(cache_ttl_sec))
        self._cache: Dict[int, Tuple[Optional[Dict[str, Any]], float]] = {}

    def invalidate_cache(self, zone_id: Optional[int] = None) -> None:
        """Invalidate cached effective targets.

        Args:
            zone_id: Zone to invalidate. When ``None``, the entire cache is cleared.
        """
        if zone_id is None:
            self._cache.clear()
        else:
            self._cache.pop(zone_id, None)

    def _lookup_cache(self, zone_id: int, now_monotonic: float) -> Tuple[bool, Optional[Dict[str, Any]]]:
        cached = self._cache.get(zone_id)
        if not cached:
            return False, None
        payload, ts = cached
        if now_monotonic - ts >= self._cache_ttl_sec:
            return False, None
        return True, payload

    async def _load_cycles(self, zone_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        rows = await fetch(
            """
            SELECT DISTINCT ON (gc.zone_id)
                gc.id AS cycle_id,
                gc.zone_id,
                gc.status,
                gc.current_phase_id,
                gc.current_stage_code,
                gc.phase_started_at,
                gc.progress_meta
            FROM grow_cycles gc
            WHERE gc.zone_id = ANY($1::int[])
              AND gc.status = ANY($2::text[])
            ORDER BY
                gc.zone_id,
                CASE gc.status
                    WHEN 'RUNNING' THEN 0
                    WHEN 'PAUSED' THEN 1
                    WHEN 'PLANNED' THEN 2
                    ELSE 9
                END,
                gc.id DESC
            """,
            zone_ids,
            _ACTIVE_CYCLE_STATUSES,
        )
        return {int(row["zone_id"]): dict(row) for row in rows}

    async def _load_phases(self, phase_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        rows = await fetch(
            """
            SELECT
                id,
                name,
                progress_model,
                duration_hours,
                duration_days,
                base_temp_c,
                ph_target,
                ph_min,
                ph_max,
                ec_target,
                ec_min,
                ec_max,
                irrigation_mode,
                irrigation_interval_sec,
                irrigation_duration_sec,
                lighting_photoperiod_hours,
                lighting_start_time,
                temp_air_target,
                humidity_target,
                co2_target,
                mist_interval_sec,
                mist_duration_sec,
                mist_mode,
                extensions
            FROM grow_cycle_phases
            WHERE id = ANY($1::bigint[])
            """,
            phase_ids or [0],
        )
        return {int(row["id"]): dict(row) for row in rows}

    async def _load_overrides(self, cycle_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
        rows = await fetch(
            """
            SELECT grow_cycle_id, parameter, value_type, value
            FROM grow_cycle_overrides
            WHERE grow_cycle_id = ANY($1::bigint[])
              AND is_active = TRUE
              AND (applies_from IS NULL OR applies_from <= NOW())
              AND (applies_until IS NULL OR applies_until >= NOW())
            ORDER BY id ASC
            """,
            cycle_ids or [0],
        )
        overrides_by_cycle: Dict[int, List[Dict[str, Any]]] = {}
        for row in rows:
            cycle_id = int(row["grow_cycle_id"])
            overrides_by_cycle.setdefault(cycle_id, []).append(dict(row))
        return overrides_by_cycle

    async def _load_runtime_profiles(self, zone_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        rows = await fetch(
            """
            SELECT DISTINCT ON (zone_id)
                zone_id,
                mode,
                subsystems,
                updated_at
            FROM zone_automation_logic_profiles
            WHERE zone_id = ANY($1::int[])
              AND is_active = TRUE
            ORDER BY zone_id, updated_at DESC, id DESC
            """,
            zone_ids,
        )
        return {int(row["zone_id"]): dict(row) for row in rows}

    def _build_effective_targets(
        self,
        *,
        zone_id: int,
        cycle: Dict[str, Any],
        phase: Dict[str, Any],
        overrides: List[Dict[str, Any]],
        runtime_profile: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        targets = build_base_targets(phase)
        targets = apply_overrides(targets, overrides)
        targets = merge_runtime_profile(targets, runtime_profile)
        targets = clean_null_values(targets)
        phase_due_at = resolve_phase_due_at(cycle, phase)

        return {
            "cycle_id": int(cycle["cycle_id"]),
            "zone_id": zone_id,
            "phase": {
                "id": int(phase["id"]),
                "code": str(cycle.get("current_stage_code") or "UNKNOWN"),
                "name": str(phase.get("name") or "UNKNOWN"),
                "started_at": to_iso(cycle.get("phase_started_at")),
                "due_at": to_iso(phase_due_at),
                "progress_model": phase.get("progress_model"),
            },
            "targets": targets,
        }

    async def get_effective_targets_batch(self, zone_ids: List[int]) -> Dict[int, Optional[Dict[str, Any]]]:
        if not zone_ids:
            return {}

        normalized_zone_ids = [int(zone_id) for zone_id in zone_ids if int(zone_id) > 0]
        if not normalized_zone_ids:
            return {}

        now_monotonic = time.monotonic()
        results: Dict[int, Optional[Dict[str, Any]]] = {}
        missing_zone_ids: List[int] = []

        for zone_id in normalized_zone_ids:
            found, cached_payload = self._lookup_cache(zone_id, now_monotonic)
            if found:
                results[zone_id] = cached_payload
            else:
                missing_zone_ids.append(zone_id)

        if not missing_zone_ids:
            return results

        try:
            cycle_by_zone = await self._load_cycles(missing_zone_ids)
            phase_ids = [int(row["current_phase_id"]) for row in cycle_by_zone.values() if row.get("current_phase_id")]
            phase_by_id = await self._load_phases(phase_ids)
            cycle_ids = [int(row["cycle_id"]) for row in cycle_by_zone.values()]
            overrides_by_cycle = await self._load_overrides(cycle_ids)
            profile_by_zone = await self._load_runtime_profiles(missing_zone_ids)

            for zone_id in missing_zone_ids:
                cycle = cycle_by_zone.get(zone_id)
                if not cycle:
                    results[zone_id] = None
                    self._cache[zone_id] = (None, now_monotonic)
                    continue

                phase = phase_by_id.get(int(cycle.get("current_phase_id") or 0))
                if not phase:
                    results[zone_id] = None
                    self._cache[zone_id] = (None, now_monotonic)
                    continue

                payload = self._build_effective_targets(
                    zone_id=zone_id,
                    cycle=cycle,
                    phase=phase,
                    overrides=overrides_by_cycle.get(int(cycle["cycle_id"]), []),
                    runtime_profile=profile_by_zone.get(zone_id),
                )
                results[zone_id] = payload
                self._cache[zone_id] = (payload, now_monotonic)
        except Exception as exc:
            logger.error("Failed to load effective targets from SQL read-model: %s", exc, exc_info=True)
            for zone_id in missing_zone_ids:
                results.setdefault(zone_id, None)

        return results

    async def get_effective_targets(self, zone_id: int) -> Optional[Dict[str, Any]]:
        payload = await self.get_effective_targets_batch([zone_id])
        return payload.get(zone_id)
