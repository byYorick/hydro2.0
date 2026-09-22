"""Пакет ae4 не тянет ae3lite и не читает переключатель процесса."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from ae4.runtime.env import Ae4RuntimeConfig

_PACKAGE = Path(__file__).resolve().parents[3] / "ae4"
_MAIN = Path(__file__).resolve().parents[3] / "main.py"


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def test_ae4_package_does_not_import_ae3lite() -> None:
    offenders: list[str] = []
    for path in _python_files(_PACKAGE):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.Import):
                module = " ".join(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
            if module == "ae3lite" or module.startswith("ae3lite."):
                offenders.append(f"{path}:{getattr(node, 'lineno', 0)}:{module}")
    assert offenders == []


def test_ae4_and_process_entry_have_no_runtime_switch() -> None:
    files = [*_python_files(_PACKAGE), _MAIN]
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "AE_RUNTIME":
                raise AssertionError(f"{path} читает AE_RUNTIME")


def test_reconcile_interval_uses_existing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AE_RECONCILE_POLL_INTERVAL_SEC", "1.25")
    assert Ae4RuntimeConfig.from_env().reconcile_poll_interval_sec == 1.25

    monkeypatch.setenv("AE_RECONCILE_POLL_INTERVAL_SEC", "0.01")
    assert Ae4RuntimeConfig.from_env().reconcile_poll_interval_sec == 0.1


async def test_main_starts_both_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AE_RECONCILE_POLL_INTERVAL_SEC", "1.25")
    started: list[str] = []
    stop = asyncio.Event()

    class RecordingWorker:
        def __init__(self, *, config: Ae4RuntimeConfig) -> None:
            assert config.reconcile_poll_interval_sec == 1.25
            started.append("ae4-init")

        async def run(self) -> None:
            started.append("ae4-run")
            await stop.wait()

        async def shutdown(self) -> None:
            started.append("ae4-stop")
            stop.set()

    async def fake_serve() -> None:
        started.append("ae3-serve")

    import main as process_main

    monkeypatch.setattr(process_main, "Ae4RuntimeWorker", RecordingWorker)
    monkeypatch.setattr(process_main, "serve", fake_serve)
    await process_main.main()

    assert "ae4-init" in started
    assert "ae4-run" in started
    assert "ae3-serve" in started
    assert "ae4-stop" in started
