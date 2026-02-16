"""Unit tests for application.dispatch_merge helpers."""

from application.dispatch_merge import merge_command_dispatch_results


def test_merge_command_dispatch_results_accumulates_and_keeps_error():
    merged = merge_command_dispatch_results(
        *[
            {
                "success": True,
                "commands_total": 1,
                "commands_failed": 0,
                "commands_submitted": 1,
                "commands_effect_confirmed": 1,
                "command_statuses": [{"terminal_status": "DONE"}],
            },
            {
                "success": False,
                "commands_total": 1,
                "commands_failed": 1,
                "commands_submitted": 1,
                "commands_effect_confirmed": 0,
                "command_statuses": [{"terminal_status": "SEND_FAILED"}],
                "error_code": "send_failed",
                "error": "send_failed",
            },
        ],
        err_two_tank_command_failed="two_tank_command_failed",
    )
    assert merged["success"] is False
    assert merged["commands_total"] == 2
    assert merged["commands_failed"] == 1
    assert merged["error_code"] == "send_failed"
