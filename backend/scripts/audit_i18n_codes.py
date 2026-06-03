#!/usr/bin/env python3
"""Аудит и дополнение каталогов error_codes.json / alert_codes.json.

Извлекает коды из кодовой базы, сравнивает с каталогами, добавляет русские переводы.

  python3 backend/scripts/audit_i18n_codes.py --check
  python3 backend/scripts/audit_i18n_codes.py --fix
  python3 backend/scripts/audit_i18n_codes.py --fix --sync
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
ERROR_CANONICAL = BACKEND / "error_codes.json"
ALERT_CANONICAL = BACKEND / "alert_codes.json"
SYNC_SCRIPT = BACKEND / "scripts" / "sync_i18n_catalogs.py"

sys.path.insert(0, str(BACKEND / "scripts"))
from i18n_catalog_seeds import (  # noqa: E402
    ALERT_SEEDS,
    ERROR_CODE_DENYLIST,
    ERROR_PREFIX_PATTERNS,
    ERROR_SEEDS,
)

ERROR_CODE_RE = re.compile(
    r"""(?:error_code\s*=\s*["']([a-zA-Z][a-zA-Z0-9_]*)["']"""
    r"""|'code'\s*=>\s*['"]([A-Z][A-Z0-9_]*)['"]"""
    r"""|["']code["']\s*:\s*["']([a-zA-Z][a-zA-Z0-9_]*)["'])""",
    re.MULTILINE,
)
ERROR_CODES_CLASS_RE = re.compile(r"""=\s*["']([a-z][a-z0-9_]*)["']""")
TERMINAL_ERROR_RE = re.compile(
    r"""terminal_error=\(\s*["']([a-z][a-z0-9_]*)["']""",
    re.MULTILINE,
)
SEND_ALERT_CODE_RE = re.compile(
    r"""send_(?:infra|biz)_alert\(\s*[^)]*?\bcode\s*=\s*["']([a-z][a-z0-9_]*)["']""",
    re.MULTILINE | re.DOTALL,
)


def _normalize_code(raw: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", raw.strip().lower()).strip("_")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _humanize(code: str) -> str:
    words = code.replace("-", "_").split("_")
    mapping = {
        "ae3": "AE3",
        "irr": "IRR",
        "ec": "EC",
        "ph": "pH",
        "api": "API",
        "mqtt": "MQTT",
        "hl": "HL",
        "uid": "UID",
        "cmd": "команды",
        "fsm": "FSM",
        "ttl": "TTL",
    }
    parts: list[str] = []
    for word in words:
        low = word.lower()
        if low in mapping:
            parts.append(mapping[low])
        elif low:
            parts.append(word.capitalize())
    return " ".join(parts) if parts else code


def _seed_error_map() -> dict[str, tuple[str, str]]:
    return {code: (title, message) for code, title, message in ERROR_SEEDS}


def _resolve_error_translation(code: str, seeds: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    if code in seeds:
        return seeds[code]
    for prefix, title, message in ERROR_PREFIX_PATTERNS:
        if code.startswith(prefix):
            return title, message
    if code in ERROR_CODE_DENYLIST:
        return None
    if len(code) < 3 or code.isdigit():
        return None
    title = _humanize(code)
    return title, f"{title}. Проверьте конфигурацию, логи сервиса и состояние зоны."


def _extract_error_codes_from_sources() -> set[str]:
    found: set[str] = set()

    def add(raw: str | None) -> None:
        if not raw:
            return
        code = _normalize_code(raw)
        if code and code not in ERROR_CODE_DENYLIST:
            found.add(code)

    # ErrorCodes enum
    errors_py = BACKEND / "services/automation-engine/ae3lite/domain/errors.py"
    if errors_py.is_file():
        for match in ERROR_CODES_CLASS_RE.finditer(errors_py.read_text(encoding="utf-8")):
            add(match.group(1))

    # workflow terminal_error tuples
    topology_py = (
        BACKEND / "services/automation-engine/ae3lite/application/services/workflow_topology.py"
    )
    if topology_py.is_file():
        for match in TERMINAL_ERROR_RE.finditer(topology_py.read_text(encoding="utf-8")):
            add(match.group(1))

    scan_roots = [
        BACKEND / "services",
        BACKEND / "laravel" / "app",
        ROOT / "tests" / "node_sim",
        ROOT / "firmware",
    ]
    for root in scan_roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".php", ".c", ".h"}:
                continue
            if "/vendor/" in str(path) or "/node_modules/" in str(path):
                continue
            if path.name.startswith("test_") and "node_sim" not in str(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for m in ERROR_CODE_RE.finditer(text):
                add(m.group(1) or m.group(2) or m.group(3))

    # execute_task constants
    for const in (
        "ae3_task_execution_timeout",
        "ae3_zone_lease_lost",
        "infra_ae3_snapshot_retry_scheduled",
        "ae3_snapshot_retry_exhausted",
        "infra_ae3_command_send_retry_scheduled",
        "ae3_command_send_retry_exhausted",
    ):
        add(const)

    return found


def _alert_name_to_code(name: str) -> str:
    step = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    step = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", step)
    return step.lower()


def _extract_alert_codes_from_sources() -> set[str]:
    found: set[str] = set()

    for alerts_path in (
        BACKEND / "configs/dev/prometheus/alerts.yml",
        BACKEND / "configs/prod/prometheus/alerts.yml",
    ):
        if not alerts_path.is_file():
            continue
        doc = yaml.safe_load(alerts_path.read_text(encoding="utf-8"))
        for group in doc.get("groups", []):
            for rule in group.get("rules", []):
                name = rule.get("alert")
                if name:
                    found.add(_alert_name_to_code(name))

    services = BACKEND / "services"
    if services.is_dir():
        for path in services.rglob("*.py"):
            if path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for m in SEND_ALERT_CODE_RE.finditer(text):
                found.add(_normalize_code(m.group(1)))

    return found


def _seed_alert_entry(
    code: str,
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    for seed in ALERT_SEEDS:
        if seed[0] == code:
            return {
                "code": code,
                "source": seed[6],
                "category": seed[5],
                "severity": seed[4],
                "title": seed[1],
                "description": seed[2],
                "recommendation": seed[3],
                "node_related": False,
            }
    if existing:
        return dict(existing)
    title = _humanize(code)
    is_biz = code.startswith("biz_")
    return {
        "code": code,
        "source": "biz" if is_biz else "infra",
        "category": "operations",
        "severity": "warning",
        "title": title,
        "description": f"{title}: требуется проверка по журналам и метрикам.",
        "recommendation": "Проверьте логи сервисов, метрики Prometheus и состояние зоны.",
        "node_related": is_biz,
    }


def _merge_errors(found: set[str], fix: bool) -> tuple[list[str], int]:
    seeds = _seed_error_map()
    data = _load_json(ERROR_CANONICAL)
    by_code = {e["code"]: e for e in data.get("codes", [])}
    missing: list[str] = []

    for code in sorted(found):
        if code in by_code:
            entry = by_code[code]
            if seeds.get(code) and (
                not str(entry.get("message", "")).strip()
                or not re.search(r"[А-Яа-яЁё]", str(entry.get("message", "")))
            ):
                if fix:
                    title, message = seeds[code]
                    entry["title"] = title
                    entry["message"] = message
            continue
        translation = _resolve_error_translation(code, seeds)
        if translation is None:
            continue
        missing.append(code)
        if fix:
            title, message = translation
            by_code[code] = {"code": code, "title": title, "message": message}

    if fix:
        data["codes"] = sorted(by_code.values(), key=lambda x: x["code"])
        data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_json(ERROR_CANONICAL, data)

    return missing, len(missing)


def _merge_alerts(found: set[str], fix: bool) -> tuple[list[str], int]:
    data = _load_json(ALERT_CANONICAL)
    by_code = {e["code"]: e for e in data.get("codes", [])}
    missing: list[str] = []

    for code in sorted(found):
        if code in by_code:
            entry = by_code[code]
            if fix and not re.search(r"[А-Яа-яЁё]", str(entry.get("title", ""))):
                updated = _seed_alert_entry(code, entry)
                by_code[code] = updated
            continue
        missing.append(code)
        if fix:
            by_code[code] = _seed_alert_entry(code, None)

    if fix:
        data["codes"] = sorted(by_code.values(), key=lambda x: x["code"])
        data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_json(ALERT_CANONICAL, data)

    return missing, len(missing)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="только проверка, exit 1 при пропусках")
    parser.add_argument("--fix", action="store_true", help="дописать недостающие переводы в каталоги")
    parser.add_argument("--sync", action="store_true", help="после --fix запустить sync_i18n_catalogs.py")
    args = parser.parse_args()

    if not args.check and not args.fix:
        args.check = True

    error_found = _extract_error_codes_from_sources()
    alert_found = _extract_alert_codes_from_sources()

    err_missing, err_count = _merge_errors(error_found, fix=args.fix)
    alert_missing, alert_count = _merge_alerts(alert_found, fix=args.fix)

    catalog_errors = {e["code"] for e in _load_json(ERROR_CANONICAL).get("codes", [])}
    catalog_alerts = {e["code"] for e in _load_json(ALERT_CANONICAL).get("codes", [])}

    print(f"Извлечено error_code из кода: {len(error_found)}")
    print(f"Записей в error_codes.json: {len(catalog_errors)}")
    print(f"Извлечено alert code из кода/Prometheus: {len(alert_found)}")
    print(f"Записей в alert_codes.json: {len(catalog_alerts)}")

    if err_missing and not args.fix:
        print(f"\nНет в error_codes.json ({len(err_missing)}):")
        for code in err_missing[:50]:
            print(f"  - {code}")
        if len(err_missing) > 50:
            print(f"  ... и ещё {len(err_missing) - 50}")

    if alert_missing and not args.fix:
        print(f"\nНет в alert_codes.json ({len(alert_missing)}):")
        for code in alert_missing[:50]:
            print(f"  - {code}")
        if len(alert_missing) > 50:
            print(f"  ... и ещё {len(alert_missing) - 50}")

    if args.fix:
        print(f"\nДобавлено/обновлено error codes: {err_count}")
        print(f"Добавлено/обновлено alert codes: {alert_count}")
        if args.sync and SYNC_SCRIPT.is_file():
            subprocess.run([sys.executable, str(SYNC_SCRIPT)], check=True)

    ok = not err_missing and not alert_missing
    if args.check and not ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
