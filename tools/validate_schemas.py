#!/usr/bin/env python3
"""Validate JSON Schema files under schemas/ against the Draft 2020-12 meta-schema.

This script is the single place that confirms every file in schemas/ is itself
valid JSON Schema. It runs outside Docker — requires only `jsonschema>=4.23`
installed locally (or in the project venv).

Usage:
    python3 tools/validate_schemas.py [schemas/dir]

Exit codes:
    0 — all schemas valid
    1 — at least one schema failed meta-schema validation
    2 — usage error / environment problem
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover — environment sanity
    print(
        "error: `jsonschema>=4.23` is not installed.\n"
        "       pip install 'jsonschema>=4.23'  (or run inside project venv)",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


def iter_schema_files(schemas_dir: Path) -> list[Path]:
    return sorted(schemas_dir.glob("*.json"))


def validate_one(path: Path) -> list[str]:
    """Return list of error messages for `path`; empty list = valid."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"JSON parse error: {exc}"]

    if not isinstance(payload, dict):
        return ["top-level JSON must be an object"]

    declared = payload.get("$schema")
    expected = "https://json-schema.org/draft/2020-12/schema"
    if declared != expected:
        return [f"$schema must be {expected!r}, got {declared!r}"]

    try:
        Draft202012Validator.check_schema(payload)
    except Exception as exc:  # noqa: BLE001 — want any schema error
        return [f"meta-schema violation: {exc}"]

    return []


def main(argv: list[str]) -> int:
    schemas_dir = Path(argv[1]) if len(argv) > 1 else Path("schemas")
    if not schemas_dir.is_dir():
        print(f"error: {schemas_dir} is not a directory", file=sys.stderr)
        return 2

    files = iter_schema_files(schemas_dir)
    if not files:
        print(f"error: no .json files under {schemas_dir}/", file=sys.stderr)
        return 2

    all_ok = True
    for path in files:
        errors = validate_one(path)
        if errors:
            all_ok = False
            print(f"✗ {path.name}")
            for err in errors:
                print(f"    {err}")
        else:
            print(f"✓ {path.name}")

    print()
    if all_ok:
        print(f"All {len(files)} schema(s) valid.")
        return 0
    print("Validation failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
