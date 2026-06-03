#!/usr/bin/env python3
"""Сборка backend/node_error_codes.json (фаза 5) и слияние в error_codes.json.

  python3 backend/scripts/build_node_error_catalog.py
  python3 backend/scripts/build_node_error_catalog.py --check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
NODE_CATALOG = BACKEND / "node_error_codes.json"
ERROR_CATALOG = BACKEND / "error_codes.json"

sys.path.insert(0, str(BACKEND / "scripts"))
from firmware_error_codes import (  # noqa: E402
    FIRMWARE_CODE_DENYLIST,
    FIRMWARE_ERROR_MANIFEST,
    extract_firmware_error_codes,
    manifest_by_code,
    normalize_code,
)


def _humanize(code: str) -> str:
    words = code.replace("-", "_").split("_")
    mapping = {"ec": "EC", "ph": "pH", "ina": "INA", "hmac": "HMAC", "gpio": "GPIO", "irr": "IRR"}
    return " ".join(mapping.get(w.lower(), w.capitalize()) for w in words if w)


def _build_entries() -> list[dict]:
    manifest = manifest_by_code()
    extracted = extract_firmware_error_codes()
    entries: list[dict] = []

    for code in sorted(extracted):
        if code in manifest:
            _, title, message, category = manifest[code]
        else:
            title = _humanize(code)
            message = f"{title}. Проверьте NodeConfig, журнал узла и состояние канала."
            category = "firmware"

        entries.append(
            {
                "code": code,
                "title": title,
                "message": message,
                "category": category,
                "layer": "firmware_mqtt",
            }
        )

    return entries


def _write_node_catalog(entries: list[dict]) -> None:
    payload = {
        "version": "1.0.0",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "description": "Коды error_code из command_response ESP32 и MQTT (фаза 5). Source of truth для слоя узлов.",
        "codes": entries,
    }
    NODE_CATALOG.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _merge_into_error_catalog(entries: list[dict]) -> tuple[int, int]:
    data = json.loads(ERROR_CATALOG.read_text(encoding="utf-8"))
    by_code = {row["code"]: row for row in data.get("codes", [])}
    updated = 0
    node_codes = {entry["code"] for entry in entries}

    for entry in entries:
        code = entry["code"]
        existing = by_code.get(code)
        message = entry["message"]
        title = entry["title"]
        if existing is None:
            by_code[code] = {
                "code": code,
                "title": title,
                "message": message,
                "source_layer": "firmware_mqtt",
            }
            updated += 1
            continue
        if not re.search(r"[А-Яа-яЁё]", str(existing.get("message", ""))):
            existing["message"] = message
            existing["title"] = title
            updated += 1
        existing["source_layer"] = "firmware_mqtt"

    pruned = 0
    for code, row in list(by_code.items()):
        if row.get("source_layer") == "firmware_mqtt" and code not in node_codes:
            del by_code[code]
            pruned += 1
        elif code in FIRMWARE_CODE_DENYLIST and code not in node_codes:
            del by_code[code]
            pruned += 1

    data["codes"] = sorted(by_code.values(), key=lambda row: row["code"])
    data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ERROR_CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return updated, pruned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="только проверка без записи")
    args = parser.parse_args()

    entries = _build_entries()
    missing_manifest = sorted(
        extract_firmware_error_codes() - {normalize_code(row[0]) for row in FIRMWARE_ERROR_MANIFEST}
    )

    if args.check:
        if not NODE_CATALOG.is_file():
            print(f"FAIL: missing {NODE_CATALOG}", file=sys.stderr)
            return 1
        current = {e["code"] for e in json.loads(NODE_CATALOG.read_text())["codes"]}
        expected = {e["code"] for e in entries}
        if current != expected:
            print(f"FAIL: node_error_codes.json out of date ({len(current)} vs {len(expected)})", file=sys.stderr)
            return 1
        print(f"OK node_error_codes.json ({len(entries)} codes)")
        return 0

    _write_node_catalog(entries)
    merged, pruned = _merge_into_error_catalog(entries)
    print(f"Wrote {NODE_CATALOG.relative_to(ROOT)} ({len(entries)} codes)")
    print(f"Merged {merged} entries into {ERROR_CATALOG.relative_to(ROOT)}")
    if pruned:
        print(f"Pruned {pruned} stale firmware_mqtt codes from error_codes.json")
    if missing_manifest:
        print(f"Note: {len(missing_manifest)} extracted codes use auto-translation (add to FIRMWARE_ERROR_MANIFEST):")
        for code in missing_manifest[:10]:
            print(f"  - {code}")
        if len(missing_manifest) > 10:
            print(f"  ... +{len(missing_manifest) - 10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
