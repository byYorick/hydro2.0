"""State storage adapters for AE2-Lite."""

from __future__ import annotations

from typing import Any, Dict, Optional

from infrastructure.workflow_state_store import WorkflowStateStore


class Ae2StateStore:
    def __init__(self, workflow_store: Optional[WorkflowStateStore] = None):
        self._workflow_store = workflow_store or WorkflowStateStore()

    async def get_workflow_state(self, zone_id: int) -> Optional[Dict[str, Any]]:
        return await self._workflow_store.get(zone_id)

    async def upsert_workflow_state(
        self,
        *,
        zone_id: int,
        workflow_phase: str,
        payload: Dict[str, Any],
        updated_at_iso: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self._workflow_store.upsert(
            zone_id=zone_id,
            workflow_phase=workflow_phase,
            payload=payload,
            updated_at_iso=updated_at_iso,
        )
        row = await self._workflow_store.get(zone_id)
        return row or {"zone_id": zone_id, "workflow_phase": workflow_phase, "payload": payload}


__all__ = ["Ae2StateStore"]
