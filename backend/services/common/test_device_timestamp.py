"""Tests for normalize_device_timestamp."""

from common.utils.time import normalize_device_timestamp


def test_normalize_device_timestamp_milliseconds():
    ts_ms, ts_sec = normalize_device_timestamp(1737979200000)
    assert ts_ms == 1737979200000
    assert ts_sec == 1737979200


def test_normalize_device_timestamp_seconds():
    ts_ms, ts_sec = normalize_device_timestamp(1737979200)
    assert ts_ms == 1737979200000
    assert ts_sec == 1737979200


def test_normalize_device_timestamp_invalid():
    assert normalize_device_timestamp(None) == (None, None)
    assert normalize_device_timestamp(-1) == (None, None)
