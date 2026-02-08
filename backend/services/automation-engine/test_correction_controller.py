"""Tests for correction_controller."""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from types import SimpleNamespace
from datetime import datetime, timezone
from correction_controller import CorrectionController, CorrectionType


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


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_no_target():
    """Test pH controller when target is not set."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {}
    telemetry = {"PH": 6.5}
    nodes = {}
    
    telemetry_ts = {"PH": datetime.now(timezone.utc)}
    result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
    assert result is None


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_no_current():
    """Test pH controller when current value is not available."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": {"target": 6.5}}
    telemetry = {}
    nodes = {}
    
    telemetry_ts = {"PH": datetime.now(timezone.utc)}
    result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
    assert result is None


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_small_diff():
    """Test pH controller when difference is too small."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": {"target": 6.5}}
    telemetry = {"PH": 6.4}  # diff = 0.1, меньше порога 0.2
    nodes = {}
    
    telemetry_ts = {"PH": datetime.now(timezone.utc)}
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
            telemetry_ts = {"PH": datetime.now(timezone.utc)}
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

        telemetry_ts = {"PH": datetime.now(timezone.utc)}
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

        telemetry_ts = {"PH": datetime.now(timezone.utc)}
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

        telemetry_ts = {"PH": datetime.now(timezone.utc)}
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
        
        telemetry_ts = {"PH": datetime.now(timezone.utc)}
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
        telemetry_ts = {"PH": datetime.now(timezone.utc)}
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
        
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
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
        
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
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
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
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
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
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

        telemetry_ts = {"EC": datetime.now(timezone.utc)}
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
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
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
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
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
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
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
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
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
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
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
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
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
    command_bus.publish_controller_command = AsyncMock(return_value=True)

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
    command_bus.publish_controller_command = AsyncMock(return_value=True)

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
    command_bus.publish_controller_command = AsyncMock(return_value=True)

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
         patch("correction_controller.send_infra_alert", new_callable=AsyncMock), \
         patch("correction_controller.fetch", new_callable=AsyncMock, return_value=[]):
        await controller.apply_correction(command, command_bus)

    assert command_bus.publish_controller_command.await_count == 2
    command_bus.tracker.confirm_command_status.assert_awaited()
    assert mock_record.await_count == 0
    events = [call.args[1] for call in mock_zone_event.await_args_list if len(call.args) >= 2]
    assert "EC_COMPONENT_BATCH_ABORTED" in events


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
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    
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
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    
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
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    
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
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    
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
