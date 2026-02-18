"""Tests for correction_controller."""
import logging
import time
import pytest
from unittest.mock import Mock, AsyncMock, patch
from types import SimpleNamespace
from datetime import datetime, timezone
from correction_controller import CorrectionController, CorrectionType
from correction_command_retry import publish_controller_command_with_retry
from correction_freshness import validate_freshness_or_skip


class _PidZone:
    def __init__(self, value: str):
        self.value = value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _PidZone) and other.value == self.value


class _PidStub:
    def __init__(self, output: float):
        self._zone = _PidZone("close")
        self.config = SimpleNamespace(
            dead_zone=0.0,
            close_zone=0.0,
            far_zone=0.0,
            zone_coeffs={self._zone: SimpleNamespace(kp=1.0, ki=0.0, kd=0.0)},
        )
        self.integral = 0.0
        self.prev_error = 0.0
        self._output = output

    def compute(self, current: float, dt_seconds: float) -> float:
        return self._output

    def get_zone(self):
        return self._zone


def _configure_confirmed_command_bus(command_bus: Mock, cmd_ids: list[str] | None = None) -> None:
    """Configure command bus mock for successful publish+confirmation path."""
    seq = iter(cmd_ids or [])
    publish_count = 0

    async def _publish(zone_id, payload, context):
        nonlocal publish_count
        publish_count += 1
        if cmd_ids is not None:
            payload["cmd_id"] = next(seq)
        else:
            payload["cmd_id"] = payload.get("cmd_id") or f"cmd-test-{publish_count}"
        return True

    command_bus.publish_controller_command = AsyncMock(side_effect=_publish)
    command_bus.tracker = Mock()
    command_bus.tracker.wait_for_command_done = AsyncMock(return_value=True)
    command_bus.tracker.confirm_command_status = AsyncMock(return_value=None)


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_no_target():
    """Test pH controller when target is not set."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {}
    telemetry = {"PH": 6.5}
    nodes = {}
    
    telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
    result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
    assert result is None


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_no_current():
    """Test pH controller when current value is not available."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": {"target": 6.5}}
    telemetry = {}
    nodes = {}
    
    telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
    result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
    assert result is None


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_small_diff():
    """Test pH controller when difference is too small."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": {"target": 6.5}}
    telemetry = {"PH": 6.4}  # diff = 0.1, меньше порога 0.2
    nodes = {}
    
    telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
    result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
    assert result is None


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_cooldown():
    """Test pH controller when in cooldown period."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": {"target": 6.5}}
    telemetry = {"PH": 6.8}  # diff = 0.3, больше порога
    nodes = {
        "irrig:default": {
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "type": "irrig"
        }
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should:
        mock_should.return_value = (False, "В cooldown периоде")
        with patch("correction_controller.create_zone_event") as mock_event:
            telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
            result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
            
            assert result is None
            mock_event.assert_called_once()
            call_args = mock_event.call_args
            assert call_args[0][1] == 'PH_CORRECTION_SKIPPED'


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_low_ph():
    """Test pH controller when pH is too low (add base)."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": {"target": 6.5}}
    telemetry = {"PH": 6.2}  # diff = -0.3, pH слишком низкий
    nodes = {}
    actuators = {
        "ph_base_pump": {
            "node_uid": "nd-ph-1",
            "channel": "pump_base",
            "role": "ph_base_pump"
        }
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(3.0)):
        mock_should.return_value = (True, "Корректировка необходима")

        telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True, actuators=actuators)
        
        assert result is not None
        assert result['cmd'] == 'dose'
        assert result['params']['type'] == 'add_base'
        assert result['params']['ml'] == pytest.approx(3.0, abs=0.01)  # abs(-0.3) * 10
        assert result['event_type'] == 'PH_CORRECTED'
        assert result['event_details']['correction_type'] == 'add_base'


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_high_ph():
    """Test pH controller when pH is too high (add acid)."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": {"target": 6.5}}
    telemetry = {"PH": 6.8}  # diff = 0.3, pH слишком высокий
    nodes = {}
    actuators = {
        "ph_acid_pump": {
            "node_uid": "nd-ph-2",
            "channel": "pump_acid",
            "role": "ph_acid_pump"
        }
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(3.0)):
        mock_should.return_value = (True, "Корректировка необходима")

        telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True, actuators=actuators)
        
        assert result is not None
        assert result['cmd'] == 'dose'
        assert result['params']['type'] == 'add_acid'
        assert result['params']['ml'] == pytest.approx(3.0, abs=0.01)  # abs(0.3) * 10
        assert result['event_type'] == 'PH_CORRECTED'


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_no_water():
    """Test pH controller when water level is low."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": {"target": 6.5}}
    telemetry = {"PH": 6.8}
    nodes = {}
    actuators = {
        "ph_acid_pump": {
            "node_uid": "nd-ph-2",
            "channel": "pump_acid",
            "role": "ph_acid_pump"
        }
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")

        telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=False, actuators=actuators)
        
        assert result is None  # Не должно быть корректировки при низком уровне воды


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_no_nodes():
    """Test pH controller when no irrigation nodes available."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": {"target": 6.5}}
    telemetry = {"PH": 6.8}
    nodes = {}  # Нет узлов
    
    with patch("correction_controller.should_apply_correction") as mock_should:
        mock_should.return_value = (True, "Корректировка необходима")
        
        telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
        
        assert result is None


