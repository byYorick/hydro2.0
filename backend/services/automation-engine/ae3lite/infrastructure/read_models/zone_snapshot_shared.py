"""Shared records and immutable policy values for PgZoneSnapshotReadModel."""

from __future__ import annotations

import os


def _node_freshness_fallback_sec() -> int:
    """Окно (сек) для fallback по last_seen_at, если ``nodes.status`` ещё не обновлён.

    Должно перекрывать ``NODE_OFFLINE_TIMEOUT_SEC + NODE_OFFLINE_CHECK_INTERVAL_SEC``
    (history-logger). Default 180 = 120 (heartbeat timeout) + 60 (sweep interval).
    """
    try:
        return max(1, int(os.getenv("AE3_NODE_FRESHNESS_FALLBACK_SEC", "180")))
    except (TypeError, ValueError):
        return 180


def _node_persistent_dead_sec() -> int:
    """Возраст ``last_seen_at``, после которого нода считается persistently dead.

    При попадании в snapshot diagnostics такая нода переводит SnapshotBuildError
    в немедленный fail-closed без retry (см. ExecuteTaskUseCase).
    Default 600 секунд (10 минут).
    """
    try:
        return max(60, int(os.getenv("AE3_NODE_PERSISTENT_DEAD_SEC", "600")))
    except (TypeError, ValueError):
        return 600
