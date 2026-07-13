import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_resolve_zone_id_for_node_event_prefers_zones_uid_for_zn_prefixed_uid() -> None:
    from handlers._shared import resolve_zone_id_for_node_event

    with patch("handlers._shared.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [
            [{"id": 1}],
        ]

        zone_id = await resolve_zone_id_for_node_event("zn-886", "nd-test-irrig-1")

        assert zone_id == 1
        assert mock_fetch.await_count == 1


@pytest.mark.asyncio
async def test_resolve_zone_id_for_node_event_falls_back_to_node_zone_when_uid_missing() -> None:
    """zn-<N> must NOT become zones.id=N; use nodes.zone_id when uid lookup misses."""
    from handlers._shared import resolve_zone_id_for_node_event

    with patch("handlers._shared.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [
            [],  # zones.uid miss
            [{"zone_id": 1}],  # nodes.uid hit
        ]

        zone_id = await resolve_zone_id_for_node_event("zn-1411", "nd-test-irrig-1")

        assert zone_id == 1
        assert mock_fetch.await_count == 2


@pytest.mark.asyncio
async def test_resolve_zone_id_for_node_event_returns_none_when_unresolved() -> None:
    from handlers._shared import resolve_zone_id_for_node_event

    with patch("handlers._shared.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [
            [],
            [],
        ]

        zone_id = await resolve_zone_id_for_node_event("zn-1411", "nd-missing")

        assert zone_id is None
        assert mock_fetch.await_count == 2