@pytest.mark.asyncio
async def test_ph_controller_does_not_fallback_to_nodes_without_actuator_bindings():
    """pH correction must not fallback to legacy nodes map without actuator bindings."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": {"target": 6.5}}
    telemetry = {"PH": 6.8}
    nodes = {
        "ph:pump_acid": {
            "node_uid": "nd-ph-legacy",
            "channel": "pump_acid",
            "type": "ph",
        },
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(3.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes=nodes,
            water_level_ok=True,
            actuators={},
        )

    assert result is None


@pytest.mark.asyncio
async def test_ph_controller_skips_when_target_violates_abs_bounds():
    controller = CorrectionController(CorrectionType.PH)
    telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}

    with patch("correction_controller.validate_freshness_or_skip", new_callable=AsyncMock, return_value=True), \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_event:
        result = await controller.check_and_correct(
            zone_id=1,
            targets={"ph": {"target": 7.1}},
            telemetry={"PH": 6.5},
            telemetry_timestamps=telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators={},
            bounds_overrides={"ph": {"abs_min": 5.2, "abs_max": 6.8}},
        )

    assert result is None
    event_types = [call.args[1] for call in mock_event.await_args_list if len(call.args) >= 2]
    assert "PH_CORRECTION_SKIPPED_BOUNDS" in event_types


@pytest.mark.asyncio
async def test_ph_controller_skips_when_hard_pct_is_violated():
    controller = CorrectionController(CorrectionType.PH)
    controller._last_target_by_zone[1] = 6.0
    controller._last_target_ts_by_zone[1] = time.monotonic() - 60.0
    telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}

    with patch("correction_controller.validate_freshness_or_skip", new_callable=AsyncMock, return_value=True), \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_event:
        result = await controller.check_and_correct(
            zone_id=1,
            targets={"ph": {"target": 6.9}},
            telemetry={"PH": 6.5},
            telemetry_timestamps=telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators={},
            bounds_overrides={"ph": {"hard_pct": 10, "abs_min": 5.0, "abs_max": 8.0}},
        )

    assert result is None
    assert any(
        call.args[1] == "PH_CORRECTION_SKIPPED_BOUNDS"
        and call.args[2].get("reason_code") == "target_hard_pct_violation"
        for call in mock_event.await_args_list
        if len(call.args) >= 3
    )


@pytest.mark.asyncio
async def test_ph_controller_clamps_target_by_max_delta_per_min():
    controller = CorrectionController(CorrectionType.PH)
    controller._last_target_by_zone[1] = 6.0
    controller._last_target_ts_by_zone[1] = time.monotonic() - 60.0
    telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
    actuators = {
        "ph_acid_pump": {
            "node_uid": "nd-ph-1",
            "channel": "pump_acid",
            "role": "ph_acid_pump",
        },
    }

    with patch("correction_controller.validate_freshness_or_skip", new_callable=AsyncMock, return_value=True), \
         patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(3.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        result = await controller.check_and_correct(
            zone_id=1,
            targets={"ph": {"target": 6.8}},
            telemetry={"PH": 6.4},
            telemetry_timestamps=telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
            bounds_overrides={"ph": {"hard_pct": 50, "max_delta_per_min": 0.1, "abs_min": 5.0, "abs_max": 8.0}},
        )

    assert result is not None
    assert result["target_value"] == pytest.approx(6.1, abs=0.01)
    assert result["event_details"]["target_rate_limited"] is True
    assert any(
        call.args[1] == "PH_TARGET_CLAMPED_RATE_LIMIT"
        for call in mock_event.await_args_list
        if len(call.args) >= 2
    )


@pytest.mark.asyncio
async def test_ph_controller_kill_switch_disables_safety_bounds():
    controller = CorrectionController(CorrectionType.PH)
    telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
    actuators = {
        "ph_acid_pump": {
            "node_uid": "nd-ph-1",
            "channel": "pump_acid",
            "role": "ph_acid_pump",
        },
    }
    settings = SimpleNamespace(
        AE_SAFETY_BOUNDS_ENABLED=True,
        AE_SAFETY_BOUNDS_KILL_SWITCH=True,
        MAIN_LOOP_SLEEP_SECONDS=15,
    )

    with patch("correction_controller.get_settings", return_value=settings), \
         patch("correction_controller.validate_freshness_or_skip", new_callable=AsyncMock, return_value=True), \
         patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(3.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        result = await controller.check_and_correct(
            zone_id=1,
            targets={"ph": {"target": 7.2}},
            telemetry={"PH": 7.6},
            telemetry_timestamps=telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
            bounds_overrides={"ph": {"abs_min": 5.2, "abs_max": 6.8}},
        )

    assert result is not None
    assert result["event_details"]["safety_bounds_active"] is False


@pytest.mark.asyncio
async def test_ph_controller_proactive_mode_triggers_inside_dead_zone():
    controller = CorrectionController(CorrectionType.PH)
    telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
    pid_stub = _PidStub(3.0)
    pid_stub.config.dead_zone = 0.2
    actuators = {
        "ph_acid_pump": {
            "node_uid": "nd-ph-1",
            "channel": "pump_acid",
            "role": "ph_acid_pump",
        },
    }

    with patch("correction_controller.validate_freshness_or_skip", new_callable=AsyncMock, return_value=True), \
         patch("correction_controller.analyze_proactive_correction_signal", new_callable=AsyncMock) as mock_proactive, \
         patch("correction_controller.should_apply_proactive_correction", new_callable=AsyncMock, return_value=(True, "ok")), \
         patch("correction_controller.should_apply_correction", new_callable=AsyncMock) as mock_regular_policy, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=pid_stub):
        mock_proactive.return_value = {
            "should_correct": True,
            "reason_code": "proactive_predicted_target_escape",
            "predicted_diff": 0.35,
            "predicted_value": 6.85,
            "predicted_deviation": 0.35,
            "slope_per_min": 0.02,
            "horizon_minutes": 20,
            "samples_count": 6,
        }
        result = await controller.check_and_correct(
            zone_id=1,
            targets={"ph": {"target": 6.5}},
            telemetry={"PH": 6.55},
            telemetry_timestamps=telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
        )

    assert result is not None
    assert result["event_details"]["proactive_mode"] is True
    assert result["event_details"]["proactive"]["reason_code"] == "proactive_predicted_target_escape"
    mock_regular_policy.assert_not_awaited()


@pytest.mark.asyncio
async def test_ph_controller_skips_when_anomaly_block_is_active():
    controller = CorrectionController(CorrectionType.PH)
    controller._anomaly_blocked_until_by_zone[1] = time.monotonic() + 120.0
    telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
    actuators = {
        "ph_acid_pump": {
            "node_uid": "nd-ph-1",
            "channel": "pump_acid",
            "role": "ph_acid_pump",
        },
    }

    with patch("correction_controller.validate_freshness_or_skip", new_callable=AsyncMock, return_value=True), \
         patch("correction_controller.should_apply_correction", new_callable=AsyncMock, return_value=(True, "ok")), \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(3.0)):
        result = await controller.check_and_correct(
            zone_id=1,
            targets={"ph": {"target": 6.5}},
            telemetry={"PH": 6.9},
            telemetry_timestamps=telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
        )

    assert result is None
    assert any(
        call.args[1] == "PH_CORRECTION_SKIPPED_ANOMALY"
        for call in mock_event.await_args_list
        if len(call.args) >= 2
    )


@pytest.mark.asyncio
async def test_ph_controller_no_effect_streak_activates_anomaly_block():
    controller = CorrectionController(CorrectionType.PH)
    pid_stub = _PidStub(3.0)
    pid_stub.config.dead_zone = 0.2
    controller._pending_effect_window_by_zone[1] = {
        "baseline_value": 6.50,
        "target_value": 6.40,
        "expected_direction": 1,
        "correction_type": "add_base",
        "window_deadline_at": time.monotonic() - 1.0,
        "window_sec": 180,
        "correlation_id": "corr-test-no-effect",
    }
    telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}
    settings = SimpleNamespace(
        AE_SAFETY_BOUNDS_ENABLED=True,
        AE_SAFETY_BOUNDS_KILL_SWITCH=False,
        AE_PROACTIVE_CORRECTION_ENABLED=False,
        AE_EQUIPMENT_ANOMALY_GUARD_ENABLED=True,
        AE_EQUIPMENT_ANOMALY_NO_EFFECT_WINDOW_SEC=180,
        AE_EQUIPMENT_ANOMALY_STREAK_THRESHOLD=1,
        AE_EQUIPMENT_ANOMALY_BLOCK_MINUTES=15,
        AE_EQUIPMENT_ANOMALY_PH_MIN_DELTA=0.03,
        AE_EQUIPMENT_ANOMALY_EC_MIN_DELTA=0.03,
        AE_SAFETY_PH_HARD_PCT=20.0,
        AE_SAFETY_PH_ABS_MIN=5.2,
        AE_SAFETY_PH_ABS_MAX=6.8,
        AE_SAFETY_PH_MAX_DELTA_PER_MIN=0.2,
    )

    with patch("correction_controller.get_settings", return_value=settings), \
         patch("correction_controller.validate_freshness_or_skip", new_callable=AsyncMock, return_value=True), \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch("correction_controller.send_infra_alert", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=pid_stub):
        result = await controller.check_and_correct(
            zone_id=1,
            targets={"ph": {"target": 6.5}},
            telemetry={"PH": 6.49},
            telemetry_timestamps=telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators={},
        )

    assert result is None
    assert 1 in controller._anomaly_blocked_until_by_zone
    event_types = [call.args[1] for call in mock_event.await_args_list if len(call.args) >= 2]
    assert "PH_DOSE_NO_EFFECT" in event_types
    assert "PH_DOSING_BLOCKED_ANOMALY" in event_types


@pytest.mark.asyncio
async def test_ec_controller_check_and_correct_low_ec():
    """Test EC controller when EC is too low (add nutrients)."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 1.8},
        "nutrition": {
            "mode": "ratio_ec_pid",
            "components": {
                "npk": {"ratio_pct": 50},
                "calcium": {"ratio_pct": 20},
                "magnesium": {"ratio_pct": 20},
                "micro": {"ratio_pct": 10},
            },
        },
    }
    telemetry = {"EC": 1.5}  # diff = -0.3, EC слишком низкий
    nodes = {}
    actuators = {
        "ec_npk_pump": {"node_uid": "nd-ec-a", "channel": "pump_a", "role": "ec_npk_pump", "ml_per_sec": 1.2},
        "ec_calcium_pump": {"node_uid": "nd-ec-b", "channel": "pump_b", "role": "ec_calcium_pump", "ml_per_sec": 1.1},
        "ec_magnesium_pump": {"node_uid": "nd-ec-c", "channel": "pump_c", "role": "ec_magnesium_pump", "ml_per_sec": 1.0},
        "ec_micro_pump": {"node_uid": "nd-ec-d", "channel": "pump_d", "role": "ec_micro_pump", "ml_per_sec": 0.9},
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True, actuators=actuators)
        
        assert result is not None
        assert result['cmd'] == 'run_pump'
        assert result['params']['type'] == 'add_nutrients'
        assert result['params']['ml'] == pytest.approx(30.0, abs=0.01)  # abs(-0.3) * 100
        assert result['params']['duration_ms'] > 0
        assert len(result.get("batch_commands", [])) == 4
        doses = {item["component"]: item["ml"] for item in result["batch_commands"]}
        assert doses["npk"] == pytest.approx(15.0, abs=0.01)
        assert doses["calcium"] == pytest.approx(6.0, abs=0.01)
        assert doses["magnesium"] == pytest.approx(6.0, abs=0.01)
        assert doses["micro"] == pytest.approx(3.0, abs=0.01)
        assert result['event_type'] == 'EC_DOSING'


