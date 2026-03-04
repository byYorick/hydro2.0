import sys
import types


if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")
    asyncpg_stub.Connection = object
    asyncpg_stub.pool = types.SimpleNamespace(Pool=object)

    async def _create_pool_stub(*_args, **_kwargs):
        raise RuntimeError("asyncpg is not available in this test runtime")

    asyncpg_stub.create_pool = _create_pool_stub
    sys.modules["asyncpg"] = asyncpg_stub

if "prometheus_client" not in sys.modules:
    prometheus_client_stub = types.ModuleType("prometheus_client")

    class _CounterStub:
        def __init__(self, *_args, **_kwargs):
            pass

        def labels(self, **_kwargs):
            return self

        def inc(self):
            return None

    prometheus_client_stub.Counter = _CounterStub
    sys.modules["prometheus_client"] = prometheus_client_stub


from correction_ec_batch import build_ec_component_batch


def _mock_targets_with_all_components():
    return {
        "nutrition": {
            "mode": "ratio_ec_pid",
            "components": {
                "npk": {"ratio_pct": 60.0},
                "calcium": {"ratio_pct": 15.0},
                "magnesium": {"ratio_pct": 15.0},
                "micro": {"ratio_pct": 10.0},
            },
        }
    }


def _mock_actuators(missing_calibration_for=None):
    missing_calibration_for = set(missing_calibration_for or [])
    roles = {
        "npk": "ec_npk_pump",
        "calcium": "ec_calcium_pump",
        "magnesium": "ec_magnesium_pump",
        "micro": "ec_micro_pump",
    }
    actuators = {}
    for index, (component, role) in enumerate(roles.items(), start=1):
        actuators[role] = {
            "role": role,
            "node_uid": f"node_{component}",
            "channel": f"ch_{component}",
            "node_channel_id": index,
            "ml_per_sec": 0.0 if component in missing_calibration_for else 1.0,
        }
    return actuators


def _mock_build_cmd(actuator, correction_type, amount_ml):
    return {
        "cmd": "run_pump",
        "params": {
            "type": correction_type,
            "ml": amount_ml,
            "duration_ms": int(amount_ml * 1000),
        },
    }


class TestEcBatchPartialCalibration:
    def test_all_calibrated_returns_4_commands(self):
        commands = build_ec_component_batch(
            targets=_mock_targets_with_all_components(),
            actuators=_mock_actuators(),
            total_ml=40.0,
            current_ec=1.0,
            target_ec=1.6,
            allowed_ec_components=None,
            build_correction_command=_mock_build_cmd,
        )

        assert len(commands) == 4

    def test_micro_missing_calibration_still_doses_others(self):
        commands = build_ec_component_batch(
            targets=_mock_targets_with_all_components(),
            actuators=_mock_actuators(missing_calibration_for=["micro"]),
            total_ml=40.0,
            current_ec=1.0,
            target_ec=1.6,
            allowed_ec_components=None,
            build_correction_command=_mock_build_cmd,
        )

        components_dosed = {command["component"] for command in commands}
        assert "micro" not in components_dosed
        assert "npk" in components_dosed
        assert "calcium" in components_dosed
        assert "magnesium" in components_dosed

    def test_all_missing_calibration_returns_empty(self):
        commands = build_ec_component_batch(
            targets=_mock_targets_with_all_components(),
            actuators=_mock_actuators(missing_calibration_for=["npk", "calcium", "magnesium", "micro"]),
            total_ml=40.0,
            current_ec=1.0,
            target_ec=1.6,
            allowed_ec_components=None,
            build_correction_command=_mock_build_cmd,
        )

        assert commands == []

    def test_npk_missing_calibration_returns_empty(self):
        commands = build_ec_component_batch(
            targets=_mock_targets_with_all_components(),
            actuators=_mock_actuators(missing_calibration_for=["npk"]),
            total_ml=40.0,
            current_ec=1.0,
            target_ec=1.6,
            allowed_ec_components=None,
            build_correction_command=_mock_build_cmd,
        )

        assert commands == []
