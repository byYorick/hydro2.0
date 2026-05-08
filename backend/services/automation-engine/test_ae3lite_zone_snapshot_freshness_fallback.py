"""Тесты SQL-фильтра snapshot read-model по ``last_seen_at`` fallback.

Проверяют, что параметризованный SQL-запрос ``actuator_rows`` использует второй
позиционный параметр ``$2`` для freshness window и читает env-переменную
``AE3_NODE_FRESHNESS_FALLBACK_SEC``.
"""

from __future__ import annotations

import os

import pytest

from ae3lite.infrastructure.read_models.zone_snapshot_read_model import (
    _node_freshness_fallback_sec,
    _node_persistent_dead_sec,
)


def test_freshness_fallback_default_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AE3_NODE_FRESHNESS_FALLBACK_SEC", raising=False)
    assert _node_freshness_fallback_sec() == 180


def test_freshness_fallback_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AE3_NODE_FRESHNESS_FALLBACK_SEC", "300")
    assert _node_freshness_fallback_sec() == 300


def test_freshness_fallback_invalid_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AE3_NODE_FRESHNESS_FALLBACK_SEC", "not-a-number")
    assert _node_freshness_fallback_sec() == 180


def test_freshness_fallback_min_one_second(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AE3_NODE_FRESHNESS_FALLBACK_SEC", "0")
    assert _node_freshness_fallback_sec() == 1


def test_persistent_dead_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AE3_NODE_PERSISTENT_DEAD_SEC", raising=False)
    assert _node_persistent_dead_sec() == 600


def test_persistent_dead_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AE3_NODE_PERSISTENT_DEAD_SEC", "1200")
    assert _node_persistent_dead_sec() == 1200


def test_persistent_dead_min_60_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Жёсткий нижний предел: < 60s переводит ноду в persistent слишком агрессивно."""
    monkeypatch.setenv("AE3_NODE_PERSISTENT_DEAD_SEC", "10")
    assert _node_persistent_dead_sec() == 60


def test_actuator_query_includes_freshness_fallback_clause() -> None:
    """SQL-фильтр actuator-выборки содержит fallback по last_seen_at + параметр $2."""
    from ae3lite.infrastructure.read_models import zone_snapshot_read_model as module

    source = module.__loader__.get_source(module.__name__)
    actuator_query_marker = "FROM nodes n\n                    JOIN node_channels nc"
    assert actuator_query_marker in source

    fallback_marker = (
        "OR COALESCE(n.last_seen_at, n.last_heartbeat_at, n.updated_at)\n"
        "                                 >= NOW() - ($2 * INTERVAL '1 second')"
    )
    assert fallback_marker in source, "Actuator SQL должен использовать $2 для freshness fallback"


def test_diagnostics_query_groups_by_node() -> None:
    from ae3lite.infrastructure.read_models import zone_snapshot_read_model as module

    source = module.__loader__.get_source(module.__name__)
    assert "active_actuator_count" in source
    assert "GROUP BY n.id" in source