@pytest.mark.asyncio
async def test_ec_controller_check_and_correct_filters_components_to_npk_only():
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 1.8},
        "nutrition": {
            "mode": "ratio_ec_pid",
            "components": {
                "npk": {"ratio_pct": 50},
                "calcium": {"ratio_pct": 20},
                "magnesium": {"ratio_pct": 20},
                "micro": {"ratio_pct": 10},
            },
        },
    }
    telemetry = {"EC": 1.5}
    actuators = {
        "ec_npk_pump": {"node_uid": "nd-ec-a", "channel": "pump_a", "role": "ec_npk_pump", "ml_per_sec": 1.2},
        "ec_calcium_pump": {"node_uid": "nd-ec-b", "channel": "pump_b", "role": "ec_calcium_pump", "ml_per_sec": 1.1},
        "ec_magnesium_pump": {"node_uid": "nd-ec-c", "channel": "pump_c", "role": "ec_magnesium_pump", "ml_per_sec": 1.0},
        "ec_micro_pump": {"node_uid": "nd-ec-d", "channel": "pump_d", "role": "ec_micro_pump", "ml_per_sec": 0.9},
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
            allowed_ec_components=["npk"],
        )

    assert result is not None
    components = [item["component"] for item in result["batch_commands"]]
    assert components == ["npk"]


@pytest.mark.asyncio
async def test_ec_controller_check_and_correct_filters_components_to_calmgmicro():
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 1.8},
        "nutrition": {
            "mode": "ratio_ec_pid",
            "components": {
                "npk": {"ratio_pct": 50},
                "calcium": {"ratio_pct": 20},
                "magnesium": {"ratio_pct": 20},
                "micro": {"ratio_pct": 10},
            },
        },
    }
    telemetry = {"EC": 1.5}
    actuators = {
        "ec_npk_pump": {"node_uid": "nd-ec-a", "channel": "pump_a", "role": "ec_npk_pump", "ml_per_sec": 1.2},
        "ec_calcium_pump": {"node_uid": "nd-ec-b", "channel": "pump_b", "role": "ec_calcium_pump", "ml_per_sec": 1.1},
        "ec_magnesium_pump": {"node_uid": "nd-ec-c", "channel": "pump_c", "role": "ec_magnesium_pump", "ml_per_sec": 1.0},
        "ec_micro_pump": {"node_uid": "nd-ec-d", "channel": "pump_d", "role": "ec_micro_pump", "ml_per_sec": 0.9},
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
            allowed_ec_components=["calcium", "magnesium", "micro"],
        )

    assert result is not None
    components = [item["component"] for item in result["batch_commands"]]
    assert components == ["calcium", "magnesium", "micro"]


@pytest.mark.asyncio
async def test_ec_controller_check_and_correct_high_ec():
    """Test EC controller when EC is too high (dilute)."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {"ec": {"target": 1.8}}
    telemetry = {"EC": 2.1}  # diff = 0.3, EC слишком высокий
    nodes = {}
    actuators = {
        "ec_npk_pump": {
            "node_uid": "nd-ec-1",
            "channel": "pump_a",
            "role": "ec_npk_pump"
        }
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should:
        mock_should.return_value = (True, "Корректировка необходима")
        
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True, actuators=actuators)
        
        # Для dilute актюатор не выбирается, команда не отправляется
        assert result is None


@pytest.mark.asyncio
async def test_ec_controller_requires_all_four_component_pumps():
    """EC correction should be skipped when at least one component pump is missing."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 2.0},
        "nutrition": {
            "mode": "ratio_ec_pid",
            "components": {
                "npk": {"ratio_pct": 50},
                "calcium": {"ratio_pct": 30},
                "magnesium": {"ratio_pct": 10},
                "micro": {"ratio_pct": 20},
            },
        },
    }
    telemetry = {"EC": 1.6}
    actuators = {
        "ec_npk_pump": {"node_uid": "nd-ec-a", "channel": "pump_a", "role": "ec_npk_pump"},
        "ec_calcium_pump": {"node_uid": "nd-ec-b", "channel": "pump_b", "role": "ec_calcium_pump"},
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
        )

    assert result is None


@pytest.mark.asyncio
async def test_ec_controller_rejects_duplicate_physical_pumps_for_different_components():
    """EC correction should be skipped if two nutrient roles point to the same physical pump."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 2.0},
        "nutrition": {
            "mode": "ratio_ec_pid",
            "components": {
                "npk": {"ratio_pct": 50},
                "calcium": {"ratio_pct": 30},
                "magnesium": {"ratio_pct": 10},
                "micro": {"ratio_pct": 10},
            },
        },
    }
    telemetry = {"EC": 1.6}
    actuators = {
        "ec_npk_pump": {"node_uid": "nd-ec-a", "channel": "pump_a", "role": "ec_npk_pump"},
        "ec_calcium_pump": {"node_uid": "nd-ec-b", "channel": "pump_b", "role": "ec_calcium_pump"},
        "ec_magnesium_pump": {"node_uid": "nd-ec-c", "channel": "pump_c", "role": "ec_magnesium_pump"},
        "ec_micro_pump": {"node_uid": "nd-ec-c", "channel": "pump_c", "role": "ec_micro_pump"},
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
        )

    assert result is None
    skip_events = [call[0][1] for call in mock_event.await_args_list if len(call[0]) >= 2]
    assert "EC_CORRECTION_SKIPPED" in skip_events


@pytest.mark.asyncio
async def test_ec_controller_splits_dose_for_four_component_feeding():
    """EC correction should be split across NPK/Ca/Mg/Micro pumps."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 2.0},
        "nutrition": {
            "mode": "ratio_ec_pid",
            "program_code": "YARAREGA_4PART_V1",
            "components": {
                "npk": {"ratio_pct": 50},
                "calcium": {"ratio_pct": 20},
                "magnesium": {"ratio_pct": 20},
                "micro": {"ratio_pct": 10},
            },
        },
    }
    telemetry = {"EC": 1.6}  # diff = -0.4
    nodes = {}
    actuators = {
        "ec_npk_pump": {
            "node_uid": "nd-ec-a",
            "channel": "pump_a",
            "role": "ec_npk_pump",
            "ml_per_sec": 1.2,
        },
        "ec_calcium_pump": {
            "node_uid": "nd-ec-b",
            "channel": "pump_b",
            "role": "ec_calcium_pump",
            "ml_per_sec": 1.1,
        },
        "ec_magnesium_pump": {
            "node_uid": "nd-ec-c",
            "channel": "pump_c",
            "role": "ec_magnesium_pump",
            "ml_per_sec": 1.0,
        },
        "ec_micro_pump": {
            "node_uid": "nd-ec-d",
            "channel": "pump_d",
            "role": "ec_micro_pump",
            "ml_per_sec": 0.9,
        },
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")

        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes=nodes,
            water_level_ok=True,
            actuators=actuators,
        )

        assert result is not None
        assert "batch_commands" in result
        assert len(result["batch_commands"]) == 4
        doses = {item["component"]: item["ml"] for item in result["batch_commands"]}
        assert doses["npk"] == pytest.approx(15.0, abs=0.01)
        assert doses["calcium"] == pytest.approx(6.0, abs=0.01)
        assert doses["magnesium"] == pytest.approx(6.0, abs=0.01)
        assert doses["micro"] == pytest.approx(3.0, abs=0.01)


