#!/usr/bin/env python3
"""Аудит 100% покрытия i18n: middleware, raw translations, Prometheus alert codes."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

sys.path.insert(0, str(BACKEND / "scripts"))
from audit_i18n_codes import _extract_alert_codes_from_sources, _extract_error_codes_from_sources  # noqa: E402


def _alertname_to_code(name: str) -> str:
    step = re.sub(r"(MQTT)(Broker)", r"\1_\2", name, flags=re.IGNORECASE)
    step = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", step)
    step = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", step)
    code = step.lower()
    if code == "mqttbroker_down":
        return "mqtt_broker_down"
    return code


def _prometheus_alert_codes() -> set[str]:
    codes: set[str] = set()
    for yml in (BACKEND / "configs").rglob("alerts.yml"):
        text = yml.read_text(encoding="utf-8")
        for match in re.finditer(r"^\s*-\s*alert:\s*(\w+)", text, re.MULTILINE):
            codes.add(_alertname_to_code(match.group(1)))
    return codes


def main() -> int:
    print("=== Аудит фазы 4: 100% i18n coverage ===\n")
    ok = True

    middleware = BACKEND / "laravel/app/Http/Middleware/LocalizeApiErrorResponse.php"
    if middleware.is_file():
        print(f"OK middleware: {middleware.relative_to(ROOT)}")
    else:
        print("FAIL: LocalizeApiErrorResponse middleware missing")
        ok = False

    raw_canon = BACKEND / "api_error_raw_translations.json"
    if raw_canon.is_file():
        print(f"OK raw translations: {raw_canon.relative_to(ROOT)}")
    else:
        print("FAIL: api_error_raw_translations.json missing")
        ok = False

    for rel in (
        "laravel/api_error_raw_translations.json",
        "services/common/api_error_raw_translations.json",
    ):
        path = BACKEND / rel
        if path.is_file():
            print(f"OK copy: backend/{rel}")
        else:
            print(f"FAIL: missing copy backend/{rel}")
            ok = False

    catalog_errors = {e["code"] for e in json.loads((BACKEND / "error_codes.json").read_text())["codes"]}
    found_errors = _extract_error_codes_from_sources()
    missing_errors = sorted(found_errors - catalog_errors)
    if missing_errors:
        print(f"\nFAIL error_codes missing ({len(missing_errors)}):")
        for code in missing_errors[:20]:
            print(f"  - {code}")
        ok = False
    else:
        print(f"\nOK all {len(found_errors)} runtime error codes in catalog ({len(catalog_errors)} entries)")

    catalog_alerts = {e["code"] for e in json.loads((BACKEND / "alert_codes.json").read_text())["codes"]}
    prom_codes = _prometheus_alert_codes()
    missing_prom = sorted(prom_codes - catalog_alerts)
    if missing_prom:
        print(f"\nFAIL Prometheus alerts without catalog ({len(missing_prom)}):")
        for code in missing_prom:
            print(f"  - {code}")
        ok = False
    else:
        print(f"OK all {len(prom_codes)} Prometheus alerts in alert_codes.json")

    compose = BACKEND / "docker-compose.dev.yml"
    compose_text = compose.read_text(encoding="utf-8")
    for needle in ("api_error_raw_translations.json:/app/api_error_raw_translations.json", "error_codes.json:/app/error_codes.json"):
        if needle in compose_text:
            print(f"OK compose mount: {needle.split(':')[0]}")
        else:
            print(f"WARN: compose missing mount {needle}")

    print("\nИтог:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
