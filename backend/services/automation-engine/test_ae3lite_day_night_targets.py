"""Тесты day/night override для pH/EC targets и bounds.

Покрывает:
- `_build_day_night_config` (сборка конфига из snapshot для проброса в runtime)
- `BaseStageHandler._is_day_now` (резолв is_day по локальному времени)
- `BaseStageHandler._day_night_override` (выбор day/night значения)
- `_effective_ph_target/min/max`, `_effective_ec_target/min/max` (e2e logic)
- NPK-share scaling для prepare-фазы при night override
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.services.two_tank_runtime_spec import _build_day_night_config


# ── _build_day_night_config ───────────────────────────────────────────────────


class TestBuildDayNightConfig:

    def test_disabled_when_flag_false(self) -> None:
        snapshot = SimpleNamespace(phase_targets={"day_night_enabled": False})
        cfg = _build_day_night_config(snapshot)
        assert cfg["enabled"] is False
        assert cfg["ph"] == {
            "day": None, "night": None,
            "day_min": None, "day_max": None,
            "night_min": None, "night_max": None,
        }

    def test_enabled_with_full_extensions(self) -> None:
        snapshot = SimpleNamespace(phase_targets={
            "day_night_enabled": True,
            "extensions": {
                "day_night": {
                    "lighting": {"day_start_time": "06:00", "day_hours": 16},
                    "ph": {
                        "day": 5.8, "night": 6.2,
                        "day_min": 5.6, "day_max": 6.0,
                        "night_min": 6.0, "night_max": 6.4,
                    },
                    "ec": {
                        "day": 1.6, "night": 1.2,
                        "night_min": 1.0, "night_max": 1.4,
                    },
                },
            },
        })
        cfg = _build_day_night_config(snapshot)
        assert cfg["enabled"] is True
        assert cfg["lighting"]["day_start_time"] == "06:00"
        assert cfg["lighting"]["day_hours"] == 16.0
        assert "timezone" in cfg["lighting"]
        assert cfg["ph"]["night"] == 6.2
        assert cfg["ph"]["night_min"] == 6.0
        assert cfg["ec"]["night"] == 1.2

    def test_lighting_fallback_to_phase(self) -> None:
        """Если day_night.lighting пустой — берём lighting из phase."""
        snapshot = SimpleNamespace(phase_targets={
            "day_night_enabled": True,
            "lighting": {"start_time": "07:30", "photoperiod_hours": 14.0},
            "extensions": {"day_night": {"ph": {"night": 6.5}}},
        })
        cfg = _build_day_night_config(snapshot)
        assert cfg["lighting"]["day_start_time"] == "07:30"
        assert cfg["lighting"]["day_hours"] == 14.0


# ── _is_day_now ───────────────────────────────────────────────────────────────


class TestIsDayNow:

    def test_returns_true_when_lighting_missing(self) -> None:
        # fail-safe: считаем "день" по умолчанию
        assert BaseStageHandler._is_day_now({"lighting": {}}) is True

    def test_simple_window_within_day(self) -> None:
        cfg = {"lighting": {"day_start_time": "06:00", "day_hours": 16}}
        with patch("ae3lite.application.handlers.base.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 13, 12, 0)
            assert BaseStageHandler._is_day_now(cfg) is True

    def test_simple_window_outside_day(self) -> None:
        cfg = {"lighting": {"day_start_time": "06:00", "day_hours": 16}}
        # 23:00 — после 22:00 (06:00 + 16h)
        with patch("ae3lite.application.handlers.base.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 13, 23, 0)
            assert BaseStageHandler._is_day_now(cfg) is False

    def test_overnight_wrap_within_day(self) -> None:
        # 22:00 + 8h → 06:00; в 02:00 — день
        cfg = {"lighting": {"day_start_time": "22:00", "day_hours": 8}}
        with patch("ae3lite.application.handlers.base.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 13, 2, 0)
            assert BaseStageHandler._is_day_now(cfg) is True

    def test_overnight_wrap_outside_day(self) -> None:
        cfg = {"lighting": {"day_start_time": "22:00", "day_hours": 8}}
        with patch("ae3lite.application.handlers.base.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 13, 12, 0)
            assert BaseStageHandler._is_day_now(cfg) is False

    def test_zero_hours_means_always_night(self) -> None:
        cfg = {"lighting": {"day_start_time": "06:00", "day_hours": 0}}
        assert BaseStageHandler._is_day_now(cfg) is False

    def test_24_hours_means_always_day(self) -> None:
        cfg = {"lighting": {"day_start_time": "06:00", "day_hours": 24}}
        assert BaseStageHandler._is_day_now(cfg) is True

    def test_timezone_shifts_day_window(self) -> None:
        # day_start_time=06:00 локальное время Europe/Moscow (UTC+3).
        # При UTC=03:00 в Москве уже 06:00 → день начался.
        cfg = {"lighting": {"day_start_time": "06:00", "day_hours": 16, "timezone": "Europe/Moscow"}}
        with patch("ae3lite.application.handlers.base.datetime") as mock_dt:
            utc_now = datetime(2026, 4, 13, 3, 30, tzinfo=timezone.utc)
            # datetime.now(tz) → локальное время МСК = 06:30
            mock_dt.now.side_effect = lambda tz=None: utc_now.astimezone(tz) if tz else utc_now
            assert BaseStageHandler._is_day_now(cfg) is True

    def test_timezone_at_night_utc_vs_local(self) -> None:
        # day_start_time=06:00 МСК, day_hours=16 → 06:00..22:00 МСК = 03:00..19:00 UTC.
        # UTC=22:00 → МСК=01:00 → ночь.
        cfg = {"lighting": {"day_start_time": "06:00", "day_hours": 16, "timezone": "Europe/Moscow"}}
        with patch("ae3lite.application.handlers.base.datetime") as mock_dt:
            utc_now = datetime(2026, 4, 13, 22, 0, tzinfo=timezone.utc)
            mock_dt.now.side_effect = lambda tz=None: utc_now.astimezone(tz) if tz else utc_now
            assert BaseStageHandler._is_day_now(cfg) is False

    def test_invalid_timezone_falls_back_to_utc(self) -> None:
        cfg = {"lighting": {"day_start_time": "06:00", "day_hours": 16, "timezone": "Invalid/Zone"}}
        with patch("ae3lite.application.handlers.base.datetime") as mock_dt:
            utc_now = datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc)
            mock_dt.now.side_effect = lambda tz=None: utc_now.astimezone(tz) if tz else utc_now
            assert BaseStageHandler._is_day_now(cfg) is True


# ── _day_night_override + effective_* ─────────────────────────────────────────


def _handler() -> BaseStageHandler:
    return BaseStageHandler(runtime_monitor=None, command_gateway=None)


def _runtime(*, day_night_enabled: bool, ph_section: dict | None = None, ec_section: dict | None = None,
             lighting: dict | None = None, **runtime_overrides) -> dict:
    base = {
        "target_ph": 5.8, "target_ph_min": 5.6, "target_ph_max": 6.0,
        "target_ec": 1.6, "target_ec_min": 1.5, "target_ec_max": 1.7,
        "target_ec_prepare": 0.7, "target_ec_prepare_min": 0.65, "target_ec_prepare_max": 0.75,
        "npk_ec_share": 0.44,
        "day_night_enabled": day_night_enabled,
        "day_night_config": {
            "enabled": day_night_enabled,
            "lighting": lighting or {"day_start_time": "06:00", "day_hours": 16},
            "ph": ph_section or {"day": None, "night": None, "day_min": None, "day_max": None,
                                  "night_min": None, "night_max": None},
            "ec": ec_section or {"day": None, "night": None, "day_min": None, "day_max": None,
                                  "night_min": None, "night_max": None},
        },
    }
    base.update(runtime_overrides)
    return base


def _task(workflow_phase: str = "irrigation"):
    return SimpleNamespace(
        zone_id=1,
        workflow=SimpleNamespace(workflow_phase=workflow_phase),
        current_stage=workflow_phase,
    )


@patch("ae3lite.application.handlers.base.datetime")
class TestEffectivePhTargets:

    def test_disabled_returns_base(self, mock_dt) -> None:
        mock_dt.now.return_value = datetime(2026, 4, 13, 23, 0)  # ночь
        h = _handler()
        rt = _runtime(day_night_enabled=False, ph_section={"night": 6.5})
        # disabled — игнорируем night override
        assert h._effective_ph_target(task=_task(), runtime=rt) == 5.8

    def test_night_override_target(self, mock_dt) -> None:
        mock_dt.now.return_value = datetime(2026, 4, 13, 23, 0)  # ночь
        h = _handler()
        rt = _runtime(day_night_enabled=True, ph_section={
            "day": 5.8, "night": 6.4, "night_min": None, "night_max": None,
            "day_min": None, "day_max": None,
        })
        assert h._effective_ph_target(task=_task(), runtime=rt) == 6.4

    def test_day_uses_day_value(self, mock_dt) -> None:
        mock_dt.now.return_value = datetime(2026, 4, 13, 12, 0)  # день
        h = _handler()
        rt = _runtime(day_night_enabled=True, ph_section={
            "day": 5.5, "night": 6.4, "night_min": None, "night_max": None,
            "day_min": None, "day_max": None,
        })
        assert h._effective_ph_target(task=_task(), runtime=rt) == 5.5

    def test_night_min_max_override(self, mock_dt) -> None:
        mock_dt.now.return_value = datetime(2026, 4, 13, 23, 0)
        h = _handler()
        rt = _runtime(day_night_enabled=True, ph_section={
            "day": None, "night": None, "day_min": None, "day_max": None,
            "night_min": 6.0, "night_max": 6.4,
        })
        assert h._effective_ph_min(task=_task(), runtime=rt) == 6.0
        assert h._effective_ph_max(task=_task(), runtime=rt) == 6.4

    def test_missing_night_value_falls_back_to_default(self, mock_dt) -> None:
        mock_dt.now.return_value = datetime(2026, 4, 13, 23, 0)
        h = _handler()
        rt = _runtime(day_night_enabled=True, ph_section={
            "day": None, "night": None, "day_min": None, "day_max": None,
            "night_min": None, "night_max": None,
        })
        assert h._effective_ph_target(task=_task(), runtime=rt) == 5.8


@patch("ae3lite.application.handlers.base.datetime")
class TestEffectiveEcTargets:

    def test_irrigation_phase_night_override(self, mock_dt) -> None:
        mock_dt.now.return_value = datetime(2026, 4, 13, 23, 0)
        h = _handler()
        rt = _runtime(day_night_enabled=True, ec_section={
            "day": 1.6, "night": 1.2, "day_min": None, "day_max": None,
            "night_min": 1.0, "night_max": 1.4,
        })
        assert h._effective_ec_target(task=_task("irrigation"), runtime=rt) == 1.2
        assert h._effective_ec_min(task=_task("irrigation"), runtime=rt) == 1.0
        assert h._effective_ec_max(task=_task("irrigation"), runtime=rt) == 1.4

    def test_prepare_phase_scales_by_npk_share_at_night(self, mock_dt) -> None:
        """tank_recirc + night ec target=1.2 → prepare = 1.2 * 0.44 = 0.528."""
        mock_dt.now.return_value = datetime(2026, 4, 13, 23, 0)
        h = _handler()
        rt = _runtime(day_night_enabled=True, ec_section={
            "day": 1.6, "night": 1.2, "day_min": None, "day_max": None,
            "night_min": 1.0, "night_max": 1.4,
        })
        # 1.2 * 0.44 ≈ 0.528
        assert h._effective_ec_target(task=_task("tank_recirc"), runtime=rt) == pytest.approx(0.528, abs=0.01)
        # min: 1.0 * 0.44 = 0.44
        assert h._effective_ec_min(task=_task("tank_recirc"), runtime=rt) == pytest.approx(0.44, abs=0.01)
        # max: 1.4 * 0.44 = 0.616
        assert h._effective_ec_max(task=_task("tank_recirc"), runtime=rt) == pytest.approx(0.616, abs=0.01)

    def test_prepare_phase_day_keeps_base_prepare(self, mock_dt) -> None:
        """Если день — prepare остаётся target_ec_prepare без override."""
        mock_dt.now.return_value = datetime(2026, 4, 13, 12, 0)
        h = _handler()
        rt = _runtime(day_night_enabled=True, ec_section={
            "day": 1.6, "night": 1.2, "day_min": None, "day_max": None,
            "night_min": 1.0, "night_max": 1.4,
        })
        assert h._effective_ec_target(task=_task("tank_recirc"), runtime=rt) == 0.7
        assert h._effective_ec_min(task=_task("tank_recirc"), runtime=rt) == 0.65
        assert h._effective_ec_max(task=_task("tank_recirc"), runtime=rt) == 0.75

    def test_disabled_returns_base_irrigation(self, mock_dt) -> None:
        mock_dt.now.return_value = datetime(2026, 4, 13, 23, 0)
        h = _handler()
        rt = _runtime(day_night_enabled=False, ec_section={"night": 1.0})
        assert h._effective_ec_target(task=_task("irrigation"), runtime=rt) == 1.6
