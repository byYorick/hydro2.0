#!/usr/bin/env python3
"""AE2 machine-checkable invariants for CI/local verification."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class Violation:
    check: str
    path: Path
    message: str


IGNORED_DIRS = {"__pycache__", ".venv", ".mypy_cache", ".pytest_cache"}


def _iter_python_files(base: Path) -> Iterable[Path]:
    for path in base.rglob("*.py"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        yield path


def _is_test_file(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root).as_posix()
    name = path.name
    return (
        "/tests/" in rel
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _line_of_first_match(pattern: re.Pattern[str], text: str) -> int | None:
    match = pattern.search(text)
    if not match:
        return None
    return text[: match.start()].count("\n") + 1


def check_history_logger_publish_path(repo_root: Path) -> List[Violation]:
    """
    Команды к history-logger должны уходить только из command_bus.
    Фиксируем только явные publish endpoint references `/commands`.
    """
    check_name = "history_logger_single_publish_path"
    ae_root = repo_root / "backend/services/automation-engine"
    allowed = ae_root / "infrastructure/command_bus.py"
    violations: List[Violation] = []

    for path in _iter_python_files(ae_root):
        if _is_test_file(path, repo_root):
            continue
        if path == allowed:
            continue
        text = _read_text(path)
        if "/commands" in text and ("history_logger" in text or "history-logger" in text):
            violations.append(
                Violation(
                    check=check_name,
                    path=path,
                    message="Найден reference history-logger publish endpoint вне infrastructure/command_bus.py",
                )
            )
    return violations


def check_no_direct_mqtt_publish_in_runtime(repo_root: Path) -> List[Violation]:
    check_name = "no_direct_mqtt_publish_runtime"
    ae_root = repo_root / "backend/services/automation-engine"
    publish_pattern = re.compile(r"\.(publish|publish_json)\s*\(")
    violations: List[Violation] = []

    for path in _iter_python_files(ae_root):
        if _is_test_file(path, repo_root):
            continue
        text = _read_text(path)
        line = _line_of_first_match(publish_pattern, text)
        if line is not None:
            violations.append(
                Violation(
                    check=check_name,
                    path=path,
                    message=f"Найден прямой MQTT publish вызов (line {line})",
                )
            )
    return violations


def check_feature_flags_executor_constants(repo_root: Path) -> List[Violation]:
    """
    Минимальный guard:
    1) executor constants файл существует и содержит ожидаемые anchor constants;
    2) в executor-* модулях нет прямого os.getenv/os.environ.get, кроме executor_constants.py.
    """
    check_name = "feature_flags_executor_constants"
    app_root = repo_root / "backend/services/automation-engine/application"
    constants_path = app_root / "executor_constants.py"
    violations: List[Violation] = []

    if not constants_path.exists():
        return [
            Violation(
                check=check_name,
                path=constants_path,
                message="Отсутствует application/executor_constants.py",
            )
        ]

    constants_text = _read_text(constants_path)
    for anchor in ("AE_LEGACY_WORKFLOW_DEFAULT_ENABLED", "AUTO_LOGIC_DECISION_V1"):
        if anchor not in constants_text:
            violations.append(
                Violation(
                    check=check_name,
                    path=constants_path,
                    message=f"Не найден anchor feature-flag constant: {anchor}",
                )
            )

    env_pattern = re.compile(r"os\.(getenv|environ\.get)\s*\(")
    for path in app_root.glob("executor*.py"):
        if path == constants_path:
            continue
        text = _read_text(path)
        line = _line_of_first_match(env_pattern, text)
        if line is not None:
            violations.append(
                Violation(
                    check=check_name,
                    path=path,
                    message=f"Прямой env-access в executor модуле (line {line}); зарегистрируйте флаг в executor_constants.py",
                )
            )

    return violations


def check_no_sql_ddl_in_python_services(repo_root: Path) -> List[Violation]:
    check_name = "no_sql_ddl_in_python_services"
    services_root = repo_root / "backend/services"
    ddl_pattern = re.compile(r"\b(CREATE|ALTER|DROP)\s+TABLE\b", re.IGNORECASE)
    violations: List[Violation] = []

    for path in _iter_python_files(services_root):
        if _is_test_file(path, repo_root):
            continue
        text = _read_text(path)
        line = _line_of_first_match(ddl_pattern, text)
        if line is not None:
            violations.append(
                Violation(
                    check=check_name,
                    path=path,
                    message=f"Найден SQL DDL в Python-сервисе (line {line})",
                )
            )
    return violations


def run_all(repo_root: Path) -> Sequence[Violation]:
    checks = (
        check_history_logger_publish_path,
        check_no_direct_mqtt_publish_in_runtime,
        check_feature_flags_executor_constants,
        check_no_sql_ddl_in_python_services,
    )
    violations: List[Violation] = []
    for check in checks:
        violations.extend(check(repo_root))
    return violations


def _print_report(repo_root: Path, violations: Sequence[Violation]) -> None:
    if not violations:
        print("AE2_INVARIANTS: PASS")
        print(f"repo_root={repo_root}")
        return

    print("AE2_INVARIANTS: FAIL")
    print(f"repo_root={repo_root}")
    for violation in violations:
        rel = violation.path.relative_to(repo_root).as_posix()
        print(f"[{violation.check}] {rel}: {violation.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AE2 machine-checkable invariants.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Path to repository root (default: auto-detected).",
    )
    args = parser.parse_args()

    repo_root = args.root.resolve()
    violations = run_all(repo_root)
    _print_report(repo_root, violations)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
