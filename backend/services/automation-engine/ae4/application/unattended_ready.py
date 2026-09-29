"""Сбор фактов §11.7 и запись unattended в ответ состояния зоны."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Mapping
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

from ae4.application.mutation_decision import (
    has_clean_fill_steps,
    has_solution_fill_steps,
)
from ae4.config.zone_plan import (
    ZonePlan,
    ZonePlanConfigurationError,
    load_zone_plan,
    require_plan_steps,
)
from ae4.domain.drain_policy import has_drain_circuit, has_feed_to_drain_plan_steps
from ae4.domain.light_policy import LIGHT_NO_GUARANTEED_OFF, light_unattended_blocker
from ae4.domain.unattended import (
    UnattendedAssessment,
    UnattendedBlocker,
    UnattendedFacts,
    evaluate_unattended,
)
from ae4.infrastructure.failure_report import report_critical_call
from ae4.infrastructure.phase_loader import PhaseLoadError, load_planting_state
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from ae4.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from ae4.infrastructure.zone_telemetry import load_zone_telemetry
from common.db import create_zone_event, fetch

logger = logging.getLogger(__name__)

_SNAPSHOT_TYPE = "AE4_UNATTENDED_SNAPSHOT"
_HEATER_CHANNELS = frozenset({"heater", "solution_heater"})
_CO2_CHANNELS = frozenset({"co2", "co2_valve", "co2_injector"})
_MIST_CHANNELS = frozenset({"mister", "mist", "fog"})
_ALERT_POLICIES_NS = "system.alert_policies"


async def assess_zone_unattended(
    *,
    zone_id: int,
    now: Any,
    emit_regression_alerts: bool = True,
) -> UnattendedAssessment:
    """Собирает факты и оценивает готовность. Тик не останавливает."""
    facts = await collect_unattended_facts(zone_id=zone_id, now=now)
    assessment = evaluate_unattended(facts)
    if emit_regression_alerts:
        await _maybe_alert_regression(zone_id=zone_id, assessment=assessment)
    await _store_snapshot(zone_id=zone_id, assessment=assessment)
    return assessment


async def collect_unattended_facts(*, zone_id: int, now: Any) -> UnattendedFacts:
    runtime = await _zone_runtime(zone_id=zone_id)
    if runtime != "ae4":
        return _empty_facts()

    plan: ZonePlan | None = None
    planting = None
    try:
        plan = await load_zone_plan(zone_id=zone_id)
        planting = await load_planting_state(zone_id=zone_id)
    except (ZonePlanConfigurationError, PhaseLoadError):
        plan = None
        planting = None

    control_mode = await _control_mode(zone_id=zone_id)
    stale_ec: bool | None = None
    volume: float | None = await _read_phase_volume(zone_id=zone_id)
    ec_clean: float | None = await _read_ec_clean(zone_id=zone_id)
    has_clean = False
    has_feed = False
    has_frame = False
    has_level_feed = False
    has_level_clean = False
    phase_has_ec = False
    has_drain = False
    sol_temp_norm = False
    co2_norm = False
    mist_norm = False
    light_blocker = False
    planting_active = planting is not None and plan is not None

    if plan is not None:
        control_mode = plan.control_mode
        stale_ec = plan.stale_ec_allows_shot
        volume = float(plan.nutrient_solution_volume_l)
        ec_clean = plan.ec_clean
        has_clean = has_clean_fill_steps(plan=plan)
        has_feed = has_solution_fill_steps(plan=plan)
        try:
            require_plan_steps(plan, plan_key="irrigation_start")
            has_irrigation = True
        except ZonePlanConfigurationError:
            has_irrigation = False
        has_frame = bool(
            has_irrigation
            and planting is not None
            and planting.phase.duration_sec is not None
            and planting.phase.duration_sec > 0
        )
        telemetry = await load_zone_telemetry(
            zone_id=zone_id,
            now=now,
            telemetry_max_age_sec=plan.telemetry_max_age_sec,
        )
        has_level_feed = (
            telemetry.level_solution_min.bound and telemetry.level_solution_max.bound
        )
        has_level_clean = (
            telemetry.level_clean_min.bound and telemetry.level_clean_max.bound
        )
        has_drain = has_drain_circuit(
            level_drain_min_bound=telemetry.level_drain_min.bound,
            level_drain_max_bound=telemetry.level_drain_max.bound,
            ec_drain_bound=telemetry.ec_drain is not None,
            has_feed_to_drain_steps=has_feed_to_drain_plan_steps(
                command_plans=plan.command_plans
            ),
        )
        light_reason = await light_unattended_blocker(plan=plan, zone_id=zone_id)
        light_blocker = light_reason == LIGHT_NO_GUARANTEED_OFF

    if planting is not None:
        phase = planting.phase
        phase_has_ec = phase.ec_target is not None
        sol_temp_norm = (
            phase.solution_temp_min is not None or phase.solution_temp_max is not None
        )
        co2_norm = phase.co2_target is not None
        mist_norm = (
            phase.mist_interval_sec is not None
            or phase.mist_duration_sec is not None
            or (phase.mist_mode is not None and str(phase.mist_mode).strip() != "")
        )

    bound = await _channel_bindings(zone_id=zone_id)
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    active = await task_repo.get_active_for_zone(zone_id=zone_id)
    lease = await lease_repo.get(zone_id=zone_id)

    return UnattendedFacts(
        planting_active=planting_active,
        control_mode=control_mode,
        stale_ec_allows_shot=stale_ec,
        nutrient_solution_volume_l=volume,
        ec_clean=ec_clean,
        has_clean_fill_binding=has_clean,
        has_feed_topup_binding=has_feed,
        has_frame_with_duration_ms=has_frame,
        has_level_feed=has_level_feed,
        has_level_clean=has_level_clean,
        phase_has_ec_target=phase_has_ec,
        has_drain_path=has_drain,
        solution_temp_norm_present=sol_temp_norm,
        heater_channel_bound=bool(bound & _HEATER_CHANNELS),
        co2_norm_present=co2_norm,
        co2_channel_bound=bool(bound & _CO2_CHANNELS),
        mist_norm_present=mist_norm,
        mist_channel_bound=bool(bound & _MIST_CHANNELS),
        light_no_guaranteed_off=light_blocker,
        telegram_test_ok=await _telegram_test_ok(),
        obs_alive=probe_obs_alive(),
        has_open_task_or_lease=active is not None or lease is not None,
    )


def assessment_to_payload(assessment: UnattendedAssessment) -> dict[str, Any]:
    return {
        "unattended_ready": bool(assessment.ready),
        "unattended_blockers": [
            {
                "reason_code": item.reason_code,
                "human_message": item.human_message,
            }
            for item in assessment.blockers
        ],
    }


def probe_obs_alive() -> bool:
    """Живой сигнал Prometheus blackbox / mqtt probe. Нет ответа — блокер."""
    base = str(os.environ.get("PROMETHEUS_URL") or "http://prometheus:9090").rstrip("/")
    query = 'up{job="blackbox"} or probe_success{job="mqtt-broker"}'
    url = f"{base}/api/v1/query?query={quote(query)}"
    try:
        with urlopen(url, timeout=2.0) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError) as exc:
        logger.info("AE4 obs probe silent: %s", exc)
        return False
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False
    if payload.get("status") != "success":
        return False
    results = (payload.get("data") or {}).get("result") or []
    if not isinstance(results, list):
        return False
    for item in results:
        if not isinstance(item, Mapping):
            continue
        value = item.get("value")
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            continue
        if str(value[1]).strip() in {"1", "1.0"}:
            return True
    return False


def _empty_facts() -> UnattendedFacts:
    return UnattendedFacts(
        planting_active=False,
        control_mode="manual",
        stale_ec_allows_shot=None,
        nutrient_solution_volume_l=None,
        ec_clean=None,
        has_clean_fill_binding=False,
        has_feed_topup_binding=False,
        has_frame_with_duration_ms=False,
        has_level_feed=False,
        has_level_clean=False,
        phase_has_ec_target=False,
        has_drain_path=False,
        solution_temp_norm_present=False,
        heater_channel_bound=False,
        co2_norm_present=False,
        co2_channel_bound=False,
        mist_norm_present=False,
        mist_channel_bound=False,
        light_no_guaranteed_off=False,
        telegram_test_ok=False,
        obs_alive=False,
        has_open_task_or_lease=False,
    )


async def _maybe_alert_regression(
    *,
    zone_id: int,
    assessment: UnattendedAssessment,
) -> None:
    previous = await _load_snapshot(zone_id=zone_id)
    was_ready = bool(previous.get("unattended_ready")) if previous else False
    if not was_ready or assessment.ready:
        return
    for blocker in assessment.blockers:
        await report_critical_call(
            zone_id=zone_id,
            reason_code=f"unattended_blocker:{blocker.reason_code}",
            human_message=blocker.human_message,
            dedupe_key=f"ae4-unattended:{zone_id}:{blocker.reason_code}",
        )


async def _store_snapshot(*, zone_id: int, assessment: UnattendedAssessment) -> None:
    await create_zone_event(zone_id, _SNAPSHOT_TYPE, assessment_to_payload(assessment))


async def _load_snapshot(*, zone_id: int) -> dict[str, Any]:
    rows = await fetch(
        """
        SELECT payload_json
        FROM zone_events
        WHERE zone_id = $1
          AND type = $2
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        zone_id,
        _SNAPSHOT_TYPE,
    )
    if not rows:
        return {}
    payload = rows[0].get("payload_json")
    return dict(payload) if isinstance(payload, dict) else {}


