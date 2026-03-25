from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.infrastructure.repositories.zone_correction_authority_repository import (
    PgZoneCorrectionAuthorityRepository,
)


@pytest.mark.asyncio
async def test_mark_applied_passes_datetimes_to_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    async def _fake_execute(query: str, *args: object) -> str:
        recorded["query"] = query
        recorded["args"] = args
        return "UPDATE 1"

    monkeypatch.setattr(
        "ae3lite.infrastructure.repositories.zone_correction_authority_repository.execute",
        _fake_execute,
    )

    repository = PgZoneCorrectionAuthorityRepository()
    now = datetime(2026, 3, 25, 9, 15, 11, 987654, tzinfo=timezone.utc)

    await repository.mark_applied(zone_id=1, version=42, now=now)

    args = recorded["args"]
    assert args[0] == 1
    assert args[1] == 42
    assert args[2] == datetime(2026, 3, 25, 9, 15, 11, tzinfo=timezone.utc)
    assert args[3] == datetime(2026, 3, 25, 9, 15, 11)
