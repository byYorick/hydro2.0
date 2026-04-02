from __future__ import annotations

import logging

from ae3lite.application.use_cases.manual_control_contract import normalize_control_mode


def test_normalize_control_mode_logs_unknown_value_and_falls_back_to_auto(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        result = normalize_control_mode("AUTOX")

    assert result == "auto"
    assert "unknown control_mode=autox" in caplog.text