async def _zone_runtime(*, zone_id: int) -> str:
    rows = await fetch(
        "SELECT automation_runtime FROM zones WHERE id = $1",
        zone_id,
    )
    if not rows:
        return ""
    return str(rows[0].get("automation_runtime") or "").strip().lower()


async def _control_mode(*, zone_id: int) -> str:
    rows = await fetch("SELECT control_mode FROM zones WHERE id = $1", zone_id)
    if not rows:
        return "auto"
    return str(rows[0].get("control_mode") or "auto").strip().lower() or "auto"


async def _read_phase_volume(*, zone_id: int) -> float | None:
    rows = await fetch(
        """
        SELECT gcp.nutrient_solution_volume_l AS volume
        FROM grow_cycles AS gc
        JOIN grow_cycle_phases AS gcp ON gcp.id = gc.current_phase_id
        WHERE gc.zone_id = $1
          AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
        ORDER BY
            CASE gc.status
                WHEN 'RUNNING' THEN 1
                WHEN 'PAUSED' THEN 2
                ELSE 3
            END,
            gc.id DESC
        LIMIT 1
        """,
        zone_id,
    )
    if not rows or rows[0].get("volume") is None:
        return None
    try:
        value = float(rows[0]["volume"])
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


async def _read_ec_clean(*, zone_id: int) -> float | None:
    rows = await fetch(
        """
        SELECT bundles.config AS bundle_config
        FROM zones
        LEFT JOIN grow_cycles AS gc
            ON gc.zone_id = zones.id
           AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
        LEFT JOIN automation_effective_bundles AS bundles
            ON bundles.scope_type = 'grow_cycle'
           AND bundles.scope_id = gc.id
        WHERE zones.id = $1
        ORDER BY gc.id DESC NULLS LAST
        LIMIT 1
        """,
        zone_id,
    )
    if not rows:
        return None
    config = rows[0].get("bundle_config")
    if not isinstance(config, Mapping):
        return None
    zone = config.get("zone")
    if not isinstance(zone, Mapping):
        return None
    correction = zone.get("correction")
    if not isinstance(correction, Mapping):
        return None
    resolved = correction.get("resolved_config")
    if not isinstance(resolved, Mapping):
        return None
    timing = resolved.get("timing")
    if not isinstance(timing, Mapping):
        return None
    raw = timing.get("ec_clean")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


