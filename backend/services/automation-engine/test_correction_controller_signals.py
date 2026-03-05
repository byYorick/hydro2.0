from __future__ import annotations

from datetime import datetime

import pytest

from correction_controller_signals import (
    build_ec_batch_debug_payload,
    build_ph_batch_debug_payload,
    emit_correction_actuator_unavailable_signal,
    emit_ec_batch_unavailable_signal,
    emit_ph_batch_unavailable_signal,
    resolve_correction_transient_alerts,
)
from services.resilience_contract import (
    INFRA_CORRECTION_ACTUATOR_UNAVAILABLE,
    INFRA_CORRECTION_COMMAND_UNCONFIRMED,
    INFRA_CORRECTION_EC_BATCH_UNAVAILABLE,
    INFRA_CORRECTION_PH_BATCH_UNAVAILABLE,
)


def test_build_ec_batch_debug_payload_keeps_only_ec_component_roles() -> None:
    payload = build_ec_batch_debug_payload(
        {
            "ec_npk_pump": {
                "node_uid": "nd-1",
                "channel": "ec_npk",
                "ml_per_sec": 1.2,
                "pump_calibration": {"ml_per_sec": 1.2},
            },
            "ph_acid_pump": {
                "node_uid": "nd-2",
                "channel": "ph_down",
            },
        }
    )

    assert sorted(payload.keys()) == ["ec_npk_pump"]
    assert payload["ec_npk_pump"]["node_uid"] == "nd-1"
    assert payload["ec_npk_pump"]["channel"] == "ec_npk"


def test_build_ec_batch_debug_payload_serializes_datetime_values() -> None:
    payload = build_ec_batch_debug_payload(
        {
            "ec_npk_pump": {
                "node_uid": "nd-1",
                "channel": "ec_npk",
                "ml_per_sec": 1.2,
                "pump_calibration": {
                    "ml_per_sec": 1.2,
                    "calibrated_at": datetime(2026, 3, 4, 11, 0, 0),
                },
            },
        }
    )

    assert payload["ec_npk_pump"]["pump_calibration"]["calibrated_at"] == "2026-03-04T11:00:00"


def test_build_ph_batch_debug_payload_keeps_only_ph_component_roles() -> None:
    payload = build_ph_batch_debug_payload(
        {
            "ph_acid_pump": {
                "node_uid": "nd-1",
                "channel": "ph_down",
                "ml_per_sec": 0.55,
                "pump_calibration": {"ml_per_sec": 0.55},
            },
            "ec_npk_pump": {"node_uid": "nd-2", "channel": "ec_npk"},
        }
    )

    assert sorted(payload.keys()) == ["ph_acid_pump"]
    assert payload["ph_acid_pump"]["node_uid"] == "nd-1"
    assert payload["ph_acid_pump"]["channel"] == "ph_down"


@pytest.mark.asyncio
async def test_emit_correction_actuator_unavailable_signal_sends_infra_alert() -> None:
    calls = []

    async def fake_send_infra_alert_fn(**kwargs):
        calls.append(kwargs)
        return True

    await emit_correction_actuator_unavailable_signal(
        zone_id=10,
        metric_name="ec",
        correction_type="add_nutrients",
        available_roles=["ec_npk_pump"],
        send_infra_alert_fn=fake_send_infra_alert_fn,
    )

    assert len(calls) == 1
    assert calls[0]["code"] == INFRA_CORRECTION_ACTUATOR_UNAVAILABLE
    assert calls[0]["zone_id"] == 10
    assert calls[0]["details"]["reason_code"] == "actuator_unavailable"


@pytest.mark.asyncio
async def test_emit_correction_actuator_unavailable_signal_passes_lifecycle_context() -> None:
    calls = []

    async def fake_send_infra_alert_fn(**kwargs):
        calls.append(kwargs)
        return True

    await emit_correction_actuator_unavailable_signal(
        zone_id=10,
        metric_name="ec",
        correction_type="dilute",
        available_roles=["recirculation_pump"],
        cycle_id=44,
        intent_id="intent-44",
        correlation_id="corr-44",
        send_infra_alert_fn=fake_send_infra_alert_fn,
    )

    assert calls[0]["cycle_id"] == 44
    assert calls[0]["intent_id"] == "intent-44"
    assert calls[0]["details"]["cycle_id"] == 44
    assert calls[0]["details"]["intent_id"] == "intent-44"
    assert calls[0]["details"]["correlation_id"] == "corr-44"


