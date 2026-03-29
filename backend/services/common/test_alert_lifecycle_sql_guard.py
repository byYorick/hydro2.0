from __future__ import annotations

from pathlib import Path


SERVICES_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_SQL_PATTERNS = (
    "UPDATE alerts",
    "INSERT INTO alerts",
    "DELETE FROM alerts",
)

FORBIDDEN_ALERT_EVENT_PATTERNS = (
    "ALERT_CREATED",
    "ALERT_UPDATED",
    "ALERT_RESOLVED",
)


def _iter_runtime_python_files():
    for path in SERVICES_ROOT.rglob("*.py"):
        relative = path.relative_to(SERVICES_ROOT).as_posix()
        if "/test_" in f"/{relative}" or "/tests/" in f"/{relative}":
            continue
        yield path, relative


def test_runtime_python_has_no_direct_alert_lifecycle_sql_mutations() -> None:
    violations: list[str] = []

    for path, relative in _iter_runtime_python_files():
        content = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_SQL_PATTERNS:
            if pattern in content:
                violations.append(f"{relative}: forbidden SQL pattern `{pattern}`")

    assert violations == [], "Found direct alert lifecycle SQL mutations:\n" + "\n".join(violations)


def test_runtime_python_has_no_manual_alert_zone_event_emission() -> None:
    violations: list[str] = []

    for path, relative in _iter_runtime_python_files():
        content = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_ALERT_EVENT_PATTERNS:
            if pattern in content:
                violations.append(f"{relative}: forbidden alert event `{pattern}`")

    assert violations == [], "Found manual alert zone_event emission outside Laravel:\n" + "\n".join(violations)
