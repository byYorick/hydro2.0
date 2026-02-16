"""Unit tests for cycle-start refill helper policy."""

from datetime import datetime, timedelta, timezone

from domain.policies.cycle_start_refill_policy import (
    build_refill_check_payload,
    normalize_node_type_list,
    resolve_clean_tank_threshold,
    resolve_refill_attempt,
    resolve_refill_duration_ms,
    resolve_refill_started_at,
    resolve_refill_timeout_at,
)


def _parse_iso(value: str):
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def test_normalize_node_type_list_deduplicates_and_filters_unknown():
    values = normalize_node_type_list(raw=["IRRIG", "bad_type", "irrig", "ph"], default=("irrig",))
    assert values == ["irrig", "ph"]


def test_resolve_clean_tank_threshold_clamps_and_prefers_refill_config():
    threshold = resolve_clean_tank_threshold(
        execution_config={"clean_tank_full_threshold": 0.8},
        refill_config={"clean_tank_full_threshold": "1.2"},
        default_threshold=0.95,
    )
    assert threshold == 1.0


def test_resolve_refill_duration_ms_uses_minimum():
    duration_ms = resolve_refill_duration_ms(
        execution_config={},
        refill_config={"duration_sec": 0},
        default_duration_sec=30,
    )
    assert duration_ms == 100


def test_resolve_refill_attempt_parses_non_negative_int():
    assert resolve_refill_attempt(payload={"refill_attempt": "3"}) == 3
    assert resolve_refill_attempt(payload={"refill_attempt": "-4"}) == 0


def test_resolve_refill_started_at_falls_back_to_now_for_invalid_input():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    started_at = resolve_refill_started_at(
        payload={"refill_started_at": "bad-iso"},
        now=now,
        parse_iso_datetime=_parse_iso,
    )
    assert started_at == now


def test_resolve_refill_timeout_at_prefers_explicit_payload_timestamp():
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    explicit = (started_at + timedelta(seconds=123)).isoformat()
    timeout_at = resolve_refill_timeout_at(
        payload={"refill_timeout_at": explicit},
        started_at=started_at,
        execution_config={},
        refill_config={},
        parse_iso_datetime=_parse_iso,
        default_timeout_sec=600,
    )
    assert timeout_at.isoformat() == explicit


def test_build_refill_check_payload_sets_workflow_fields():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = build_refill_check_payload(
        payload={"task_type": "diagnostics"},
        refill_started_at=now,
        refill_timeout_at=now + timedelta(seconds=60),
        next_attempt=2,
    )
    assert payload["workflow"] == "refill_check"
    assert payload["refill_attempt"] == 2
    assert payload["refill_started_at"] == now.isoformat()
