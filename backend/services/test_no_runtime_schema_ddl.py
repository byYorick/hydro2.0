"""Guardrails: runtime services must not manage DB schema outside Laravel migrations."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent

# Runtime code only (exclude tests/docs) must not contain DDL statements.
DDL_PATTERN = re.compile(
    r"\b(create\s+table|alter\s+table|drop\s+table|create\s+index|drop\s+index|truncate\s+table)\b",
    re.IGNORECASE,
)

SERVICE_DIRS = (
    "common",
    "history-logger",
    "automation-engine",
    "scheduler",
    "mqtt-bridge",
    "telemetry-aggregator",
    "digital-twin",
    "node-emulator",
)


def _iter_runtime_python_files() -> list[Path]:
    files: list[Path] = []
    for service_dir in SERVICE_DIRS:
        base = ROOT / service_dir
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            rel = path.relative_to(ROOT)
            parts = rel.parts
            name = path.name
            if "test" in parts or "tests" in parts:
                continue
            if name.startswith("test_"):
                continue
            files.append(path)
    return files


def test_runtime_services_do_not_execute_schema_ddl() -> None:
    offenders: list[str] = []
    for path in _iter_runtime_python_files():
        content = path.read_text(encoding="utf-8")
        if DDL_PATTERN.search(content):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == [], (
        "Найдены runtime DDL-операции в сервисах. "
        "Схема БД должна управляться только Laravel миграциями: "
        + ", ".join(sorted(offenders))
    )


def test_services_do_not_ship_local_sql_migrations() -> None:
    sql_files = sorted(
        str(p.relative_to(ROOT))
        for service_dir in SERVICE_DIRS
        for p in (ROOT / service_dir).rglob("*.sql")
        if (ROOT / service_dir).exists() and "test" not in p.parts and "tests" not in p.parts
    )
    assert sql_files == [], (
        "Найдены SQL-файлы в backend/services (локальные миграции запрещены): "
        + ", ".join(sql_files)
    )
