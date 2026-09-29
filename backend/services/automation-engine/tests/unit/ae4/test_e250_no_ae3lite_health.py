"""E250: процесс без пакета ae3lite; health/metrics в ae4."""

from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.routing import APIRoute


def test_e250_ae3lite_directory_gone() -> None:
    root = Path(__file__).resolve().parents[3]
    assert not (root / "ae3lite").exists()


def test_e250_health_and_metrics_registered_in_ae4(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AE_DB_DSN", "postgresql://hydro:hydro@localhost:5432/hydro_test")
    monkeypatch.setenv("HISTORY_LOGGER_API_TOKEN", "test-token")
    monkeypatch.setenv("AE_API_TOKEN", "test-token")
    monkeypatch.setenv("AE_SCHEDULER_SECURITY_BASELINE_ENFORCE", "0")

    # Не стартуем lifespan/воркер — только фабрика маршрутов.
    from ae4.runtime import app as app_module

    class _DummyWorker:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs
            self._stop = type("E", (), {"is_set": lambda self: False})()

        async def run(self) -> None:
            return None

        async def shutdown(self) -> None:
            return None

    monkeypatch.setattr(app_module, "Ae4RuntimeWorker", _DummyWorker)
    application = app_module.create_app()
    paths = {route.path for route in application.routes if isinstance(route, APIRoute)}
    assert "/health" in paths or "/health/live" in paths
    assert "/health/ready" in paths
    mounted = [getattr(route, "path", "") for route in application.routes]
    assert any(path.startswith("/metrics") for path in mounted)

    # Импорт ae3lite обязан падать.
    try:
        importlib.import_module("ae3lite")
        raise AssertionError("ae3lite must not import")
    except ModuleNotFoundError:
        pass
