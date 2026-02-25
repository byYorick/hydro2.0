from repositories.infrastructure_repository import InfrastructureRepository


def test_extract_pump_calibration_prefers_new_table_values():
    row = {
        "calibration_ml_per_sec": 1.25,
        "calibration_k_ms_per_ml_l": 0.55,
        "calibration_component": "npk",
        "calibration_source": "manual_calibration",
        "calibration_quality_score": 0.9,
        "calibration_sample_count": 2,
        "calibration_valid_from": "2026-02-25T10:00:00Z",
        "channel_config": {
            "pump_calibration": {"ml_per_sec": 9.0, "k_ms_per_ml_l": 9.0},
        },
    }

    calibration = InfrastructureRepository._extract_pump_calibration(row=row)

    assert calibration["ml_per_sec"] == 1.25
    assert calibration["k_ms_per_ml_l"] == 0.55
    assert calibration["source"] == "manual_calibration"


def test_extract_pump_calibration_falls_back_to_legacy_config():
    row = {
        "calibration_ml_per_sec": None,
        "calibration_k_ms_per_ml_l": None,
        "channel_config": {
            "pump_calibration": {"ml_per_sec": 2.0, "k_ms_per_ml_l": 0.75, "component": "micro"},
        },
    }

    calibration = InfrastructureRepository._extract_pump_calibration(row=row)

    assert calibration["ml_per_sec"] == 2.0
    assert calibration["k_ms_per_ml_l"] == 0.75
    assert calibration["source"] == "legacy_config_fallback"