@pytest.mark.asyncio
async def test_ec_controller_delta_ec_by_k_mode_uses_solution_volume():
    """delta_ec_by_k mode should compute ml from ΔEC, k and solution volume."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 2.0},
        "nutrition": {
            "mode": "delta_ec_by_k",
            "solution_volume_l": 100,
            "components": {
                "npk": {"ratio_pct": 50, "k_ms_per_ml_l": 0.8},
                "calcium": {"ratio_pct": 20, "k_ms_per_ml_l": 0.6},
                "magnesium": {"ratio_pct": 20, "k_ms_per_ml_l": 0.4},
                "micro": {"ratio_pct": 10, "k_ms_per_ml_l": 0.2},
            },
        },
    }
    telemetry = {"EC": 1.6}
    actuators = {
        "ec_npk_pump": {"node_uid": "nd-ec-a", "channel": "pump_a", "role": "ec_npk_pump", "ml_per_sec": 1.2},
        "ec_calcium_pump": {"node_uid": "nd-ec-b", "channel": "pump_b", "role": "ec_calcium_pump", "ml_per_sec": 1.1},
        "ec_magnesium_pump": {"node_uid": "nd-ec-c", "channel": "pump_c", "role": "ec_magnesium_pump", "ml_per_sec": 1.0},
        "ec_micro_pump": {"node_uid": "nd-ec-d", "channel": "pump_d", "role": "ec_micro_pump", "ml_per_sec": 0.9},
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
        )

    assert result is not None
    doses = {item["component"]: item["ml"] for item in result["batch_commands"]}
    assert doses["npk"] == pytest.approx(25.0, abs=0.01)
    assert doses["calcium"] == pytest.approx(13.333, abs=0.01)
    assert doses["magnesium"] == pytest.approx(20.0, abs=0.01)
    assert doses["micro"] == pytest.approx(20.0, abs=0.01)


@pytest.mark.asyncio
async def test_ec_controller_ratio_mode_with_k_weighting():
    """ratio_ec_pid mode should compensate doses by inverse k when k is available."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 2.0},
        "nutrition": {
            "mode": "ratio_ec_pid",
            "components": {
                "npk": {"ratio_pct": 25},
                "calcium": {"ratio_pct": 25},
                "magnesium": {"ratio_pct": 25},
                "micro": {"ratio_pct": 25},
            },
        },
    }
    telemetry = {"EC": 1.6}
    actuators = {
        "ec_npk_pump": {"node_uid": "nd-ec-a", "channel": "pump_a", "role": "ec_npk_pump", "k_ms_per_ml_l": 1.0, "ml_per_sec": 1.2},
        "ec_calcium_pump": {"node_uid": "nd-ec-b", "channel": "pump_b", "role": "ec_calcium_pump", "k_ms_per_ml_l": 0.5, "ml_per_sec": 1.1},
        "ec_magnesium_pump": {"node_uid": "nd-ec-c", "channel": "pump_c", "role": "ec_magnesium_pump", "k_ms_per_ml_l": 0.25, "ml_per_sec": 1.0},
        "ec_micro_pump": {"node_uid": "nd-ec-d", "channel": "pump_d", "role": "ec_micro_pump", "k_ms_per_ml_l": 0.125, "ml_per_sec": 0.9},
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
        )

    assert result is not None
    doses = {item["component"]: item["ml"] for item in result["batch_commands"]}
    assert doses["npk"] == pytest.approx(2.0, abs=0.01)
    assert doses["calcium"] == pytest.approx(4.0, abs=0.01)
    assert doses["magnesium"] == pytest.approx(8.0, abs=0.01)
    assert doses["micro"] == pytest.approx(16.0, abs=0.01)


@pytest.mark.asyncio
async def test_ec_controller_delta_ec_by_k_mode_requires_full_k_profile():
    """delta_ec_by_k mode should be skipped when one of k values is missing."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 2.0},
        "nutrition": {
            "mode": "delta_ec_by_k",
            "solution_volume_l": 100,
            "components": {
                "npk": {"ratio_pct": 40, "k_ms_per_ml_l": 0.8},
                "calcium": {"ratio_pct": 30, "k_ms_per_ml_l": 0.6},
                "magnesium": {"ratio_pct": 20},
                "micro": {"ratio_pct": 10, "k_ms_per_ml_l": 0.2},
            },
        },
    }
    telemetry = {"EC": 1.6}
    actuators = {
        "ec_npk_pump": {"node_uid": "nd-ec-a", "channel": "pump_a", "role": "ec_npk_pump"},
        "ec_calcium_pump": {"node_uid": "nd-ec-b", "channel": "pump_b", "role": "ec_calcium_pump"},
        "ec_magnesium_pump": {"node_uid": "nd-ec-c", "channel": "pump_c", "role": "ec_magnesium_pump"},
        "ec_micro_pump": {"node_uid": "nd-ec-d", "channel": "pump_d", "role": "ec_micro_pump"},
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
        )

    assert result is None


@pytest.mark.asyncio
async def test_ec_controller_invalid_nutrition_mode_is_skipped():
    """Unknown nutrition.mode must be fail-closed (no legacy fallback)."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 2.0},
        "nutrition": {
            "mode": "legacy_ratio",
            "components": {
                "npk": {"ratio_pct": 44},
                "calcium": {"ratio_pct": 36},
                "magnesium": {"ratio_pct": 17},
                "micro": {"ratio_pct": 3},
            },
        },
    }
    telemetry = {"EC": 1.6}
    actuators = {
        "ec_npk_pump": {"node_uid": "nd-ec-a", "channel": "pump_a", "role": "ec_npk_pump"},
        "ec_calcium_pump": {"node_uid": "nd-ec-b", "channel": "pump_b", "role": "ec_calcium_pump"},
        "ec_magnesium_pump": {"node_uid": "nd-ec-c", "channel": "pump_c", "role": "ec_magnesium_pump"},
        "ec_micro_pump": {"node_uid": "nd-ec-d", "channel": "pump_d", "role": "ec_micro_pump"},
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
        )

    assert result is None


