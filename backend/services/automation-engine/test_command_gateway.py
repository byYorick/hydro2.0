from unittest.mock import AsyncMock, patch

import pytest

from infrastructure.command_gateway import CommandGateway


class _FakeLock:
    def __init__(self) -> None:
        self.entered = 0

    async def __aenter__(self):
        self.entered += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_publish_command_uses_zone_lock():
    bus = AsyncMock()
    bus.publish_command = AsyncMock(return_value=True)
    gateway = CommandGateway(bus, enable_zone_lock=True)
    fake_lock = _FakeLock()

    with patch.object(CommandGateway, "_get_zone_lock", return_value=fake_lock):
        result = await gateway.publish_command(
            zone_id=7,
            node_uid="nd-irrig-1",
            channel="pump_main",
            cmd="set_state",
            params={"state": True},
        )

    assert result is True
    assert fake_lock.entered == 1
    bus.publish_command.assert_awaited_once_with(
        7,
        "nd-irrig-1",
        "pump_main",
        "set_state",
        {"state": True},
        cmd_id=None,
    )


@pytest.mark.asyncio
async def test_publish_controller_command_closed_loop_does_not_hold_zone_lock():
    bus = AsyncMock()
    bus.publish_controller_command_closed_loop = AsyncMock(
        return_value={"command_submitted": True, "command_effect_confirmed": True, "terminal_status": "DONE"}
    )
    gateway = CommandGateway(bus, enable_zone_lock=True)
    fake_lock = _FakeLock()

    with patch.object(CommandGateway, "_get_zone_lock", return_value=fake_lock):
        result = await gateway.publish_controller_command_closed_loop(
            zone_id=7,
            command={"node_uid": "nd-irrig-1", "channel": "pump_main", "cmd": "set_state"},
            context={"reason": "test"},
            timeout_sec=30,
        )

    assert result["command_effect_confirmed"] is True
    assert fake_lock.entered == 0
    bus.publish_controller_command_closed_loop.assert_awaited_once_with(
        zone_id=7,
        command={"node_uid": "nd-irrig-1", "channel": "pump_main", "cmd": "set_state"},
        context={"reason": "test"},
        timeout_sec=30,
    )
