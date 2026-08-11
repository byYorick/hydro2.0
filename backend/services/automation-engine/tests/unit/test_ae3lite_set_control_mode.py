from __future__ import annotations

from datetime import datetime, timezone

from ae3lite.application.use_cases.set_control_mode import SetControlModeUseCase


NOW = datetime(2026, 3, 14, 15, 20, 0, tzinfo=timezone.utc)


class _TaskRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def update_control_mode_snapshot_for_zone(self, *, zone_id: int, control_mode: str, now: datetime) -> None:
        self.calls.append({"zone_id": zone_id, "control_mode": control_mode, "now": now})


async def test_set_control_mode_updates_zone_and_active_snapshot() -> None:
    executed: list[tuple[str, tuple[object, ...]]] = []

    async def execute_fn(query: str, *args: object) -> str:
        executed.append((query, args))
        return "UPDATE 1"

    repo = _TaskRepository()
    result = await SetControlModeUseCase(
        task_repository=repo,
        execute_fn=execute_fn,
    ).run(zone_id=7, control_mode="manual", now=NOW)

    assert result == "manual"
    assert executed
    assert repo.calls == [{"zone_id": 7, "control_mode": "manual", "now": NOW}]
