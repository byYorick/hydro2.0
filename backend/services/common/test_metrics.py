"""Tests for metrics normalization module."""
import pytest
from common.metrics import Metric, normalize_metric_type, UnknownMetricError, CANONICAL_METRICS


def test_normalize_metric_type_valid():
    """Test normalization of valid metric types."""
    assert normalize_metric_type("ph") == "ph"
    assert normalize_metric_type("PH") == "ph"
    assert normalize_metric_type("  PH  ") == "ph"
    assert normalize_metric_type("temp_air") == "temp_air"
    assert normalize_metric_type("TEMP_AIR") == "temp_air"
    assert normalize_metric_type("  TEMP_AIR  ") == "temp_air"
    assert normalize_metric_type("ec") == "ec"
    assert normalize_metric_type("water_level") == "water_level"


def test_normalize_metric_type_invalid():
    """Test normalization of invalid metric types raises error."""
    with pytest.raises(UnknownMetricError):
        normalize_metric_type("unknown_metric")
    
    with pytest.raises(UnknownMetricError):
        normalize_metric_type("pH_invalid")
    
    with pytest.raises(UnknownMetricError):
        normalize_metric_type("")


def test_canonical_metrics_completeness():
    """Test that all Metric enum values are in CANONICAL_METRICS."""
    for metric in Metric:
        assert metric.value in CANONICAL_METRICS
        assert CANONICAL_METRICS[metric.value] == metric


def test_unknown_metric_error():
    """Test UnknownMetricError exception."""
    error = UnknownMetricError("test_metric")
    assert error.metric_type == "test_metric"
    assert "test_metric" in str(error)