@pytest.mark.asyncio
async def test_ec_controller_ratio_mode_requires_valid_ml_per_sec_for_each_pump():
    """EC batch must fail-closed when at least one component pump has invalid ml_per_sec."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 2.0},
        "nutrition": {
            "mode": "ratio_ec_pid",
            "components": {
                "npk": {"ratio_pct": 44},
                "calcium": {"ratio_pct": 36},
                "magnesium": {"ratio_pct": 17},
                "micro": {"ratio_pct": 3},
            },
        },
    }
    telemetry = {"EC": 1.6}
    actuators = {
        "ec_npk_pump": {"node_uid": "nd-ec-a", "channel": "pump_a", "role": "ec_npk_pump", "ml_per_sec": 1.2},
        "ec_calcium_pump": {"node_uid": "nd-ec-b", "channel": "pump_b", "role": "ec_calcium_pump", "ml_per_sec": 1.1},
        "ec_magnesium_pump": {"node_uid": "nd-ec-c", "channel": "pump_c", "role": "ec_magnesium_pump", "ml_per_sec": 0.0},
        "ec_micro_pump": {"node_uid": "nd-ec-d", "channel": "pump_d", "role": "ec_micro_pump", "ml_per_sec": 1.0},
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
        )

    assert result is None


@pytest.mark.asyncio
async def test_ec_controller_dose_ml_l_only_requires_all_component_doses():
    """dose_ml_l_only must skip if any component dose is missing/non-positive."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {
        "ec": {"target": 2.0},
        "nutrition": {
            "mode": "dose_ml_l_only",
            "solution_volume_l": 100,
            "components": {
                "npk": {"ratio_pct": 44, "dose_ml_per_l": 1.7},
                "calcium": {"ratio_pct": 36, "dose_ml_per_l": 1.2},
                "magnesium": {"ratio_pct": 17},
                "micro": {"ratio_pct": 3, "dose_ml_per_l": 0.2},
            },
        },
    }
    telemetry = {"EC": 1.6}
    actuators = {
        "ec_npk_pump": {"node_uid": "nd-ec-a", "channel": "pump_a", "role": "ec_npk_pump"},
        "ec_calcium_pump": {"node_uid": "nd-ec-b", "channel": "pump_b", "role": "ec_calcium_pump"},
        "ec_magnesium_pump": {"node_uid": "nd-ec-c", "channel": "pump_c", "role": "ec_magnesium_pump"},
        "ec_micro_pump": {"node_uid": "nd-ec-d", "channel": "pump_d", "role": "ec_micro_pump"},
    }

    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(30.0)):
        mock_should.return_value = (True, "Корректировка необходима")
        telemetry_ts = {"EC": datetime.now(timezone.utc).replace(tzinfo=None)}
        result = await controller.check_and_correct(
            1,
            targets,
            telemetry,
            telemetry_ts,
            nodes={},
            water_level_ok=True,
            actuators=actuators,
        )

    assert result is None


@pytest.mark.asyncio
async def test_apply_correction_publishes_all_batch_commands():
    """Batch correction should publish each component command."""
    controller = CorrectionController(CorrectionType.EC)
    command = {
        "node_uid": "nd-ec-a",
        "channel": "pump_a",
        "cmd": "run_pump",
        "params": {"type": "add_nutrients", "ml": 10.0, "duration_ms": 1000},
        "event_type": "EC_DOSING",
        "event_details": {
            "correction_type": "add_nutrients",
            "current_ec": 1.6,
            "target_ec": 2.0,
            "diff": -0.4,
            "ml": 30.0,
        },
        "zone_id": 1,
        "correction_type_str": "ec",
        "current_value": 1.6,
        "target_value": 2.0,
        "reason": "Корректировка необходима",
        "batch_commands": [
            {
                "node_uid": "nd-ec-a",
                "channel": "pump_a",
                "cmd": "run_pump",
                "params": {"type": "add_nutrients", "component": "npk", "ml": 15.0, "duration_ms": 1500},
            },
            {
                "node_uid": "nd-ec-b",
                "channel": "pump_b",
                "cmd": "run_pump",
                "params": {"type": "add_nutrients", "component": "calcium", "ml": 9.0, "duration_ms": 900},
            },
            {
                "node_uid": "nd-ec-c",
                "channel": "pump_c",
                "cmd": "run_pump",
                "params": {"type": "add_nutrients", "component": "micro", "ml": 6.0, "duration_ms": 600},
            },
        ],
    }

    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    _configure_confirmed_command_bus(command_bus)

    with patch("correction_controller.record_correction"), \
         patch("correction_controller.create_zone_event"), \
         patch("correction_controller.create_ai_log"), \
         patch("correction_controller.fetch", new_callable=AsyncMock, return_value=[]):
        await controller.apply_correction(command, command_bus)

    assert command_bus.publish_controller_command.await_count == 3


@pytest.mark.asyncio
async def test_apply_correction_stops_batch_when_ec_target_reached():
    """Batch EC dosing should stop early after recheck if target reached."""
    controller = CorrectionController(CorrectionType.EC)
    command = {
        "zone_id": 1,
        "correction_type_str": "ec",
        "current_value": 1.6,
        "target_value": 2.0,
        "reason": "Корректировка необходима",
        "event_type": "EC_DOSING",
        "event_details": {"diff": -0.4, "correction_type": "add_nutrients", "ml": 30.0},
        "nutrition_control": {"dose_delay_sec": 0.0, "ec_stop_tolerance": 0.05},
        "batch_commands": [
            {"node_uid": "nd-ec-a", "channel": "pump_a", "cmd": "run_pump", "params": {"ml": 15.0}, "component": "npk"},
            {"node_uid": "nd-ec-b", "channel": "pump_b", "cmd": "run_pump", "params": {"ml": 9.0}, "component": "calcium"},
            {"node_uid": "nd-ec-c", "channel": "pump_c", "cmd": "run_pump", "params": {"ml": 6.0}, "component": "micro"},
        ],
    }

    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    _configure_confirmed_command_bus(command_bus)

    ec_after_first_dose = [{"last_value": 1.98}]
    with patch("correction_controller.record_correction"), \
         patch("correction_controller.create_zone_event"), \
         patch("correction_controller.create_ai_log"), \
         patch("correction_controller.fetch", new_callable=AsyncMock, return_value=ec_after_first_dose):
        await controller.apply_correction(command, command_bus)

    assert command_bus.publish_controller_command.await_count == 1


