#!/usr/bin/env python3
"""Аудит фазы 5: прошивки + MQTT command_response ↔ node_error_codes.json."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
NODE_CATALOG = BACKEND / "node_error_codes.json"
ERROR_CATALOG = BACKEND / "error_codes.json"
MQTT_SPEC = ROOT / "doc_ai" / "03_TRANSPORT_MQTT" / "MQTT_SPEC_FULL.md"

sys.path.insert(0, str(BACKEND / "scripts"))
from firmware_error_codes import extract_firmware_error_codes, normalize_code  # noqa: E402


def _load_codes(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {row["code"]: row for row in data.get("codes", [])}


def _spec_documented_codes() -> set[str]:
    if not MQTT_SPEC.is_file():
        return set()
    found: set[str] = set()
    text = MQTT_SPEC.read_text(encoding="utf-8")
    for match in re.finditer(r'"error_code":\s*"([a-zA-Z0-9_]+)"', text):
        found.add(normalize_code(match.group(1)))
    for match in re.finditer(r'error_code="([a-z_]+)"', text):
        found.add(normalize_code(match.group(1)))
    return found


def main() -> int:
    print("=== Аудит фазы 5: прошивки / MQTT ===\n")
    ok = True

    if not NODE_CATALOG.is_file():
        print(f"FAIL: отсутствует {NODE_CATALOG.relative_to(ROOT)}", file=sys.stderr)
        print("  Запустите: python3 backend/scripts/build_node_error_catalog.py", file=sys.stderr)
        return 1

    node_by_code = _load_codes(NODE_CATALOG)
    error_by_code = _load_codes(ERROR_CATALOG)
    extracted = extract_firmware_error_codes()
    spec_codes = _spec_documented_codes()

    print(f"Извлечено из firmware/MQTT источников: {len(extracted)}")
    print(f"Записей в node_error_codes.json: {len(node_by_code)}")
    print(f"Записей в error_codes.json: {len(error_by_code)}")

    missing_node = sorted(extracted - set(node_by_code))
    if missing_node:
        ok = False
        print(f"\nFAIL: нет в node_error_codes.json ({len(missing_node)}):")
        for code in missing_node[:20]:
            print(f"  - {code}")
        if len(missing_node) > 20:
            print(f"  ... +{len(missing_node) - 20}")

    missing_error = sorted(set(node_by_code) - set(error_by_code))
    if missing_error:
        ok = False
        print(f"\nFAIL: node-коды не слиты в error_codes.json ({len(missing_error)}):")
        for code in missing_error[:20]:
            print(f"  - {code}")

    no_ru = [
        code
        for code, row in node_by_code.items()
        if not re.search(r"[А-Яа-яЁё]", str(row.get("message", "")))
    ]
    if no_ru:
        ok = False
        print(f"\nFAIL: node_error_codes без кириллицы ({len(no_ru)}):")
        for code in no_ru[:15]:
            print(f"  - {code}")

    spec_missing = sorted(spec_codes - set(node_by_code))
    if spec_missing:
        ok = False
        print(f"\nFAIL: коды из MQTT_SPEC без node каталога ({len(spec_missing)}):")
        for code in spec_missing:
            print(f"  - {code}")
    else:
        print(f"\nOK все {len(spec_codes)} error_code из MQTT_SPEC_FULL.md в каталоге")

    doc_ref = "node_error_codes.json"
    if MQTT_SPEC.is_file() and doc_ref not in MQTT_SPEC.read_text(encoding="utf-8"):
        print(f"\nWARN: MQTT_SPEC_FULL.md не ссылается на {doc_ref}")
    else:
        print(f"OK MQTT_SPEC_FULL.md ссылается на каталог узлов")

    catalog_doc = ROOT / "doc_ai" / "04_BACKEND_CORE" / "ERROR_CODE_CATALOG.md"
    if catalog_doc.is_file() and "Фаза 5: прошивки" not in catalog_doc.read_text(encoding="utf-8"):
        print("WARN: ERROR_CODE_CATALOG.md без раздела «Фаза 5: прошивки»")
    else:
        print("OK ERROR_CODE_CATALOG.md содержит фазу 5")

    print("\nИтог:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
