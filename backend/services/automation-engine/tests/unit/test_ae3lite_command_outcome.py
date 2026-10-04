"""Одинаковые входы normal/recovery имеют один terminal contract."""
from datetime import datetime

import pytest

from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.command_outcome import decode_command_outcome


@pytest.mark.parametrize("status", ["PENDING", "QUEUED", "SENT", "ACK", "RUNNING"])
def test_nonterminal_observation_is_not_success_or_error(status):
    row = {"status": status, "error_message": "obsolete transport error", "ack_at": datetime(2026, 1, 1)}
    ordinary = decode_command_outcome(row)
    replay = decode_command_outcome(dict(row))
    assert ordinary == replay
    assert ordinary.terminal_status is None
    assert ordinary.last_error is None


@pytest.mark.parametrize("status", ["DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"])
def test_terminal_result_replays_without_new_decision(status):
    row = {"status": status, "updated_at": datetime(2026, 1, 1)}
    result = decode_command_outcome(row)
    assert result == decode_command_outcome(dict(row))
    assert result.terminal_status == status
    assert (result.last_error is None) == (status == "DONE")


@pytest.mark.parametrize("status,code", [("ACCEPTED", "command_protocol_violation"), ("", "ae3_unsupported_legacy_status")])
def test_unsupported_protocol_result_is_rejected(status, code):
    with pytest.raises(TaskExecutionError) as caught:
        decode_command_outcome({"status": status})
    assert caught.value.code == code