@pytest.mark.asyncio
async def test_apply_correction_waits_between_component_doses_and_rechecks_ec():
    """Batch EC dosing should wait between doses and recheck EC after each component."""
    controller = CorrectionController(CorrectionType.EC)
    command = {
        "zone_id": 1,
        "correction_type_str": "ec",
        "current_value": 1.6,
        "target_value": 2.0,
        "reason": "Корректировка необходима",
        "event_type": "EC_DOSING",
        "event_details": {"diff": -0.4, "correction_type": "add_nutrients", "ml": 30.0},
        "nutrition_control": {"dose_delay_sec": 2.5, "ec_stop_tolerance": 0.05},
        "batch_commands": [
            {"node_uid": "nd-ec-a", "channel": "pump_a", "cmd": "run_pump", "params": {"ml": 15.0}, "component": "npk"},
            {"node_uid": "nd-ec-b", "channel": "pump_b", "cmd": "run_pump", "params": {"ml": 9.0}, "component": "calcium"},
            {"node_uid": "nd-ec-c", "channel": "pump_c", "cmd": "run_pump", "params": {"ml": 6.0}, "component": "micro"},
        ],
    }

    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    _configure_confirmed_command_bus(command_bus)

    with patch("correction_controller.record_correction"), \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_zone_event, \
         patch("correction_controller.create_ai_log"), \
         patch("correction_controller.fetch", new_callable=AsyncMock, side_effect=[[{"last_value": 1.70}], [{"last_value": 1.82}]]), \
         patch("correction_controller.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await controller.apply_correction(command, command_bus)

    assert command_bus.publish_controller_command.await_count == 3
    assert mock_sleep.await_count == 2
    assert [args[0][0] for args in mock_sleep.await_args_list] == [2.5, 2.5]
    recheck_events = [args[0][1] for args in mock_zone_event.await_args_list if len(args[0]) >= 2]
    assert recheck_events.count("EC_COMPONENT_RECHECK") == 2


@pytest.mark.asyncio
async def test_apply_correction_batch_aborts_when_command_unconfirmed_after_retries():
    """Batch should stop fully when one component command is not confirmed after retries."""
    controller = CorrectionController(CorrectionType.EC)
    command = {
        "zone_id": 1,
        "correction_type_str": "ec",
        "current_value": 1.6,
        "target_value": 2.0,
        "reason": "Корректировка необходима",
        "event_type": "EC_DOSING",
        "event_details": {"diff": -0.4, "correction_type": "add_nutrients", "ml": 30.0},
        "batch_commands": [
            {"node_uid": "nd-ec-a", "channel": "pump_a", "cmd": "run_pump", "params": {"ml": 15.0}, "component": "npk"},
            {"node_uid": "nd-ec-b", "channel": "pump_b", "cmd": "run_pump", "params": {"ml": 9.0}, "component": "calcium"},
        ],
    }

    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    cmd_seq = iter(["cmd-1", "cmd-2", "cmd-3"])

    async def _publish(*args, **kwargs):
        payload = args[1]
        payload["cmd_id"] = next(cmd_seq)
        return True

    command_bus.publish_controller_command = AsyncMock(side_effect=_publish)
    command_bus.tracker = Mock()
    command_bus.tracker.wait_for_command_done = AsyncMock(side_effect=[None, None])
    command_bus.tracker.confirm_command_status = AsyncMock(return_value=None)

    with patch("correction_controller.record_correction", new_callable=AsyncMock) as mock_record, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_zone_event, \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch("correction_controller.enqueue_internal_scheduler_task", new_callable=AsyncMock, return_value={"enqueue_id": "enq-ec-recovery", "task_type": "diagnostics", "correlation_id": "corr-ec-recovery"}) as mock_enqueue, \
         patch("correction_controller.send_infra_alert", new_callable=AsyncMock), \
         patch("correction_controller.fetch", new_callable=AsyncMock, return_value=[]):
        await controller.apply_correction(command, command_bus)

    assert command_bus.publish_controller_command.await_count == 2
    mock_enqueue.assert_awaited_once()
    command_bus.tracker.confirm_command_status.assert_awaited()
    assert mock_record.await_count == 0
    events = [call.args[1] for call in mock_zone_event.await_args_list if len(call.args) >= 2]
    assert "EC_COMPONENT_BATCH_ABORTED" in events
    assert "EC_BATCH_PARTIAL_FAILURE" in events


@pytest.mark.asyncio
async def test_apply_correction_single_command_aborts_when_unconfirmed_after_retries():
    """Single pH correction command should abort when not confirmed after retries."""
    controller = CorrectionController(CorrectionType.PH)
    command = {
        'node_uid': 'nd-ph-1',
        'channel': 'pump_acid',
        'cmd': 'dose',
        'params': {'ml': 3.0, 'type': 'add_acid'},
        'event_type': 'PH_CORRECTED',
        'event_details': {
            'correction_type': 'add_acid',
            'current_ph': 6.8,
            'target_ph': 6.5,
            'diff': 0.3,
            'ml': 3.0
        },
        'zone_id': 1,
        'correction_type_str': 'ph',
        'current_value': 6.8,
        'target_value': 6.5,
        'reason': 'Корректировка необходима'
    }

    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    cmd_seq = iter(["cmd-ph-1", "cmd-ph-2", "cmd-ph-3"])

    async def _publish(*args, **kwargs):
        payload = args[1]
        payload["cmd_id"] = next(cmd_seq)
        return True

    command_bus.publish_controller_command = AsyncMock(side_effect=_publish)
    command_bus.tracker = Mock()
    command_bus.tracker.wait_for_command_done = AsyncMock(side_effect=[None, None])
    command_bus.tracker.confirm_command_status = AsyncMock(return_value=None)

    with patch("correction_controller.record_correction", new_callable=AsyncMock) as mock_record, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_zone_event, \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch("correction_controller.send_infra_alert", new_callable=AsyncMock), \
         patch("correction_controller.fetch", new_callable=AsyncMock, return_value=[]):
        await controller.apply_correction(command, command_bus)

    assert command_bus.publish_controller_command.await_count == 2
    command_bus.tracker.confirm_command_status.assert_awaited()
    assert mock_record.await_count == 0
    events = [call.args[1] for call in mock_zone_event.await_args_list if len(call.args) >= 2]
    assert "CORRECTION_ABORTED_COMMAND_FAILURE" in events


@pytest.mark.asyncio
async def test_apply_correction_single_command_fails_closed_when_tracker_active_but_cmd_id_missing():
    controller = CorrectionController(CorrectionType.PH)
    command = {
        'node_uid': 'nd-ph-1',
        'channel': 'pump_acid',
        'cmd': 'dose',
        'params': {'ml': 3.0, 'type': 'add_acid'},
        'event_type': 'PH_CORRECTED',
        'event_details': {
            'correction_type': 'add_acid',
            'current_ph': 6.8,
            'target_ph': 6.5,
            'diff': 0.3,
            'ml': 3.0
        },
        'zone_id': 1,
        'correction_type_str': 'ph',
        'current_value': 6.8,
        'target_value': 6.5,
        'reason': 'Корректировка необходима'
    }

    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    command_bus.tracker = Mock()
    command_bus.tracker.wait_for_command_done = AsyncMock(return_value=True)
    command_bus.tracker.confirm_command_status = AsyncMock(return_value=None)

    with patch("correction_controller.record_correction", new_callable=AsyncMock) as mock_record, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_zone_event, \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch("correction_controller.send_infra_alert", new_callable=AsyncMock), \
         patch("correction_controller.fetch", new_callable=AsyncMock, return_value=[]):
        await controller.apply_correction(command, command_bus)

    assert command_bus.publish_controller_command.await_count >= 1
    command_bus.tracker.wait_for_command_done.assert_not_awaited()
    assert mock_record.await_count == 0
    events = [call.args[1] for call in mock_zone_event.await_args_list if len(call.args) >= 2]
    assert "CORRECTION_ABORTED_COMMAND_FAILURE" in events


@pytest.mark.asyncio
async def test_apply_correction_enriches_single_command_events_with_correlation_and_cmd_id():
    controller = CorrectionController(CorrectionType.PH)
    command = {
        'node_uid': 'nd-ph-1',
        'channel': 'pump_acid',
        'cmd': 'dose',
        'params': {'ml': 3.0, 'type': 'add_acid'},
        'event_type': 'PH_CORRECTED',
        'event_details': {
            'correction_type': 'add_acid',
            'current_ph': 6.8,
            'target_ph': 6.5,
            'diff': 0.3,
            'ml': 3.0,
        },
        'zone_id': 1,
        'correction_type_str': 'ph',
        'current_value': 6.8,
        'target_value': 6.5,
        'reason': 'Корректировка необходима',
    }

    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    _configure_confirmed_command_bus(command_bus, ["cmd-ph-success-1"])

    with patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_zone_event, \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch("correction_controller.fetch", new_callable=AsyncMock, return_value=[]):
        await controller.apply_correction(command, command_bus)

    primary_payload = None
    dosing_payload = None
    for call in mock_zone_event.await_args_list:
        if len(call.args) < 3:
            continue
        event_type = call.args[1]
        payload = call.args[2]
        if event_type == "PH_CORRECTED":
            primary_payload = payload
        if event_type == "DOSING":
            dosing_payload = payload

    assert isinstance(primary_payload, dict)
    assert isinstance(dosing_payload, dict)
    assert primary_payload["cmd_id"] == "cmd-ph-success-1"
    assert primary_payload["cmd_ids"] == ["cmd-ph-success-1"]
    assert isinstance(primary_payload.get("correlation_id"), str) and primary_payload["correlation_id"]
    assert dosing_payload["cmd_id"] == "cmd-ph-success-1"
    assert dosing_payload["cmd_ids"] == ["cmd-ph-success-1"]
    assert dosing_payload["correlation_id"] == primary_payload["correlation_id"]


@pytest.mark.asyncio
async def test_apply_correction_enriches_batch_events_with_cmd_ids_and_correlation():
    controller = CorrectionController(CorrectionType.EC)
    command = {
        "zone_id": 1,
        "correction_type_str": "ec",
        "current_value": 1.6,
        "target_value": 2.0,
        "reason": "Корректировка необходима",
        "event_type": "EC_DOSING",
        "event_details": {"diff": -0.4, "correction_type": "add_nutrients", "ml": 30.0},
        "nutrition_control": {"dose_delay_sec": 0.0, "ec_stop_tolerance": 0.05},
        "batch_commands": [
            {"node_uid": "nd-ec-a", "channel": "pump_a", "cmd": "run_pump", "params": {"ml": 15.0}, "component": "npk"},
            {"node_uid": "nd-ec-b", "channel": "pump_b", "cmd": "run_pump", "params": {"ml": 9.0}, "component": "calcium"},
        ],
    }

    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    _configure_confirmed_command_bus(command_bus, ["cmd-ec-success-1", "cmd-ec-success-2"])

    with patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock) as mock_zone_event, \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock), \
         patch("correction_controller.fetch", new_callable=AsyncMock, return_value=[]):
        await controller.apply_correction(command, command_bus)

    primary_payload = None
    dosing_payload = None
    for call in mock_zone_event.await_args_list:
        if len(call.args) < 3:
            continue
        event_type = call.args[1]
        payload = call.args[2]
        if event_type == "EC_DOSING":
            primary_payload = payload
        if event_type == "DOSING":
            dosing_payload = payload

    assert isinstance(primary_payload, dict)
    assert isinstance(dosing_payload, dict)
    assert primary_payload["cmd_id"] == "cmd-ec-success-2"
    assert primary_payload["cmd_ids"] == ["cmd-ec-success-1", "cmd-ec-success-2"]
    assert isinstance(primary_payload.get("correlation_id"), str) and primary_payload["correlation_id"]
    assert dosing_payload["cmd_id"] == "cmd-ec-success-2"
    assert dosing_payload["cmd_ids"] == ["cmd-ec-success-1", "cmd-ec-success-2"]
    assert dosing_payload["correlation_id"] == primary_payload["correlation_id"]


