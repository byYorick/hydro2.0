"""Unit tests for diagnostics helper policy."""

from domain.policies.diagnostics_policy import build_diagnostics_invalid_payload_result


def test_build_diagnostics_invalid_payload_result_shapes_fail_response():
    result = build_diagnostics_invalid_payload_result(
        reason_code="invalid_payload_contract_version",
        reason="payload contract mismatch",
        payload_contract_version="v9",
    )
    assert result["success"] is False
    assert result["task_type"] == "diagnostics"
    assert result["decision"] == "fail"
    assert result["error_code"] == "invalid_payload_contract_version"
    assert result["payload_contract_version"] == "v9"
