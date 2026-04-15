"""Unit tests for ae3lite.config.modes (Phase 5)."""

from __future__ import annotations

import pytest

from ae3lite.config.modes import ConfigMode


@pytest.mark.parametrize("raw,expected", [
    ("locked", ConfigMode.LOCKED),
    ("LOCKED", ConfigMode.LOCKED),
    ("  Locked  ", ConfigMode.LOCKED),
    ("live", ConfigMode.LIVE),
    ("LIVE", ConfigMode.LIVE),
    (" live", ConfigMode.LIVE),
])
def test_parse_normalizes_string(raw, expected) -> None:
    assert ConfigMode.parse(raw) is expected


@pytest.mark.parametrize("raw", [None, "", "unknown", "frozen", 0, [], {}])
def test_parse_unknown_falls_back_to_locked(raw) -> None:
    assert ConfigMode.parse(raw) is ConfigMode.LOCKED


def test_parse_passes_through_enum_instance() -> None:
    assert ConfigMode.parse(ConfigMode.LIVE) is ConfigMode.LIVE
    assert ConfigMode.parse(ConfigMode.LOCKED) is ConfigMode.LOCKED


def test_value_round_trip() -> None:
    assert ConfigMode.LOCKED.value == "locked"
    assert ConfigMode.LIVE.value == "live"