@pytest.mark.asyncio
async def test_ph_controller_apply_correction():
    """Test applying pH correction (sending command and creating events)."""
    controller = CorrectionController(CorrectionType.PH)
    mqtt = Mock()
    gh_uid = "gh-1"
    
    command = {
        'node_uid': 'nd-ph-1',
        'channel': 'pump_acid',
        'cmd': 'dose',
        'params': {'ml': 3.0, 'type': 'add_acid'},
        'event_type': 'PH_CORRECTED',
        'event_details': {
            'correction_type': 'add_acid',
            'current_ph': 6.8,
            'target_ph': 6.5,
            'diff': 0.3,
            'ml': 3.0
        },
        'zone_id': 1,
        'correction_type_str': 'ph',
        'current_value': 6.8,
        'target_value': 6.5,
        'reason': 'Корректировка необходима'
    }
    
    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    _configure_confirmed_command_bus(command_bus)
    
    with patch("correction_controller.record_correction") as mock_record, \
         patch("correction_controller.create_zone_event") as mock_event, \
         patch("correction_controller.create_ai_log") as mock_ai_log:
        
        await controller.apply_correction(command, command_bus)
        
        # Проверяем, что команда была отправлена
        command_bus.publish_controller_command.assert_called_once()
        
        # Проверяем, что было записано в cooldown
        mock_record.assert_called_once()
        
        # Проверяем, что были созданы события
        assert mock_event.call_count >= 2  # PH_CORRECTED, DOSING
        
        # Проверяем, что был создан AI log
        mock_ai_log.assert_called_once()


@pytest.mark.asyncio
async def test_ph_controller_apply_correction_high_ph_detected():
    """Test that PH_TOO_HIGH_DETECTED event is created for high pH."""
    controller = CorrectionController(CorrectionType.PH)
    mqtt = Mock()
    gh_uid = "gh-1"
    
    command = {
        'node_uid': 'nd-ph-1',
        'channel': 'pump_acid',
        'cmd': 'dose',
        'params': {'ml': 4.0, 'type': 'add_acid'},
        'event_type': 'PH_CORRECTED',
        'event_details': {
            'correction_type': 'add_acid',
            'current_ph': 6.9,
            'target_ph': 6.5,
            'diff': 0.4,  # > 0.3, должно создать PH_TOO_HIGH_DETECTED
            'ml': 4.0
        },
        'zone_id': 1,
        'correction_type_str': 'ph',
        'current_value': 6.9,
        'target_value': 6.5,
        'reason': 'Корректировка необходима'
    }
    
    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    _configure_confirmed_command_bus(command_bus)
    
    with patch("correction_controller.record_correction"), \
         patch("correction_controller.create_zone_event") as mock_event, \
         patch("correction_controller.create_ai_log"):
        
        await controller.apply_correction(command, command_bus)
        
        # Проверяем, что было создано событие PH_TOO_HIGH_DETECTED
        event_calls = [call[0][1] for call in mock_event.call_args_list]
        assert 'PH_TOO_HIGH_DETECTED' in event_calls


@pytest.mark.asyncio
async def test_ph_controller_apply_correction_low_ph_detected():
    """Test that PH_TOO_LOW_DETECTED event is created for low pH."""
    controller = CorrectionController(CorrectionType.PH)
    mqtt = Mock()
    gh_uid = "gh-1"
    
    command = {
        'node_uid': 'nd-ph-1',
        'channel': 'pump_base',
        'cmd': 'dose',
        'params': {'ml': 4.0, 'type': 'add_base'},
        'event_type': 'PH_CORRECTED',
        'event_details': {
            'correction_type': 'add_base',
            'current_ph': 6.1,
            'target_ph': 6.5,
            'diff': -0.4,  # < -0.3, должно создать PH_TOO_LOW_DETECTED
            'ml': 4.0
        },
        'zone_id': 1,
        'correction_type_str': 'ph',
        'current_value': 6.1,
        'target_value': 6.5,
        'reason': 'Корректировка необходима'
    }
    
    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    _configure_confirmed_command_bus(command_bus)
    
    with patch("correction_controller.record_correction"), \
         patch("correction_controller.create_zone_event") as mock_event, \
         patch("correction_controller.create_ai_log"):
        
        await controller.apply_correction(command, command_bus)
        
        # Проверяем, что было создано событие PH_TOO_LOW_DETECTED
        event_calls = [call[0][1] for call in mock_event.call_args_list]
        assert 'PH_TOO_LOW_DETECTED' in event_calls


@pytest.mark.asyncio
async def test_ec_controller_apply_correction():
    """Test applying EC correction (sending command and creating events)."""
    controller = CorrectionController(CorrectionType.EC)
    mqtt = Mock()
    gh_uid = "gh-1"
    
    command = {
        'node_uid': 'nd-ec-1',
        'channel': 'pump_a',
        'cmd': 'run_pump',
        'params': {'ml': 30.0, 'duration_ms': 1000, 'type': 'add_nutrients'},
        'event_type': 'EC_DOSING',
        'event_details': {
            'correction_type': 'add_nutrients',
            'current_ec': 1.5,
            'target_ec': 1.8,
            'diff': -0.3,
            'ml': 30.0
        },
        'zone_id': 1,
        'correction_type_str': 'ec',
        'current_value': 1.5,
        'target_value': 1.8,
        'reason': 'Корректировка необходима'
    }
    
    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    _configure_confirmed_command_bus(command_bus)
    
    with patch("correction_controller.record_correction") as mock_record, \
         patch("correction_controller.create_zone_event") as mock_event, \
         patch("correction_controller.create_ai_log") as mock_ai_log:
        
        await controller.apply_correction(command, command_bus)
        
        # Проверяем, что команда была отправлена
        command_bus.publish_controller_command.assert_called_once()
        
        # Проверяем, что было записано в cooldown
        mock_record.assert_called_once()
        
        # Проверяем, что были созданы события (EC_DOSING и DOSING)
        assert mock_event.call_count >= 2
        
        # Проверяем, что был создан AI log
        mock_ai_log.assert_called_once()