async def _channel_bindings(*, zone_id: int) -> set[str]:
    rows = await fetch(
        "SELECT config FROM nodes WHERE zone_id = $1",
        zone_id,
    )
    found: set[str] = set()
    for row in rows:
        config = row.get("config")
        if not isinstance(config, Mapping):
            continue
        channels = config.get("channels")
        items: list[Any] = []
        if isinstance(channels, list):
            items = list(channels)
        elif isinstance(channels, Mapping):
            items = list(channels.values())
        for item in items:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("id") or item.get("channel") or "").strip().lower()
            role = str(item.get("zone_role") or item.get("role") or "").strip().lower()
            if name:
                found.add(name)
            if role:
                found.add(role)
    return found


async def _telegram_test_ok() -> bool:
    rows = await fetch(
        """
        SELECT payload
        FROM automation_config_documents
        WHERE namespace = $1
          AND scope_type = 'system'
          AND scope_id = 0
        LIMIT 1
        """,
        _ALERT_POLICIES_NS,
    )
    if not rows:
        return False
    payload = rows[0].get("payload")
    if not isinstance(payload, Mapping):
        return False
    return payload.get("telegram_test_ok") is True


__all__ = [
    "UnattendedAssessment",
    "UnattendedBlocker",
    "assess_zone_unattended",
    "assessment_to_payload",
    "collect_unattended_facts",
    "probe_obs_alive",
]
