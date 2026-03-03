"""Interface for event-driven zone workflow check triggering."""

from __future__ import annotations

from typing import Any, Dict, Optional


class ZoneEventTrigger:
    """Stub implementation for push-triggered zone checks.

    Current behavior: no-op (polling remains the active mechanism).
    Future behavior: immediately enqueue two-tank check tasks after receiving
    relevant events through LISTEN/NOTIFY.
    """

    async def on_zone_event(
        self,
        *,
        zone_id: int,
        event_type: str,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Handle pushed zone event and optionally trigger a check task.

        Returns enqueue result when trigger is implemented, None otherwise.
        """
        _ = (zone_id, event_type, payload)
        return None


__all__ = ["ZoneEventTrigger"]
