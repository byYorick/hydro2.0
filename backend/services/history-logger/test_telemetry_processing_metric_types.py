"""Tests for telemetry_processing metric type mapping."""

from telemetry_processing import _infer_sensor_type


def test_infer_sensor_type_supports_soil_and_weather_metrics():
    assert _infer_sensor_type("SOIL_MOISTURE") == "SOIL_MOISTURE"
    assert _infer_sensor_type("SOIL_TEMP") == "SOIL_TEMP"
    assert _infer_sensor_type("WIND_SPEED") == "WIND_SPEED"
    assert _infer_sensor_type("OUTSIDE_TEMP") == "OUTSIDE_TEMP"
