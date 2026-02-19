from __future__ import annotations

from typing import Any, Dict


async def create_event(m: Any, zone_id: int, event_type: str, payload: Dict[str, Any]) -> None:
    await m.create_zone_event(zone_id, event_type, payload)
