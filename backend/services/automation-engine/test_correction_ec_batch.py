from correction_ec_batch import build_ec_component_batch


def _build_command(actuator, correction_type, amount_ml):
    return {
        "cmd": "run_pump",
        "params": {
            "type": correction_type,
            "ml": amount_ml,
            "duration_ms": max(1, int(float(amount_ml) * 100)),
        },
    }


def test_build_ec_component_batch_falls_back_to_legacy_single_npk_when_components_missing():
    commands = build_ec_component_batch(
        targets={
            "nutrition": {
                "mode": "dose_ml_l_only",
                "solution_volume_l": 10.0,
            }
        },
        actuators={
            "ec_npk_pump": {
                "role": "ec_npk_pump",
                "node_uid": "nd-dosing-e2e",
                "channel": "ec_npk_pump",
                "ml_per_sec": 2.0,
            }
        },
        total_ml=20.0,
        current_ec=0.3,
        target_ec=1.8,
        allowed_ec_components=["npk"],
        build_correction_command=_build_command,
    )

    assert len(commands) == 1
    cmd = commands[0]
    assert cmd["component"] == "npk"
    assert cmd["mode"] == "legacy_single_component"
    assert cmd["params"]["type"] == "add_nutrients"
    assert cmd["params"]["component"] == "npk"
    assert cmd["params"]["ratio_pct"] == 100.0
    assert cmd["ml"] == 20.0


def test_build_ec_component_batch_skips_when_non_npk_required_component_config_missing():
    commands = build_ec_component_batch(
        targets={
            "nutrition": {
                "mode": "ratio_ec_pid",
                "solution_volume_l": 10.0,
                "components": {
                    "npk": {"ratio_pct": 70, "k_ms_per_ml_l": 0.8},
                    # calcium намеренно отсутствует
                },
            }
        },
        actuators={
            "ec_npk_pump": {"role": "ec_npk_pump", "node_uid": "nd-a", "channel": "npk", "ml_per_sec": 2.0},
            "ec_calcium_pump": {"role": "ec_calcium_pump", "node_uid": "nd-a", "channel": "calcium", "ml_per_sec": 2.0},
        },
        total_ml=20.0,
        current_ec=0.4,
        target_ec=1.8,
        allowed_ec_components=["npk", "calcium"],
        build_correction_command=_build_command,
    )

    assert commands == []


def test_build_ec_component_batch_legacy_fallback_works_for_ratio_mode_without_components():
    commands = build_ec_component_batch(
        targets={
            "nutrition": {
                "mode": "ratio_ec_pid",
                "solution_volume_l": 10.0,
                # nutrition.components отсутствует полностью
            }
        },
        actuators={
            "ec_npk_pump": {
                "role": "ec_npk_pump",
                "node_uid": "nd-dosing-e2e",
                "channel": "ec_npk_pump",
                "ml_per_sec": 1.5,
            }
        },
        total_ml=12.5,
        current_ec=0.6,
        target_ec=1.8,
        allowed_ec_components=["npk"],
        build_correction_command=_build_command,
    )

    assert len(commands) == 1
    assert commands[0]["mode"] == "legacy_single_component"
    assert commands[0]["component"] == "npk"
    assert commands[0]["ml"] == 12.5
