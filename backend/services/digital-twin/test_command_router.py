"""Тесты CommandRouter — диспетчера inputs_schedule (Phase B)."""
import pytest

from solvers import ActuatorSolver
from world import CommandRouter


def _events():
    return [
        {"t_min": 0.0, "cmd": "set_relay", "channel": "valve_clean_fill", "params": {"state": True}},
        {"t_min": 5.0, "cmd": "set_relay", "channel": "valve_clean_fill", "params": {"state": False}},
        {"t_min": 10.0, "cmd": "dose", "channel": "pump_a", "params": {"ml": 3.0}},
    ]


def test_command_router_normalizes_and_sorts_events():
    actuator = ActuatorSolver()
    router = CommandRouter(actuator, schedule=[
        {"t_min": 5.0, "cmd": "dose", "channel": "pump_a", "params": {"ml": 1.0}},
        {"t_min": 1.0, "cmd": "set_relay", "channel": "valve_clean_fill", "params": {"state": True}},
    ])
    assert router.remaining_events == 2
    applied = router.advance_to(2.0)
    # Первый по времени — set_relay
    assert len(applied) == 1
    assert applied[0].cmd == "set_relay"


def test_command_router_advance_applies_events_in_order():
    actuator = ActuatorSolver()
    router = CommandRouter(actuator, schedule=_events())
    # До 1 минуты — только первое событие (включить valve)
    applied = router.advance_to(1.0)
    assert len(applied) == 1
    assert actuator.state.valves_open["valve_clean_fill"] is True
    # До 7 минут — добавляется выключение
    applied = router.advance_to(7.0)
    assert len(applied) == 1
    assert actuator.state.valves_open["valve_clean_fill"] is False
    # До 11 минут — добавляется доза
    applied = router.advance_to(11.0)
    assert len(applied) == 1
    assert "pump_ec_a" in actuator.state.pulses_by_role


def test_command_router_skips_invalid_events():
    actuator = ActuatorSolver()
    router = CommandRouter(actuator, schedule=[
        {"t_min": 0.0, "cmd": "dose", "channel": "pump_a", "params": {"ml": 1.0}},
        {"t_min": "bad", "cmd": "dose", "channel": "pump_a", "params": {"ml": 1.0}},
        {"t_min": 1.0, "cmd": "", "channel": "pump_a", "params": {"ml": 1.0}},
        {"t_min": 1.0, "cmd": "dose", "channel": "", "params": {"ml": 1.0}},
        "not a dict",
    ])
    assert router.remaining_events == 1


def test_command_router_idempotent_past_advance():
    actuator = ActuatorSolver()
    router = CommandRouter(actuator, schedule=_events())
    router.advance_to(100.0)
    assert router.remaining_events == 0
    # Ещё один advance не упадёт и ничего не применит
    applied = router.advance_to(200.0)
    assert applied == []


def test_command_router_negative_t_min_clamped_to_zero():
    actuator = ActuatorSolver()
    router = CommandRouter(actuator, schedule=[
        {"t_min": -10.0, "cmd": "set_relay", "channel": "valve_clean_fill", "params": {"state": True}},
    ])
    applied = router.advance_to(0.0)
    assert len(applied) == 1
