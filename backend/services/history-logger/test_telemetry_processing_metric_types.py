"""Tests for telemetry_processing metric type mapping."""

from telemetry.helpers import build_sensor_label, infer_sensor_type


def test_infer_sensor_type_supports_soil_and_weather_metrics():
    assert infer_sensor_type("SOIL_MOISTURE") == "SOIL_MOISTURE"
    assert infer_sensor_type("SOIL_TEMP") == "SOIL_TEMP"
    assert infer_sensor_type("WIND_SPEED") == "WIND_SPEED"
    assert infer_sensor_type("OUTSIDE_TEMP") == "OUTSIDE_TEMP"


def test_tds_metric_maps_to_other_sensor_type_separate_from_ec():
    """TDS (ppm) с ec_node — отдельный MQTT channel ec_tds_ppm; не должен резолвиться как EC."""
    assert infer_sensor_type("TDS") == "OTHER"
    assert build_sensor_label("TDS", "ec_tds_ppm", "OTHER") == "ec_tds_ppm"
    assert build_sensor_label("EC", "ec_sensor", "EC") == "ec_sensor"
