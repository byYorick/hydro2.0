#!/usr/bin/env python3
"""Аудит фазы 2: локализованные API-ошибки (human_error_message)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LARAVEL_CTRL = REPO / "backend" / "laravel" / "app" / "Http" / "Controllers"
AE3 = REPO / "backend" / "services" / "automation-engine" / "ae3lite"

UPPER_CODE = re.compile(r"""['"]code['"]\s*=>\s*['"]([A-Z][A-Z0-9_]+)['"]""")
LOCALIZED_TRAIT = "PresentsLocalizedApiErrors"
HUMAN_FIELD = "human_error_message"


def scan_php_controllers() -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {}
    localized: list[str] = []
    raw_errors: list[str] = []

    for path in sorted(LARAVEL_CTRL.rglob("*.php")):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO).as_posix()
        if LOCALIZED_TRAIT in text:
            localized.append(rel)
        upper_codes = UPPER_CODE.findall(text)
        if upper_codes:
            raw_errors.append(f"{rel}: {', '.join(sorted(set(upper_codes)))}")
        if "'status' => 'error'" in text and HUMAN_FIELD not in text and upper_codes:
            issues.setdefault("controllers_without_human_field", []).append(rel)

    return {
        "localized_trait_count": str(len(localized)),
        "localized_trait_files": localized,
        "upper_snake_code_remaining": raw_errors,
        "controllers_error_without_human_field": issues.get("controllers_without_human_field", []),
    }


def scan_ae3() -> dict[str, list[str]]:
    hits: list[str] = []
    if not AE3.exists():
        return {"ae3_files_with_human_error_message": hits}
    for path in sorted(AE3.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if HUMAN_FIELD in text or "present_error" in text or "api_error_detail" in text:
            hits.append(path.relative_to(REPO).as_posix())
    return {"ae3_files_with_human_error_message": hits}


def main() -> int:
    report = {**scan_php_controllers(), **scan_ae3()}
    print("=== Аудит фазы 2: API human_error_message ===\n")
    print(f"Контроллеров с {LOCALIZED_TRAIT}: {report['localized_trait_count']}")
    for line in report["localized_trait_files"]:
        print(f"  + {line}")

    remaining = report["upper_snake_code_remaining"]
    print(f"\nОстатки UPPER_SNAKE в 'code' => ({len(remaining)}):")
    if remaining:
        for line in remaining:
            print(f"  ! {line}")
    else:
        print("  (нет)")

    missing_human = report["controllers_error_without_human_field"]
    print(f"\nКонтроллеры с error JSON без human_error_message ({len(missing_human)}):")
    for line in missing_human:
        print(f"  ? {line}")

    ae3 = report["ae3_files_with_human_error_message"]
    print(f"\nAE3 файлы с локализацией ({len(ae3)}):")
    for line in ae3:
        print(f"  + {line}")

    exit_code = 1 if remaining else 0
    print("\nИтог:", "PASS" if exit_code == 0 else "WARN — остались UPPER_SNAKE коды в контроллерах")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
