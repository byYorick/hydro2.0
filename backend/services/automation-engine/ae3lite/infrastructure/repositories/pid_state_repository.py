"""PostgreSQL repository for AE3-Lite PID runtime state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from common.db import get_pool

_SQL_UPSERT = """
    INSERT INTO pid_state (
        zone_id,
        pid_type,
        integral,
        prev_error,
        prev_derivative,
        last_output_ms,
        last_dose_at,
        hold_until,
        last_measurement_at,
        last_measured_value,
        feedforward_bias,
        no_effect_count,
        last_correction_kind,
        created_at,
        updated_at
    )
    VALUES (
        $1,
        $2,
        COALESCE($3, 0.0),
        $4,
        COALESCE($5, 0.0),
        COALESCE($6, 0),
        $7,
        $8,
        $9,
        $10,
        COALESCE($11, 0.0),
        COALESCE($12, 0),
        $13,
        $14,
        $14
    )
    ON CONFLICT (zone_id, pid_type)
    DO UPDATE SET
        integral = COALESCE(EXCLUDED.integral, pid_state.integral),
        prev_error = COALESCE(EXCLUDED.prev_error, pid_state.prev_error),
        prev_derivative = COALESCE(EXCLUDED.prev_derivative, pid_state.prev_derivative),
        last_output_ms = COALESCE(EXCLUDED.last_output_ms, pid_state.last_output_ms),
        last_dose_at = COALESCE(EXCLUDED.last_dose_at, pid_state.last_dose_at),
        hold_until = COALESCE(EXCLUDED.hold_until, pid_state.hold_until),
        last_measurement_at = COALESCE(EXCLUDED.last_measurement_at, pid_state.last_measurement_at),
        last_measured_value = COALESCE(EXCLUDED.last_measured_value, pid_state.last_measured_value),
        feedforward_bias = COALESCE(EXCLUDED.feedforward_bias, pid_state.feedforward_bias),
        no_effect_count = COALESCE(EXCLUDED.no_effect_count, pid_state.no_effect_count),
        last_correction_kind = COALESCE(EXCLUDED.last_correction_kind, pid_state.last_correction_kind),
        updated_at = EXCLUDED.updated_at
"""


class PgPidStateRepository:
    """Persist additive runtime state for PH/EC controllers."""

    def _normalize_timestamp(self, value: datetime) -> datetime:
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
        return normalized.replace(microsecond=0)

    def _normalize_params(
        self,
        *,
        zone_id: int,
        pid_type: str,
        now: datetime,
        integral: Optional[float] = None,
        prev_error: Optional[float] = None,
        prev_derivative: Optional[float] = None,
        last_output_ms: Optional[int] = None,
        last_dose_at: Optional[datetime] = None,
        hold_until: Optional[datetime] = None,
        last_measurement_at: Optional[datetime] = None,
        last_measured_value: Optional[float] = None,
        feedforward_bias: Optional[float] = None,
        no_effect_count: Optional[int] = None,
        last_correction_kind: Optional[str] = None,
    ) -> tuple:
        return (
            zone_id,
            str(pid_type or "").strip().lower(),
            integral,
            prev_error,
            prev_derivative,
            last_output_ms,
            self._normalize_timestamp(last_dose_at) if isinstance(last_dose_at, datetime) else None,
            self._normalize_timestamp(hold_until) if isinstance(hold_until, datetime) else None,
            self._normalize_timestamp(last_measurement_at) if isinstance(last_measurement_at, datetime) else None,
            last_measured_value,
            feedforward_bias,
            no_effect_count,
            last_correction_kind,
            self._normalize_timestamp(now),
        )

    async def upsert_state(
        self,
        *,
        zone_id: int,
        pid_type: str,
        now: datetime,
        integral: Optional[float] = None,
        prev_error: Optional[float] = None,
        prev_derivative: Optional[float] = None,
        last_output_ms: Optional[int] = None,
        last_dose_at: Optional[datetime] = None,
        hold_until: Optional[datetime] = None,
        last_measurement_at: Optional[datetime] = None,
        last_measured_value: Optional[float] = None,
        feedforward_bias: Optional[float] = None,
        no_effect_count: Optional[int] = None,
        last_correction_kind: Optional[str] = None,
    ) -> None:
        params = self._normalize_params(
            zone_id=zone_id, pid_type=pid_type, now=now,
            integral=integral, prev_error=prev_error, prev_derivative=prev_derivative,
            last_output_ms=last_output_ms, last_dose_at=last_dose_at,
            hold_until=hold_until, last_measurement_at=last_measurement_at,
            last_measured_value=last_measured_value, feedforward_bias=feedforward_bias,
            no_effect_count=no_effect_count, last_correction_kind=last_correction_kind,
        )
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(_SQL_UPSERT, *params)

    async def upsert_states(
        self,
        *,
        zone_id: int,
        now: datetime,
        updates: list[dict],
    ) -> None:
        """Atomically upsert multiple pid_type states within a single transaction.

        Each item in ``updates`` is a dict accepted by ``upsert_state`` minus
        ``zone_id`` and ``now`` (those are shared).
        """
        all_params = [
            self._normalize_params(zone_id=zone_id, now=now, **update)
            for update in updates
        ]
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                for params in all_params:
                    await conn.execute(_SQL_UPSERT, *params)

    async def clear_feedforward_bias(self, *, zone_id: int) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE pid_state
                SET feedforward_bias = 0.0,
                    updated_at = NOW()
                WHERE zone_id = $1
                """,
                zone_id,
            )

    async def read_measured_value(self, *, zone_id: int, pid_type: str) -> Optional[float]:
        """Return the most recently persisted last_measured_value for a PID type.

        Used by dose steps to retrieve the measurement that triggered the dose,
        avoiding reliance on the potentially stale plan.runtime pid_state snapshot.
        Returns None if no row exists yet.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT last_measured_value
                FROM pid_state
                WHERE zone_id = $1 AND pid_type = $2
                """,
                zone_id,
                str(pid_type or "").strip().lower(),
            )
        return float(row["last_measured_value"]) if row and row["last_measured_value"] is not None else None

    async def reset_no_effect_counts(self, *, zone_id: int) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE pid_state
                SET no_effect_count = 0,
                    last_correction_kind = NULL,
                    updated_at = NOW()
                WHERE zone_id = $1
                """,
                zone_id,
            )