@pytest.mark.asyncio
async def test_emit_ec_batch_unavailable_signal_persists_event_and_alert() -> None:
    event_calls = []
    alert_calls = []

    async def fake_create_zone_event_fn(zone_id, event_type, details):
        event_calls.append((zone_id, event_type, details))
        return None

    async def fake_send_infra_alert_fn(**kwargs):
        alert_calls.append(kwargs)
        return True

    await emit_ec_batch_unavailable_signal(
        zone_id=11,
        allowed_ec_components=["npk", "calcium"],
        target_ec=1.05,
        current_ec=0.49,
        total_ml=4.0,
        actuators={
            "ec_npk_pump": {
                "node_uid": "nd-ec",
                "channel": "ec_npk",
                "ml_per_sec": 1.0,
                "pump_calibration": {"ml_per_sec": 1.0},
            },
            "ph_base_pump": {"node_uid": "nd-ph", "channel": "ph_up"},
        },
        create_zone_event_fn=fake_create_zone_event_fn,
        send_infra_alert_fn=fake_send_infra_alert_fn,
    )

    assert len(event_calls) == 1
    zone_id, event_type, details = event_calls[0]
    assert zone_id == 11
    assert event_type == "EC_CORRECTION_SKIPPED"
    assert details["reason"] == "ec_component_batch_unavailable"
    assert sorted(details["ec_batch_debug"].keys()) == ["ec_npk_pump"]

    assert len(alert_calls) == 1
    assert alert_calls[0]["code"] == INFRA_CORRECTION_EC_BATCH_UNAVAILABLE
    assert alert_calls[0]["zone_id"] == 11
    assert alert_calls[0]["details"]["reason_code"] == "ec_component_batch_unavailable"


@pytest.mark.asyncio
async def test_emit_ph_batch_unavailable_signal_persists_event_and_alert() -> None:
    event_calls = []
    alert_calls = []

    async def fake_create_zone_event_fn(zone_id, event_type, details):
        event_calls.append((zone_id, event_type, details))
        return None

    async def fake_send_infra_alert_fn(**kwargs):
        alert_calls.append(kwargs)
        return True

    await emit_ph_batch_unavailable_signal(
        zone_id=12,
        correction_type="add_acid",
        target_ph=5.8,
        current_ph=6.4,
        actuators={
            "ph_acid_pump": {
                "node_uid": "nd-ph",
                "channel": "ph_down",
                "ml_per_sec": 0.5,
                "pump_calibration": {"ml_per_sec": 0.5},
            },
            "ec_npk_pump": {"node_uid": "nd-ec", "channel": "ec_npk"},
        },
        create_zone_event_fn=fake_create_zone_event_fn,
        send_infra_alert_fn=fake_send_infra_alert_fn,
    )

    assert len(event_calls) == 1
    zone_id, event_type, details = event_calls[0]
    assert zone_id == 12
    assert event_type == "PH_CORRECTION_SKIPPED"
    assert details["reason"] == "ph_component_batch_unavailable"
    assert sorted(details["ph_batch_debug"].keys()) == ["ph_acid_pump"]
    assert details["correction_type"] == "add_acid"

    assert len(alert_calls) == 1
    assert alert_calls[0]["code"] == INFRA_CORRECTION_PH_BATCH_UNAVAILABLE
    assert alert_calls[0]["zone_id"] == 12
    assert alert_calls[0]["details"]["reason_code"] == "ph_component_batch_unavailable"


@pytest.mark.asyncio
async def test_resolve_correction_transient_alerts_emits_resolved_for_all_correction_codes() -> None:
    calls = []

    async def fake_send_infra_resolved_alert_fn(**kwargs):
        calls.append(kwargs)
        return True

    await resolve_correction_transient_alerts(
        zone_id=15,
        metric_name="ec",
        reason_code="correction_command_confirmed",
        cycle_id=501,
        intent_id="intent-501",
        correlation_id="corr-501",
        send_infra_resolved_alert_fn=fake_send_infra_resolved_alert_fn,
    )

    assert len(calls) == 4
    assert calls[0]["code"] == INFRA_CORRECTION_COMMAND_UNCONFIRMED
    assert calls[0]["error_type"] == "CommandUnconfirmed"
    assert all(call["cycle_id"] == 501 for call in calls)
    assert all(call["intent_id"] == "intent-501" for call in calls)
    assert all(call["details"]["correlation_id"] == "corr-501" for call in calls)
