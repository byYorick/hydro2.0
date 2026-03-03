from __future__ import annotations

import importlib
import pkgutil

import ae2lite
import ae2lite.repositories as repositories
import pytest
from repositories.effective_targets_sql_read_model import EffectiveTargetsSqlReadModel


def test_ae2lite_repositories_exports_sql_read_model_builder():
    reader = repositories.build_sql_read_model(cache_ttl_sec=5.0)
    assert isinstance(reader, EffectiveTargetsSqlReadModel)


def test_ae2lite_package_modules_import_without_errors():
    failed: list[str] = []
    for module in pkgutil.iter_modules(ae2lite.__path__):
        module_name = f"ae2lite.{module.name}"
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - diagnostic guard
            failed.append(f"{module_name}: {type(exc).__name__}: {exc}")

    assert failed == []


@pytest.mark.parametrize(
    "module_name",
    [
        "ae2lite.zone_runner",
        "ae2lite.zone_registry",
        "ae2lite.runtime",
        "ae2lite.state_store",
        "ae2lite.two_tank_workflow",
    ],
)
def test_removed_legacy_facades_are_not_importable(module_name: str):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)
