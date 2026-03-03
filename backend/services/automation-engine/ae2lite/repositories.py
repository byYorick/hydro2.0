"""Repository facades for AE2-Lite runtime."""

from __future__ import annotations

from repositories.effective_targets_sql_read_model import EffectiveTargetsSqlReadModel
from repositories.laravel_api_repository import LaravelApiRepository


def build_sql_read_model(*, cache_ttl_sec: float = 30.0) -> EffectiveTargetsSqlReadModel:
    return EffectiveTargetsSqlReadModel(cache_ttl_sec=cache_ttl_sec)


__all__ = ["LaravelApiRepository", "build_sql_read_model", "EffectiveTargetsSqlReadModel"]
