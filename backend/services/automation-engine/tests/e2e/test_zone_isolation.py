import pytest

from test_infrastructure_repository import (
    test_get_zone_bindings_by_role_filters_nodes_by_zone,
)
from test_command_bus import (
    test_publish_command_rejects_node_zone_mismatch_when_guard_enabled,
    test_publish_command_rejects_actuator_command_on_sensor_channel_when_compatibility_enabled,
)


@pytest.mark.asyncio
async def test_e2e_14_zone_isolation_two_zones_commands_do_not_cross():
    await test_get_zone_bindings_by_role_filters_nodes_by_zone()


@pytest.mark.asyncio
async def test_e2e_15_node_zone_mismatch_rejection():
    await test_publish_command_rejects_node_zone_mismatch_when_guard_enabled()


@pytest.mark.asyncio
async def test_e2e_16_channel_command_compatibility_rejection():
    await test_publish_command_rejects_actuator_command_on_sensor_channel_when_compatibility_enabled()
