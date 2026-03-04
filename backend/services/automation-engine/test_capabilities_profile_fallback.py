from __future__ import annotations

from repositories.capabilities_profile_fallback import (
    resolve_zone_capabilities_with_profile_fallback,
)


_DEFAULT = {
    "ph_control": False,
    "ec_control": False,
    "climate_control": False,
    "light_control": False,
    "irrigation_control": False,
    "recirculation": False,
    "flow_sensor": False,
}


def test_capabilities_fallback_derives_from_active_profile_subsystems():
    resolved = resolve_zone_capabilities_with_profile_fallback(
        raw_capabilities={
            "ph_control": False,
            "ec_control": False,
            "climate_control": False,
            "light_control": False,
            "irrigation_control": False,
            "recirculation": False,
            "flow_sensor": False,
        },
        profile_subsystems={
            "ph": {"enabled": True},
            "ec": {"enabled": True},
            "climate": {"enabled": True},
            "lighting": {"enabled": True},
            "irrigation": {"enabled": True, "execution": {"tanks_count": 2}},
            "diagnostics": {"enabled": True, "execution": {"topology": "two_tank_drip_substrate_trays"}},
        },
        default_capabilities=_DEFAULT,
    )

    assert resolved["ph_control"] is True
    assert resolved["ec_control"] is True
    assert resolved["climate_control"] is True
    assert resolved["light_control"] is True
    assert resolved["irrigation_control"] is True
    assert resolved["recirculation"] is True


def test_capabilities_fallback_keeps_non_empty_zone_capabilities_unchanged():
    resolved = resolve_zone_capabilities_with_profile_fallback(
        raw_capabilities={
            "ph_control": False,
            "ec_control": True,
            "climate_control": False,
            "light_control": False,
            "irrigation_control": False,
            "recirculation": False,
            "flow_sensor": False,
        },
        profile_subsystems={
            "ph": {"enabled": True},
            "ec": {"enabled": True},
            "irrigation": {"enabled": True, "execution": {"tanks_count": 2}},
        },
        default_capabilities=_DEFAULT,
    )

    assert resolved["ec_control"] is True
    assert resolved["ph_control"] is False
    assert resolved["irrigation_control"] is False
    assert resolved["recirculation"] is False


def test_capabilities_fallback_returns_defaults_when_profile_missing():
    resolved = resolve_zone_capabilities_with_profile_fallback(
        raw_capabilities={},
        profile_subsystems={},
        default_capabilities=_DEFAULT,
    )
    assert resolved == _DEFAULT
