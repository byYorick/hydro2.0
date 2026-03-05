from domain.policies.decision_policy import decide_action


def test_decide_action_skips_non_manual_step_when_manual_mode_enabled():
    decision = decide_action(
        task_type="irrigation",
        payload={"_runtime_control_mode": "manual"},
        auto_logic_decision_v1=True,
        auto_logic_new_sensors_v1=True,
    )

    assert decision.action_required is False
    assert decision.reason_code == "manual_mode_only"


def test_decide_action_allows_manual_step_when_manual_mode_enabled():
    decision = decide_action(
        task_type="diagnostics",
        payload={"_runtime_control_mode": "manual", "workflow": "manual_step"},
        auto_logic_decision_v1=True,
        auto_logic_new_sensors_v1=True,
    )

    assert decision.action_required is True
    assert decision.reason_code != "manual_mode_only"


def test_decide_action_skips_cycle_start_when_manual_mode_enabled():
    decision = decide_action(
        task_type="diagnostics",
        payload={"_runtime_control_mode": "manual", "workflow": "cycle_start"},
        auto_logic_decision_v1=True,
        auto_logic_new_sensors_v1=True,
    )

    assert decision.action_required is False
    assert decision.reason_code == "manual_mode_only"
