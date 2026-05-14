"""Исполнение одного tick климата теплицы (DB + history-logger)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from statistics import median
from typing import Any, Mapping

from ae3lite.greenhouse_climate.decision_engine import compute_climate_decision
from ae3lite.infrastructure.clients import HistoryLoggerClient
from common.db import execute, fetch

logger = logging.getLogger(__name__)

_LEASE_OWNER = "ae3_greenhouse_climate"
_TERMINAL_STATUSES = {"DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"}
_SUCCESS_STATUS = "DONE"


def _parse_bundle(config: Mapping[str, Any] | None) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
    if not isinstance(config, dict):
        return {}, None, {}
    gh = config.get("greenhouse")
    if not isinstance(gh, dict):
        return {}, None, {}
    lp = gh.get("logic_profile")
    if not isinstance(lp, dict):
        return {}, None, {}
    mode = lp.get("active_mode")
    active_mode = str(mode).strip().lower() if isinstance(mode, str) else None
    if active_mode not in {"setup", "working"}:
        return {}, None, {}
    prof = lp.get("profiles", {}).get(active_mode)
    if not isinstance(prof, dict):
        return {}, active_mode, {}
    sub = prof.get("subsystems") or {}
    climate = sub.get("climate") if isinstance(sub, dict) else None
    if not isinstance(climate, dict):
        return {}, active_mode, {}
    return climate, active_mode, lp


async def _ensure_state_row(greenhouse_id: int) -> None:
    await execute(
        """
        INSERT INTO greenhouse_automation_state (greenhouse_id, climate_enabled, control_mode, created_at, updated_at)
        VALUES ($1, false, 'auto', now(), now())
        ON CONFLICT (greenhouse_id) DO NOTHING
        """,
        greenhouse_id,
    )


async def _load_manual_override(greenhouse_id: int) -> dict[str, Any] | None:
    rows = await fetch(
        """
        SELECT id, left_position_pct, right_position_pct, ttl_sec, return_mode, reason, expires_at
        FROM greenhouse_manual_overrides
        WHERE greenhouse_id = $1 AND expires_at > now()
        ORDER BY id DESC
        LIMIT 1
        """,
        greenhouse_id,
    )
    if not rows:
        return None
    r = dict(rows[0])
    return {
        "id": int(r.get("id") or 0),
        "left_position_pct": int(r.get("left_position_pct") or 0),
        "right_position_pct": int(r.get("right_position_pct") or 0),
        "ttl_sec": int(r.get("ttl_sec") or 0),
        "return_mode": str(r.get("return_mode") or "auto"),
        "reason": r.get("reason"),
        "expires_at": r.get("expires_at"),
    }


async def _restore_expired_manual_override(greenhouse_id: int, state: Mapping[str, Any]) -> str | None:
    override_id = state.get("active_manual_override_id")
    if override_id is None:
        return None
    rows = await fetch(
        """
        SELECT return_mode
        FROM greenhouse_manual_overrides
        WHERE id = $1 AND greenhouse_id = $2 AND expires_at <= now()
        LIMIT 1
        """,
        int(override_id),
        greenhouse_id,
    )
    if not rows:
        return None
    return_mode = str(rows[0].get("return_mode") or "auto").strip().lower()
    if return_mode not in {"auto", "semi", "manual"}:
        return_mode = "auto"
    await execute(
        """
        UPDATE greenhouse_automation_state
        SET control_mode = $2,
            active_manual_override_id = NULL,
            updated_at = now()
        WHERE greenhouse_id = $1
        """,
        greenhouse_id,
        return_mode,
    )
    return return_mode


async def _claim_greenhouse_lease(greenhouse_id: int, *, ttl_sec: int = 120) -> bool:
    now = datetime.now(timezone.utc)
    leased_until = now + timedelta(seconds=max(1, int(ttl_sec)))
    rows = await fetch(
        """
        INSERT INTO greenhouse_automation_leases (greenhouse_id, owner, leased_until, updated_at)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (greenhouse_id) DO UPDATE
        SET owner = EXCLUDED.owner,
            leased_until = EXCLUDED.leased_until,
            updated_at = EXCLUDED.updated_at
        WHERE greenhouse_automation_leases.owner = EXCLUDED.owner
           OR greenhouse_automation_leases.leased_until <= $4
        RETURNING greenhouse_id
        """,
        greenhouse_id,
        _LEASE_OWNER,
        leased_until,
        now,
    )
    return bool(rows)


async def _release_greenhouse_lease(greenhouse_id: int) -> None:
    await execute(
        """
        DELETE FROM greenhouse_automation_leases
        WHERE greenhouse_id = $1 AND owner = $2
        """,
        greenhouse_id,
        _LEASE_OWNER,
    )


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_truthy_sensor_value(value: float) -> bool:
    return value >= 0.5


async def _sensor_snapshot(greenhouse_id: int, freshness_sec: int) -> dict[str, Any]:
    rows = await fetch(
        """
        SELECT s.scope::text AS scope,
               s.type::text AS type,
               s.label,
               tl.last_value,
               tl.last_ts,
               tl.last_quality::text AS last_quality
        FROM sensors s
        LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
        WHERE s.greenhouse_id = $1 AND s.is_active IS TRUE
        """,
        greenhouse_id,
    )
    now = datetime.now(timezone.utc)
    inside_temps: list[float] = []
    inside_rhs: list[float] = []
    outside_temp = outside_rh = wind_speed = wind_dir = outside_lux = None
    rain = False
    weather_fresh = False
    inside_fresh = False

    def _fresh(ts: Any) -> bool:
        if ts is None:
            return False
        if not isinstance(ts, datetime):
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (now - ts).total_seconds() <= float(freshness_sec)

    for row in rows or []:
        scope = str(row.get("scope") or "").lower()
        st = str(row.get("type") or "")
        label = str(row.get("label") or "").strip().lower()
        val = row.get("last_value")
        ts = row.get("last_ts")
        q = str(row.get("last_quality") or "").upper()
        fresh = _fresh(ts) and q != "BAD"
        if not fresh:
            continue
        fv = _as_float(val)
        if fv is None:
            continue
        if scope == "inside" and (st == "TEMPERATURE" or label in {"temperature", "temp_air"}):
            inside_temps.append(fv)
            inside_fresh = inside_fresh or fresh
        elif scope == "inside" and (st == "HUMIDITY" or label in {"humidity", "humidity_air"}):
            inside_rhs.append(fv)
            inside_fresh = inside_fresh or fresh
        elif scope == "outside" and (st in {"TEMPERATURE", "OUTSIDE_TEMP"} or label == "outside_temp"):
            outside_temp = fv
            weather_fresh = weather_fresh or fresh
        elif scope == "outside" and (st in {"HUMIDITY", "OUTSIDE_HUMIDITY"} or label == "outside_humidity"):
            outside_rh = fv
            weather_fresh = weather_fresh or fresh
        elif st == "WIND_SPEED" or label == "wind_speed":
            wind_speed = fv
            weather_fresh = weather_fresh or fresh
        elif st == "WIND_DIRECTION" or label == "wind_direction":
            wind_dir = fv
            weather_fresh = weather_fresh or fresh
        elif scope == "outside" and (st == "LIGHT_INTENSITY" or label in {"outside_light", "light"}):
            outside_lux = fv
            weather_fresh = weather_fresh or fresh
        elif scope == "outside" and st == "OUTSIDE_LIGHT":
            outside_lux = fv
            weather_fresh = weather_fresh or fresh
        elif scope == "outside" and (st in {"RAIN_DETECTED", "RAIN"} or label in {"rain_detected", "rain"}):
            rain = _is_truthy_sensor_value(fv)
            weather_fresh = weather_fresh or fresh

    it_med = float(median(inside_temps)) if inside_temps else None
    it_max = max(inside_temps) if inside_temps else None
    irh_max = max(inside_rhs) if inside_rhs else None

    return {
        "inside_temp_median": it_med,
        "inside_temp_max": it_max,
        "inside_rh_max": irh_max,
        "outside_temp": outside_temp,
        "outside_humidity": outside_rh,
        "wind_speed": wind_speed,
        "wind_direction_deg": wind_dir,
        "rain_detected": rain,
        "outside_light_lux": outside_lux,
        "weather_fresh": weather_fresh,
        "inside_fresh": inside_fresh,
    }


async def _load_vents(greenhouse_id: int) -> dict[str, dict[str, Any]]:
    rows = await fetch(
        """
        SELECT nc.channel AS channel,
               n.uid AS node_uid,
               n.zone_id AS zone_id,
               g.uid AS greenhouse_uid
        FROM channel_bindings cb
        JOIN infrastructure_instances ii ON ii.id = cb.infrastructure_instance_id
        JOIN node_channels nc ON nc.id = cb.node_channel_id
        JOIN nodes n ON n.id = nc.node_id
        JOIN greenhouses g ON g.id = ii.owner_id
        WHERE ii.owner_type = 'greenhouse'
          AND ii.owner_id = $1
          AND nc.channel IN ('roof_vent_left', 'roof_vent_right')
        """,
        greenhouse_id,
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        ch = str(row.get("channel") or "")
        if ch:
            out[ch] = {
                "node_uid": str(row.get("node_uid") or ""),
                "zone_id": int(row.get("zone_id") or 0),
                "greenhouse_uid": str(row.get("greenhouse_uid") or ""),
            }
    return out


async def _load_greenhouse_timezone(greenhouse_id: int) -> str:
    rows = await fetch(
        "SELECT timezone FROM greenhouses WHERE id = $1 LIMIT 1",
        greenhouse_id,
    )
    if not rows:
        return "UTC"
    tz = str(rows[0].get("timezone") or "UTC").strip()
    return tz or "UTC"


def _schedule_day_for_greenhouse(*, greenhouse_tz: str, execution: Mapping[str, Any]) -> bool:
    try:
        zone = ZoneInfo(greenhouse_tz)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    now_local = datetime.now(zone)

    def _parse_hhmm(value: Any, default: str) -> tuple[int, int]:
        raw = str(value or default).strip()
        try:
            hh, mm = raw.split(":", 1)
            h = max(0, min(23, int(hh)))
            m = max(0, min(59, int(mm)))
            return h, m
        except (TypeError, ValueError):
            dh, dm = default.split(":", 1)
            return int(dh), int(dm)

    schedule = execution.get("day_schedule") if isinstance(execution.get("day_schedule"), Mapping) else {}
    if schedule:
        start_h, start_m = _parse_hhmm(schedule.get("start_local"), "08:00")
        end_h, end_m = _parse_hhmm(schedule.get("end_local"), "20:00")
    else:
        start_h = max(0, min(23, int(float(execution.get("day_start_hour") or 8))))
        end_h_raw = max(0, min(24, int(float(execution.get("day_end_hour") or 20))))
        end_h = 23 if end_h_raw == 24 else end_h_raw
        start_m = 0
        end_m = 59 if end_h_raw == 24 else 0

    current_min = now_local.hour * 60 + now_local.minute
    start_min = start_h * 60 + start_m
    end_min = end_h * 60 + end_m
    if start_min == end_min:
        return True
    if start_min < end_min:
        return start_min <= current_min < end_min
    return current_min >= start_min or current_min < end_min


async def _wait_command_terminal(cmd_id: str, *, timeout_sec: float, poll_sec: float = 1.0) -> str:
    deadline = time.monotonic() + max(0.1, float(timeout_sec))
    while True:
        rows = await fetch(
            "SELECT status FROM commands WHERE cmd_id = $1 LIMIT 1",
            cmd_id,
        )
        if rows:
            status = str(rows[0].get("status") or "").strip().upper()
            if status in _TERMINAL_STATUSES:
                return status
        if time.monotonic() >= deadline:
            return "TIMEOUT"
        await asyncio.sleep(max(0.1, float(poll_sec)))


async def run_greenhouse_climate_tick(
    *,
    greenhouse_id: int,
    idempotency_key: str,
    history_logger_client: HistoryLoggerClient,
) -> dict[str, Any]:
    await _ensure_state_row(greenhouse_id)

    claimed = await fetch(
        """
        WITH c AS (
            SELECT id FROM greenhouse_automation_intents
            WHERE greenhouse_id = $1 AND idempotency_key = $2 AND status = 'pending'
            ORDER BY id ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        UPDATE greenhouse_automation_intents AS i
        SET status = 'running',
            claimed_at = now(),
            updated_at = now()
        FROM c
        WHERE i.id = c.id
        RETURNING i.id AS intent_id
        """,
        greenhouse_id,
        idempotency_key,
    )
    if not claimed:
        return {"status": "skipped", "reason": "no_pending_intent", "greenhouse_id": greenhouse_id}

    intent_id = int(claimed[0]["intent_id"])
    lease_claimed = await _claim_greenhouse_lease(greenhouse_id)
    if not lease_claimed:
        await execute(
            """
            UPDATE greenhouse_automation_intents
            SET status = 'cancelled', completed_at = now(), updated_at = now(),
                error_code = 'greenhouse_climate_busy',
                error_message = 'Greenhouse climate writer lease is busy'
            WHERE id = $1
            """,
            intent_id,
        )
        return {"status": "skipped", "reason": "greenhouse_climate_busy", "greenhouse_id": greenhouse_id}

    task_id: int | None = None
    try:
        task_rows = await fetch(
            """
            INSERT INTO greenhouse_automation_tasks (
                greenhouse_id, intent_id, task_type, status, idempotency_key, workflow_stage, created_at, updated_at
            )
            VALUES ($1, $2, 'greenhouse_climate_tick', 'running', $3, 'decision', now(), now())
            ON CONFLICT (greenhouse_id, idempotency_key) DO UPDATE
            SET status = 'running',
                intent_id = EXCLUDED.intent_id,
                workflow_stage = 'decision',
                updated_at = now()
            RETURNING id
            """,
            greenhouse_id,
            intent_id,
            idempotency_key,
        )
        task_id = int(task_rows[0]["id"]) if task_rows else None

        bundle_rows = await fetch(
            """
            SELECT config, status
            FROM automation_effective_bundles
            WHERE scope_type = 'greenhouse' AND scope_id = $1
            LIMIT 1
            """,
            greenhouse_id,
        )
        if not bundle_rows or str(bundle_rows[0].get("status") or "").lower() != "valid":
            await execute(
                """
                UPDATE greenhouse_automation_intents
                SET status = 'failed', completed_at = now(), updated_at = now(),
                    error_code = 'greenhouse_bundle_missing', error_message = 'No valid automation bundle'
                WHERE id = $1
                """,
                intent_id,
            )
            if task_id is not None:
                await execute(
                    """
                    UPDATE greenhouse_automation_tasks
                    SET status = 'failed',
                        workflow_stage = 'bundle_load',
                        error_code = 'greenhouse_bundle_missing',
                        error_message = 'No valid automation bundle',
                        completed_at = now(),
                        updated_at = now()
                    WHERE id = $1
                    """,
                    task_id,
                )
            return {"status": "failed", "reason": "bundle_missing", "greenhouse_id": greenhouse_id}

        config = bundle_rows[0].get("config") or {}
        climate, _active_mode, _lp = _parse_bundle(config if isinstance(config, dict) else None)
        enabled = bool(climate.get("enabled") is True)
        control_mode = str(climate.get("control_mode") or "auto").strip().lower()
        execution = climate.get("execution") if isinstance(climate.get("execution"), dict) else {}

        state_rows = await fetch(
            "SELECT * FROM greenhouse_automation_state WHERE greenhouse_id = $1 LIMIT 1",
            greenhouse_id,
        )
        state = dict(state_rows[0]) if state_rows else {}
        restored_mode = await _restore_expired_manual_override(greenhouse_id, state)
        if restored_mode is not None:
            state["control_mode"] = restored_mode
            state["active_manual_override_id"] = None
        db_control = str(state.get("control_mode") or "auto").strip().lower()
        if db_control in {"auto", "semi", "manual"}:
            control_mode = db_control

        freshness = int(float(execution.get("sensor_freshness_sec") or 1200))
        snap = await _sensor_snapshot(greenhouse_id, freshness)
        vents = await _load_vents(greenhouse_id)
        override = await _load_manual_override(greenhouse_id)
        active_override_id = int(override.get("id")) if isinstance(override, dict) and override.get("id") else None

        now_ts = time.time()
        last_cmd_at = state.get("last_command_at")
        last_cmd_ts = None
        if isinstance(last_cmd_at, datetime):
            last = last_cmd_at if last_cmd_at.tzinfo else last_cmd_at.replace(tzinfo=timezone.utc)
            last_cmd_ts = last.timestamp()

        greenhouse_tz = await _load_greenhouse_timezone(greenhouse_id)
        schedule_day = _schedule_day_for_greenhouse(greenhouse_tz=greenhouse_tz, execution=execution)

        decision = compute_climate_decision(
            execution=execution,
            control_mode=control_mode,
            manual_override=override,
            inside_temp_median=snap["inside_temp_median"],
            inside_temp_max=snap["inside_temp_max"],
            inside_rh_max=snap["inside_rh_max"],
            outside_temp=snap["outside_temp"],
            outside_humidity=snap["outside_humidity"],
            wind_speed=snap["wind_speed"],
            wind_direction_deg=snap["wind_direction_deg"],
            rain_detected=bool(snap["rain_detected"]),
            outside_light_lux=snap["outside_light_lux"],
            schedule_day=schedule_day,
            weather_fresh=bool(snap["weather_fresh"]),
            inside_fresh=bool(snap["inside_fresh"]),
            current_left_pct=int(state.get("left_position_pct") or 0),
            current_right_pct=int(state.get("right_position_pct") or 0),
            now_ts=now_ts,
            last_command_ts=last_cmd_ts,
        )

        interval = int(float(execution.get("decision_interval_sec") or 900))
        next_tick_active = datetime.now(timezone.utc) + timedelta(seconds=interval)

        if not enabled:
            next_tick_idle = datetime.now(timezone.utc) + timedelta(hours=1)
            await execute(
                """
                UPDATE greenhouse_automation_state
                SET climate_enabled = false,
                    recommended_left_position_pct = $2,
                    recommended_right_position_pct = $3,
                    decision_reason = $4,
                    decision_factors = $5::jsonb,
                    weather_fresh = $6,
                    inside_climate_fresh = $7,
                    last_decision_at = now(),
                    next_scheduled_tick_at = $8,
                    active_manual_override_id = $9,
                    last_task_id = $10,
                    last_error_code = NULL,
                    last_error_message = NULL,
                    updated_at = now()
                WHERE greenhouse_id = $1
                """,
                greenhouse_id,
                decision.left_target_pct,
                decision.right_target_pct,
                decision.decision_reason,
                json.dumps(decision.factors),
                snap["weather_fresh"],
                snap["inside_fresh"],
                next_tick_idle,
                active_override_id,
                task_id,
            )
            await execute(
                """
                UPDATE greenhouse_automation_intents
                SET status = 'completed', completed_at = now(), updated_at = now()
                WHERE id = $1
                """,
                intent_id,
            )
            if task_id is not None:
                await execute(
                    """
                    UPDATE greenhouse_automation_tasks
                    SET status = 'completed',
                        workflow_stage = 'disabled',
                        decision_snapshot = $2::jsonb,
                        completed_at = now(),
                        updated_at = now()
                    WHERE id = $1
                    """,
                    task_id,
                    json.dumps({"decision_reason": decision.decision_reason, "factors": decision.factors}),
                )
            return {"status": "completed", "reason": "climate_disabled", "greenhouse_id": greenhouse_id}

        left_cmd_id = None
        right_cmd_id = None
        left_done = False
        right_done = False
        command_failures: list[str] = []
        if not decision.suppress_commands:
            for side, channel in (("left", "roof_vent_left"), ("right", "roof_vent_right")):
                target = decision.left_target_pct if side == "left" else decision.right_target_pct
                cur = int(state.get("left_position_pct") or 0) if side == "left" else int(state.get("right_position_pct") or 0)
                if target == cur:
                    continue
                vent = vents.get(channel)
                if not vent or not vent.get("node_uid") or int(vent.get("zone_id") or 0) <= 0:
                    logger.warning("greenhouse_climate_tick missing vent binding channel=%s gh=%s", channel, greenhouse_id)
                    command_failures.append(f"{channel}:MISSING_BINDING")
                    continue
                params = {
                    "position_pct": int(target),
                    "max_step_pct": int(float(execution.get("max_step_pct") or 25)),
                    "reason": decision.decision_reason,
                }
                cmd_id = str(uuid.uuid4())
                hl_id = await history_logger_client.publish(
                    greenhouse_uid=str(vent["greenhouse_uid"]),
                    zone_id=int(vent["zone_id"]),
                    node_uid=str(vent["node_uid"]),
                    channel=channel,
                    cmd="set_position",
                    params=params,
                    cmd_id=cmd_id,
                )
                if side == "left":
                    left_cmd_id = hl_id
                else:
                    right_cmd_id = hl_id

                terminal = await _wait_command_terminal(
                    hl_id,
                    timeout_sec=float(execution.get("command_terminal_timeout_sec") or 120),
                    poll_sec=float(execution.get("command_poll_sec") or 1),
                )
                if terminal == _SUCCESS_STATUS:
                    if side == "left":
                        left_done = True
                    else:
                        right_done = True
                else:
                    command_failures.append(f"{channel}:{terminal}")

        model_left = int(decision.left_target_pct) if left_done else int(state.get("left_position_pct") or 0)
        model_right = int(decision.right_target_pct) if right_done else int(state.get("right_position_pct") or 0)
        final_status = "completed" if not command_failures else "failed"
        error_code = None if not command_failures else "greenhouse_vent_command_failed"
        error_message = None if not command_failures else ", ".join(command_failures)

        await execute(
            """
            UPDATE greenhouse_automation_state
            SET climate_enabled = true,
                control_mode = $2,
                left_position_pct = $3,
                right_position_pct = $4,
                recommended_left_position_pct = $5,
                recommended_right_position_pct = $6,
                last_sent_left_position_pct = CASE WHEN $14 THEN $5 ELSE last_sent_left_position_pct END,
                last_sent_right_position_pct = CASE WHEN $15 THEN $6 ELSE last_sent_right_position_pct END,
                decision_reason = $7,
                decision_factors = $8::jsonb,
                weather_fresh = $11,
                inside_climate_fresh = $12,
                last_decision_at = now(),
                last_command_at = CASE WHEN ($9::varchar IS NOT NULL OR $10::varchar IS NOT NULL) THEN now() ELSE last_command_at END,
                last_left_cmd_id = COALESCE($9, last_left_cmd_id),
                last_right_cmd_id = COALESCE($10, last_right_cmd_id),
                next_scheduled_tick_at = $13,
                active_manual_override_id = $16,
                last_task_id = $17,
                last_error_code = $18,
                last_error_message = $19,
                updated_at = now()
            WHERE greenhouse_id = $1
            """,
            greenhouse_id,
            control_mode,
            model_left,
            model_right,
            decision.left_target_pct,
            decision.right_target_pct,
            decision.decision_reason,
            json.dumps(decision.factors),
            left_cmd_id,
            right_cmd_id,
            snap["weather_fresh"],
            snap["inside_fresh"],
            next_tick_active,
            left_done,
            right_done,
            active_override_id,
            task_id,
            error_code,
            error_message,
        )

        await execute(
            """
            UPDATE greenhouse_automation_intents
            SET status = $2, completed_at = now(), updated_at = now(),
                error_code = $3,
                error_message = $4
            WHERE id = $1
            """,
            intent_id,
            final_status,
            error_code,
            error_message,
        )
        if task_id is not None:
            await execute(
                """
                UPDATE greenhouse_automation_tasks
                SET status = $2,
                    workflow_stage = 'terminal',
                    decision_snapshot = $3::jsonb,
                    command_refs = $4::jsonb,
                    error_code = $5,
                    error_message = $6,
                    completed_at = now(),
                    updated_at = now()
                WHERE id = $1
                """,
                task_id,
                final_status,
                json.dumps({"decision_reason": decision.decision_reason, "factors": decision.factors}),
                json.dumps({"left_cmd_id": left_cmd_id, "right_cmd_id": right_cmd_id}),
                error_code,
                error_message,
            )

        return {
            "status": "ok" if final_status == "completed" else "failed",
            "greenhouse_id": greenhouse_id,
            "decision": decision.decision_reason,
            "suppress": decision.suppress_commands,
            "left_cmd_id": left_cmd_id,
            "right_cmd_id": right_cmd_id,
            "command_failures": command_failures,
        }
    except Exception as exc:
        logger.error("greenhouse_climate_tick failed gh=%s intent=%s", greenhouse_id, intent_id, exc_info=True)
        await execute(
            """
            UPDATE greenhouse_automation_intents
            SET status = 'failed', completed_at = now(), updated_at = now(),
                error_code = 'greenhouse_climate_tick_failed', error_message = $2
            WHERE id = $1
            """,
            intent_id,
            str(exc)[:2000],
        )
        if task_id is not None:
            await execute(
                """
                UPDATE greenhouse_automation_tasks
                SET status = 'failed',
                    workflow_stage = 'exception',
                    error_code = 'greenhouse_climate_tick_failed',
                    error_message = $2,
                    completed_at = now(),
                    updated_at = now()
                WHERE id = $1
                """,
                task_id,
                str(exc)[:2000],
            )
        raise
    finally:
        if lease_claimed:
            await _release_greenhouse_lease(greenhouse_id)


__all__ = ["run_greenhouse_climate_tick"]
