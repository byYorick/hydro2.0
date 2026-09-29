"""E248: unattended_ready ложен при любом блокере §11.7; пустой список — истина."""

from __future__ import annotations

from ae4.domain.unattended import UnattendedFacts, evaluate_unattended


def _facts(**overrides: object) -> UnattendedFacts:
    base = UnattendedFacts(
        planting_active=True,
        control_mode="auto",
        stale_ec_allows_shot=True,
        nutrient_solution_volume_l=200.0,
        ec_clean=0.2,
        has_clean_fill_binding=True,
        has_feed_topup_binding=True,
        has_frame_with_duration_ms=True,
        has_level_feed=True,
        has_level_clean=True,
        phase_has_ec_target=False,
        has_drain_path=False,
        solution_temp_norm_present=False,
        heater_channel_bound=False,
        co2_norm_present=False,
        co2_channel_bound=False,
        mist_norm_present=False,
        mist_channel_bound=False,
        light_no_guaranteed_off=False,
        telegram_test_ok=True,
        obs_alive=True,
        has_open_task_or_lease=False,
    )
    return UnattendedFacts(**{**base.__dict__, **overrides})


def test_e248_empty_blockers_ready_true() -> None:
    assessment = evaluate_unattended(_facts())
    assert assessment.ready is True
    assert assessment.blockers == ()


def test_e248_manual_blocks_ready() -> None:
    assessment = evaluate_unattended(_facts(control_mode="manual"))
    assert assessment.ready is False
    assert any(item.reason_code == "control_mode_manual" for item in assessment.blockers)
    assert all(item.human_message for item in assessment.blockers)


def test_e248_empty_stale_ec_blocks_ready() -> None:
    assessment = evaluate_unattended(_facts(stale_ec_allows_shot=None))
    assert assessment.ready is False
    assert any(item.reason_code == "stale_ec_setting_empty" for item in assessment.blockers)


def test_e248_missing_volume_blocks_ready() -> None:
    assessment = evaluate_unattended(_facts(nutrient_solution_volume_l=None))
    assert assessment.ready is False
    assert any(item.reason_code == "tank_volume_missing" for item in assessment.blockers)