@pytest.mark.asyncio
async def test_structured_skip_log_for_water_level_guard(caplog):
    controller = CorrectionController(CorrectionType.PH)
    caplog.set_level(logging.WARNING, logger="correction_controller")

    targets = {"ph": {"target": 6.5}}
    telemetry = {"PH": 6.8}
    telemetry_ts = {"PH": datetime.now(timezone.utc).replace(tzinfo=None)}

    with patch("correction_controller.should_apply_correction", new_callable=AsyncMock, return_value=(True, "ok")), \
         patch.object(controller, "_get_pid", new_callable=AsyncMock, return_value=_PidStub(3.0)):
        result = await controller.check_and_correct(
            7,
            targets,
            telemetry,
            telemetry_ts,
            nodes={},
            water_level_ok=False,
            actuators={"ph_acid_pump": {"node_uid": "nd-ph", "channel": "pump_acid", "role": "ph_acid_pump"}},
        )

    assert result is None
    record = next(r for r in caplog.records if getattr(r, "reason_code", None) == "water_level_not_ok")
    assert getattr(record, "component", None) == "correction_controller"
    assert getattr(record, "zone_id", None) == 7
    assert getattr(record, "decision", None) == "skip"


@pytest.mark.asyncio
async def test_structured_retry_log_for_missing_cmd_id(caplog):
    caplog.set_level(logging.WARNING, logger="correction_command_retry")

    command_bus = Mock()
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    command_bus.tracker = Mock()
    command_bus.tracker.wait_for_command_done = AsyncMock(return_value=True)

    settings = SimpleNamespace(
        CORRECTION_COMMAND_MAX_ATTEMPTS=1,
        CORRECTION_COMMAND_TIMEOUT_SEC=1.0,
        CORRECTION_COMMAND_RETRY_DELAY_SEC=0.0,
    )
    create_zone_event_fn = AsyncMock()
    send_infra_alert_fn = AsyncMock()

    ok = await publish_controller_command_with_retry(
        zone_id=11,
        command_bus=command_bus,
        controller_command={"cmd": "dose", "node_uid": "nd-1", "channel": "pump"},
        context=SimpleNamespace(),
        correction_type="ph",
        get_settings_fn=lambda: settings,
        create_zone_event_fn=create_zone_event_fn,
        send_infra_alert_fn=send_infra_alert_fn,
    )

    assert ok is False
    record = next(r for r in caplog.records if getattr(r, "reason_code", None) == "cmd_id_missing_after_publish")
    assert getattr(record, "component", None) == "correction_command_retry"
    assert getattr(record, "zone_id", None) == 11
    assert getattr(record, "decision", None) == "fail_closed"


@pytest.mark.asyncio
async def test_retry_fails_closed_when_tracker_missing(caplog):
    caplog.set_level(logging.WARNING, logger="correction_command_retry")

    command_bus = Mock()
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    command_bus.tracker = None

    settings = SimpleNamespace(
        CORRECTION_COMMAND_MAX_ATTEMPTS=1,
        CORRECTION_COMMAND_TIMEOUT_SEC=1.0,
        CORRECTION_COMMAND_RETRY_DELAY_SEC=0.0,
    )
    create_zone_event_fn = AsyncMock()
    send_infra_alert_fn = AsyncMock()

    ok = await publish_controller_command_with_retry(
        zone_id=12,
        command_bus=command_bus,
        controller_command={"cmd": "dose", "node_uid": "nd-2", "channel": "pump"},
        context=SimpleNamespace(),
        correction_type="ph",
        get_settings_fn=lambda: settings,
        create_zone_event_fn=create_zone_event_fn,
        send_infra_alert_fn=send_infra_alert_fn,
    )

    assert ok is False
    record = next(r for r in caplog.records if getattr(r, "reason_code", None) == "command_tracker_unavailable")
    assert getattr(record, "component", None) == "correction_command_retry"
    assert getattr(record, "zone_id", None) == 12
    assert getattr(record, "decision", None) == "fail_closed"
    assert create_zone_event_fn.await_count >= 1
    event_payload = create_zone_event_fn.await_args_list[0].args[2]
    assert event_payload["reason"] == "command_tracker_unavailable"


@pytest.mark.asyncio
async def test_retry_emits_terminal_error_details_from_tracker_outcome():
    command_bus = Mock()
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    command_bus.tracker = Mock()
    command_bus.tracker.wait_for_command_done = AsyncMock(return_value=False)
    command_bus.tracker.get_command_outcome = AsyncMock(
        return_value={
            "status": "ERROR",
            "error_code": "node_not_activated",
            "error_message": "node is not activated",
        }
    )

    settings = SimpleNamespace(
        CORRECTION_COMMAND_MAX_ATTEMPTS=1,
        CORRECTION_COMMAND_TIMEOUT_SEC=1.0,
        CORRECTION_COMMAND_RETRY_DELAY_SEC=0.0,
    )
    create_zone_event_fn = AsyncMock()
    send_infra_alert_fn = AsyncMock()
    controller_command = {"cmd": "dose", "node_uid": "nd-ph", "channel": "pump_acid", "cmd_id": "cmd-err-1"}

    ok = await publish_controller_command_with_retry(
        zone_id=13,
        command_bus=command_bus,
        controller_command=controller_command,
        context=SimpleNamespace(),
        correction_type="ph",
        get_settings_fn=lambda: settings,
        create_zone_event_fn=create_zone_event_fn,
        send_infra_alert_fn=send_infra_alert_fn,
    )

    assert ok is False
    event_payload = create_zone_event_fn.await_args_list[0].args[2]
    assert event_payload["reason"] == "terminal_error"
    assert event_payload["terminal_status"] == "ERROR"
    assert event_payload["terminal_error_code"] == "node_not_activated"
    assert event_payload["terminal_error_message"] == "node is not activated"

    send_kwargs = send_infra_alert_fn.await_args.kwargs
    assert send_kwargs["details"]["terminal_status"] == "ERROR"
    assert send_kwargs["details"]["terminal_error_code"] == "node_not_activated"
    assert send_kwargs["details"]["terminal_error_message"] == "node is not activated"


@pytest.mark.asyncio
async def test_structured_freshness_fail_closed_log(caplog):
    caplog.set_level(logging.WARNING, logger="correction_freshness")
    failure_count = {}

    with patch("correction_freshness.create_zone_event", new_callable=AsyncMock), \
         patch("correction_freshness.create_alert", new_callable=AsyncMock):
        ok = await validate_freshness_or_skip(
            zone_id=5,
            metric_name="PH",
            target_key="ph",
            correction_type="ph",
            current=6.9,
            target=6.5,
            telemetry_timestamps=None,
            freshness_check_failure_count=failure_count,
            event_prefix="PH",
        )

    assert ok is False
    record = next(r for r in caplog.records if getattr(r, "reason_code", None) == "freshness_check_failed")
    assert getattr(record, "component", None) == "correction_freshness"
    assert getattr(record, "zone_id", None) == 5
    assert getattr(record, "decision", None) == "skip"
