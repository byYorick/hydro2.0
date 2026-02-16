"""Unit tests for normalization/coercion policy helpers."""

from domain.policies.normalization_policy import (
    canonical_sensor_label,
    merge_dict_recursive,
    normalize_labels,
    resolve_float,
    resolve_int,
)


def test_resolve_int_falls_back_and_clamps_minimum():
    assert resolve_int(raw="bad", default=5, minimum=1) == 5
    assert resolve_int(raw=-3, default=5, minimum=0) == 0


def test_resolve_float_clamps_between_bounds():
    assert resolve_float(raw="bad", default=1.5, minimum=0.0, maximum=2.0) == 1.5
    assert resolve_float(raw=5, default=1.5, minimum=0.0, maximum=2.0) == 2.0


def test_normalize_labels_handles_csv_and_fallback():
    assert normalize_labels(raw="A, b ,,C", default=("x",)) == ["a", "b", "c"]
    assert normalize_labels(raw=[], default=("x", "Y")) == ["x", "y"]


def test_canonical_sensor_label_normalizes_symbols():
    assert canonical_sensor_label(" Clean Tank  MAX ") == "clean_tank_max"
    assert canonical_sensor_label("") == ""


def test_merge_dict_recursive_merges_nested_dicts():
    merged = merge_dict_recursive(
        base={"a": 1, "nested": {"x": 1, "y": 2}},
        patch={"nested": {"y": 20, "z": 30}, "b": 2},
    )
    assert merged == {"a": 1, "nested": {"x": 1, "y": 20, "z": 30}, "b": 2}
