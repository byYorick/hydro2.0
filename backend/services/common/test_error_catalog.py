"""Unit-тесты локализации error_code (фаза 2)."""

from __future__ import annotations

from common.error_catalog import enrich_error_payload, present_error


def test_present_error_returns_russian_human_message() -> None:
    result = present_error("not_found")

    assert result["code"] == "not_found"
    assert result["message"] == result["human_error_message"]
    assert result["message"]
    assert any("\u0400" <= ch <= "\u04FF" for ch in str(result["message"]))


def test_enrich_error_payload_adds_human_error_message() -> None:
    enriched = enrich_error_payload(
        {
            "status": "error",
            "code": "ae3_task_create_conflict",
            "message": "ae3_task_create_conflict",
        }
    )

    assert enriched["code"] == "ae3_task_create_conflict"
    assert enriched["message"] == enriched["human_error_message"]
    assert any("\u0400" <= ch <= "\u04FF" for ch in str(enriched["human_error_message"]))


def test_present_error_prefers_localized_override() -> None:
    result = present_error("upstream_unavailable", "Сервис временно недоступен.")

    assert result["message"] == "Сервис временно недоступен."


def test_present_error_translates_unauthorized() -> None:
    result = present_error(None, "Unauthorized")

    assert result["message"]
    assert any("\u0400" <= ch <= "\u04FF" for ch in str(result["message"]))


def test_present_error_keeps_unknown_english() -> None:
    result = present_error("unknown_xyz", "Custom upstream failure")

    assert result["message"] == "Custom upstream failure"


def test_present_firmware_node_error_codes() -> None:
    for code in ("invalid_signature", "timestamp_expired", "overcurrent"):
        result = present_error(code)
        assert result["code"] == code
        assert any("\u0400" <= ch <= "\u04FF" for ch in str(result["message"]))


def test_enrich_error_payload_command_response_error_code() -> None:
    enriched = enrich_error_payload(
        {
            "status": "error",
            "error_code": "pump_in_cooldown",
            "message": "pump_in_cooldown",
        }
    )

    assert enriched["error_code"] == "pump_in_cooldown"
    assert enriched["human_error_message"]
    assert any("\u0400" <= ch <= "\u04FF" for ch in str(enriched["human_error_message"]))
