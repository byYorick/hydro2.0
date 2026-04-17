#!/usr/bin/env python3
"""Validates schemas/zone_correction_defaults.json against schemas/zone_correction.v1.json
and optionally generates a PHP array representation for comparison with
ZoneCorrectionConfigCatalog::defaults().

Single source of truth flow:
    zone_correction_defaults.json  ← edit here
        → validated by zone_correction.v1.json (jsonschema)
        → PHP ZoneCorrectionConfigCatalog::defaults() must match (checked by PHP unit test)

Usage:
    python3 tools/generate_zone_correction_catalog.py           # validate + summary
    python3 tools/generate_zone_correction_catalog.py --check  # CI gate: exit 1 on failure
    python3 tools/generate_zone_correction_catalog.py --output=php  # print PHP array

Exit codes:
    0  — defaults valid against schema
    1  — validation failed (schema violation or file not found)
    2  — usage / environment error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, ValidationError
except ImportError as exc:
    print(
        "error: `jsonschema>=4.23` is not installed.\n"
        "       pip install 'jsonschema>=4.23'  (or run inside project venv)",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


# ---------------------------------------------------------------------------
# Repo-root discovery
# ---------------------------------------------------------------------------

def find_repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in [here.parent, here.parent.parent]:
        if (candidate / "schemas").is_dir() and (candidate / "tools").is_dir():
            return candidate
    # fallback: cwd
    cwd = Path.cwd()
    if (cwd / "schemas").is_dir():
        return cwd
    raise SystemExit(
        "error: cannot locate repo root (directory must contain schemas/ and tools/)"
    )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_defaults(defaults: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Return list of human-readable error messages; empty = valid."""
    validator = Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}"
        for e in sorted(validator.iter_errors(defaults), key=lambda e: e.absolute_path)
    ]


# ---------------------------------------------------------------------------
# PHP array generation
# ---------------------------------------------------------------------------

def _php_value(value: Any, indent: int) -> str:
    """Recursively format a Python value as PHP array syntax."""
    pad = "    " * indent
    inner_pad = "    " * (indent + 1)

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # Preserve trailing .0 for PHP float literals
        s = repr(value)
        if "." not in s and "e" not in s.lower():
            s += ".0"
        return s
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, list):
        if not value:
            return "[]"
        items = ", ".join(_php_value(v, 0) for v in value)
        return f"[{items}]"
    if isinstance(value, dict):
        if not value:
            return "[]"
        lines = [f"["]
        for k, v in value.items():
            rendered = _php_value(v, indent + 1)
            lines.append(f"{inner_pad}'{k}' => {rendered},")
        lines.append(f"{pad}]")
        return "\n".join(lines)
    return repr(value)


def generate_php_defaults(defaults: dict[str, Any]) -> str:
    """Generate the body of ZoneCorrectionConfigCatalog::defaults()."""
    lines = [
        "    // AUTO-GENERATED from schemas/zone_correction_defaults.json",
        "    // Run: python3 tools/generate_zone_correction_catalog.py --output=php",
        "    public static function defaults(): array",
        "    {",
        "        return " + _php_value(defaults, 2) + ";",
        "    }",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Validate zone_correction_defaults.json against zone_correction.v1.json"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI mode: exit 1 if defaults don't conform to schema",
    )
    parser.add_argument(
        "--output",
        choices=["php", "json"],
        default=None,
        help="Print generated representation (php | json) without running CI check",
    )
    args = parser.parse_args(argv[1:])

    root = find_repo_root()
    defaults_path = root / "schemas" / "zone_correction_defaults.json"
    schema_path = root / "schemas" / "zone_correction.v1.json"

    # --- load files ---
    missing = [p for p in [defaults_path, schema_path] if not p.exists()]
    if missing:
        for p in missing:
            print(f"error: file not found: {p}", file=sys.stderr)
        return 1

    try:
        defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: JSON parse error: {exc}", file=sys.stderr)
        return 1

    # --- validate ---
    errors = validate_defaults(defaults, schema)

    if args.output == "php":
        print(generate_php_defaults(defaults))
        return 0

    if args.output == "json":
        print(json.dumps(defaults, indent=2, ensure_ascii=False))
        return 0

    # --- report ---
    if errors:
        print(f"✗ zone_correction_defaults.json — {len(errors)} error(s):")
        for err in errors:
            print(f"    {err}")
        if args.check:
            print(
                "\nFix schemas/zone_correction_defaults.json or zone_correction.v1.json,"
                "\nthen re-run: python3 tools/generate_zone_correction_catalog.py"
            )
            return 1
        return 1  # also fail without --check so Make knows

    print(
        f"✓ zone_correction_defaults.json valid against zone_correction.v1.json"
        f"\n  ({_count_leaves(defaults)} leaf values checked)"
    )
    return 0


def _count_leaves(obj: Any) -> int:
    if isinstance(obj, dict):
        return sum(_count_leaves(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_count_leaves(v) for v in obj)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
