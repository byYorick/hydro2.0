import pytest


@pytest.mark.asyncio
async def test_should_emit_event_throttles_within_interval():
    from common import simulation_events

    simulation_events._reset_throttle_cache()

    assert simulation_events._should_emit_event("zone:1", 5.0, now=1.0) is True
    assert simulation_events._should_emit_event("zone:1", 5.0, now=3.0) is False
    assert simulation_events._should_emit_event("zone:1", 5.0, now=6.1) is True


@pytest.mark.asyncio
async def test_should_emit_event_allows_different_keys():
    from common import simulation_events

    simulation_events._reset_throttle_cache()

    assert simulation_events._should_emit_event("zone:1", 5.0, now=1.0) is True
    assert simulation_events._should_emit_event("zone:2", 5.0, now=1.1) is True
