"""G10: метрики суток, алерты dev/prod и панели automation-engine."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from prometheus_client import REGISTRY

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.decision_gate import DecisionGateHandler
from ae3lite.hydraulics.failure_report import close_upward_capture, drain_upward_reports, open_upward_capture
from ae3lite.infrastructure.metrics import (
    CROP_IRRIGATION_BLOCKED,
    DLI_TICK_TOTAL,
    GREENHOUSE_CLIMATE_AIR_VPD_KPA,
    GREENHOUSE_CLIMATE_MOISTURE_VENT_SUPPRESSED_TOTAL,
    IRRIGATION_DECISION,
    record_greenhouse_climate_crop_metrics,
)
from test_ae3lite_dli_lighting import _series, _snapshot, _task

NOW = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
_DECISION_LABELS = {"topology": "two_tank", "strategy": "smart_soil_v1", "outcome": "skip"}
_BLOCKED_REASON = "smart_soil_telemetry_missing_or_stale"
_SOLUTION_TEMP_EXPR = "sum(solution_temp_breach_active) > 0"
_CROP_PANEL_TITLES = (
    "Доля исходов полива",
    "Блокировки полива по reason",
    "VPD воздуха по greenhouse_id",
    "Статусы DLI",
    "Рекомендации подмены раствора",
    "Подавление влажностной форточки",
)
_PANEL_METRICS = {
    "Доля исходов полива": "ae3_irrigation_decision_total",
    "Блокировки полива по reason": "ae3_crop_irrigation_blocked_total",
    "VPD воздуха по greenhouse_id": "greenhouse_climate_air_vpd_kpa",
    "Статусы DLI": "ae3_dli_tick_total",
    "Рекомендации подмены раствора": "ae3_solution_refresh_recommended_total",
    "Подавление влажностной форточки": "greenhouse_climate_moisture_vent_suppressed_total",
}
_METRIC_NAMES = set(_PANEL_METRICS.values())
_PROMQL_WORDS = {
    "sum",
    "by",
    "increase",
    "ignoring",
    "group_left",
    "rate",
    "or",
    "vector",
    "and",
    "unless",
}


class _GateDecision:
    def __init__(self, *, outcome: str, reason_code: str) -> None:
        self.outcome = outcome
        self.reason_code = reason_code
        self.degraded = False
        self.details = None


class _GateController:
    def __init__(self, decision: _GateDecision) -> None:
        self._decision = decision

    async def evaluate(self, **_kwargs):
        return self._decision


class _GateRepository:
    async def update_irrigation_runtime(self, **_kwargs):
        return SimpleNamespace(
            id=11,
            zone_id=7,
            current_stage="decision_gate",
            workflow_phase="ready",
            topology="two_tank",
            irrigation_decision_strategy="smart_soil_v1",
            irrigation_bundle_revision=None,
        )


def _gate_task(*, outcome: str | None = None, reason: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=11,
        zone_id=7,
        claimed_by="worker",
        irrigation_mode="normal",
        irrigation_requested_duration_sec=120,
        topology="two_tank",
        claim_generation=1,
        current_stage="decision_gate",
        workflow_phase="ready",
        irrigation_decision_outcome=outcome,
        irrigation_decision_reason_code=reason,
    )


def _sample(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def _run_gate(task: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_event(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "ae3lite.application.handlers.decision_gate.create_zone_event",
        _noop_event,
    )
    handler = DecisionGateHandler(
        runtime_monitor=object(),
        command_gateway=object(),
        task_repository=_GateRepository(),
        decision_controller=_GateController(
            _GateDecision(outcome="skip", reason_code=_BLOCKED_REASON),
        ),
    )
    token = open_upward_capture()
    try:
        outcome = await handler.run(
            task=task,
            plan=SimpleNamespace(runtime=make_runtime_plan(
                irrigation_decision={"strategy": "smart_soil_v1"},
            )),
            stage_def=SimpleNamespace(),
            now=NOW,
        )
        drain_upward_reports()
    finally:
        close_upward_capture(token)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "completed_skip"


@pytest.mark.asyncio
async def test_blocking_skip_counts_once_per_task_and_decision_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    assert CROP_IRRIGATION_BLOCKED._labelnames == ("reason",)
    blocked_before = _sample("ae3_crop_irrigation_blocked_total", {"reason": _BLOCKED_REASON})
    decision_before = _sample("ae3_irrigation_decision_total", _DECISION_LABELS)

    await _run_gate(_gate_task(), monkeypatch)
    assert _sample("ae3_crop_irrigation_blocked_total", {"reason": _BLOCKED_REASON}) == blocked_before + 1
    assert _sample("ae3_irrigation_decision_total", _DECISION_LABELS) == decision_before + 1

    await _run_gate(
        _gate_task(outcome="skip", reason=_BLOCKED_REASON),
        monkeypatch,
    )
    assert _sample("ae3_crop_irrigation_blocked_total", {"reason": _BLOCKED_REASON}) == blocked_before + 1
    assert _sample("ae3_irrigation_decision_total", _DECISION_LABELS) == decision_before + 2


def test_climate_tick_metrics_set_vpd_and_count_each_suppressed_tick() -> None:
    assert GREENHOUSE_CLIMATE_AIR_VPD_KPA._labelnames == ("greenhouse_id",)
    assert GREENHOUSE_CLIMATE_MOISTURE_VENT_SUPPRESSED_TOTAL._labelnames == ("greenhouse_id",)
    before = _sample(
        "greenhouse_climate_moisture_vent_suppressed_total",
        {"greenhouse_id": "15"},
    )
    factors = {"air_vpd_kpa": 1.267, "moisture_vent_suppressed": True}
    record_greenhouse_climate_crop_metrics(greenhouse_id=15, factors=factors)
    record_greenhouse_climate_crop_metrics(greenhouse_id=15, factors=factors)
    assert _sample("greenhouse_climate_air_vpd_kpa", {"greenhouse_id": "15"}) == pytest.approx(1.267)
    assert _sample(
        "greenhouse_climate_moisture_vent_suppressed_total",
        {"greenhouse_id": "15"},
    ) == before + 2
    quiet_before = _sample(
        "greenhouse_climate_moisture_vent_suppressed_total",
        {"greenhouse_id": "16"},
    )
    record_greenhouse_climate_crop_metrics(greenhouse_id=16, factors={"air_vpd_kpa": 0.4})
    assert _sample("greenhouse_climate_air_vpd_kpa", {"greenhouse_id": "16"}) == pytest.approx(0.4)
    assert _sample(
        "greenhouse_climate_moisture_vent_suppressed_total",
        {"greenhouse_id": "16"},
    ) == quiet_before


def test_dli_tick_counter_follows_built_lighting_plan_status() -> None:
    assert DLI_TICK_TOTAL._labelnames == ("status",)
    before_unavailable = _sample("ae3_dli_tick_total", {"status": "sensor_unavailable"})
    before_off = sum(
        _sample("ae3_dli_tick_total", {"status": status})
        for status in ("not_configured", "sensor_unavailable", "gap", "capped", "within_target")
    )
    from ae3lite.domain.services.cycle_start_planner import CycleStartPlanner

    planner = CycleStartPlanner(dli_alert_writer=lambda *_args, **_kwargs: None)
    lux = _snapshot(lighting={"dli_target": 5, "brightness": 55}, series=_series(unit="lux"))
    plan = planner.build(task=_task(desired="on", brightness=55), snapshot=lux)
    assert plan.steps[0].payload["dli_status"] == "sensor_unavailable"
    assert _sample("ae3_dli_tick_total", {"status": "sensor_unavailable"}) == before_unavailable + 1

    planner.build(task=_task(desired="off", brightness=55), snapshot=lux)
    after_off = sum(
        _sample("ae3_dli_tick_total", {"status": status})
        for status in ("not_configured", "sensor_unavailable", "gap", "capped", "within_target")
    )
    assert after_off == before_off + 1


def _configs_dir() -> Path:
    env = os.environ.get("HYDRO_CONFIGS_DIR", "").strip()
    candidates = [Path(env)] if env else []
    candidates.extend([
        Path("/hydro-configs"),
        Path("/home/georgiy/esp/hydro/hydro2.0/backend/configs"),
    ])
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "backend" / "configs")
        candidates.append(parent / "configs")
    for candidate in candidates:
        if (candidate / "dev" / "prometheus" / "alerts.yml").is_file():
            return candidate
    pytest.fail("backend/configs is not visible to this test")


def test_dev_and_prod_alerts_keep_one_solution_temp_rule() -> None:
    configs = _configs_dir()
    for name in ("dev", "prod"):
        text = (configs / name / "prometheus" / "alerts.yml").read_text()
        assert len(re.findall(r"(?m)^\s*- alert: AE3SmartSoilBlocked\s*$", text)) == 1
        assert len(re.findall(r"(?m)^\s*- alert: AE3DliSensorMissing\s*$", text)) == 1
        assert "GreenhouseMoistureVentSuppressed" not in text
        assert len(re.findall(r"(?m)^\s*- alert: SolutionTempOutOfBand\s*$", text)) == 1
        assert text.count(_SOLUTION_TEMP_EXPR) == 1
        assert 'sum(increase(ae3_crop_irrigation_blocked_total{reason=~"smart_soil_.+"}[15m])) > 0' in text
        assert 'sum(increase(ae3_dli_tick_total{status="sensor_unavailable"}[1h])) > 0' in text
        assert re.search(
            r"- alert: AE3SmartSoilBlocked\n(?:.*\n)*?\s+for: 0m\n\s+labels:\n\s+severity: warning",
            text,
        )
        assert re.search(
            r"- alert: AE3DliSensorMissing\n(?:.*\n)*?\s+for: 1h\n\s+labels:\n\s+severity: warning",
            text,
        )


def _metric_names(expr: str) -> set[str]:
    stripped = re.sub(
        r"\b(?:by|ignoring|on|without|group_left|group_right)\s*\([^)]*\)",
        " ",
        expr,
    )
    names = set(re.findall(r"\b[a-zA-Z_:][a-zA-Z0-9_:]*\b", stripped))
    return {name for name in names if name not in _PROMQL_WORDS}


def test_dashboards_add_crop_day_panels_without_dropping_old_ones() -> None:
    configs = _configs_dir()
    for name in ("dev", "prod"):
        doc = json.loads((configs / name / "grafana" / "dashboards" / "automation-engine.json").read_text())
        titles = [panel["title"] for panel in doc["panels"]]
        assert titles.count("Irrigation decisions (rate)") == 1
        assert "ae3_irrigation_duration_seconds_bucket" in json.dumps(doc)
        for title in _CROP_PANEL_TITLES:
            matches = [panel for panel in doc["panels"] if panel["title"] == title]
            assert len(matches) == 1
            exprs = [target["expr"] for target in matches[0].get("targets") or []]
            assert len(exprs) == 1
            assert "zone_id" not in exprs[0]
            found = _metric_names(exprs[0])
            assert found == {_PANEL_METRICS[title]}
            assert found <= _METRIC_NAMES
