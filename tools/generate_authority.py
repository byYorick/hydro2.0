#!/usr/bin/env python3
"""Phase 7: регенерирует секцию автогенерируемых таблиц параметров
в `doc_ai/04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md` из `schemas/*.v1.json`.

Save invariant: сохраняет manual preamble до маркера
`<!-- BEGIN:generated-parameters -->` и epilogue после `<!-- END:... -->`.

Usage:
    python3 tools/generate_authority.py            # регенерирует (write)
    python3 tools/generate_authority.py --dry-run  # показывает diff без записи
    python3 tools/generate_authority.py --check    # CI guard: fails if diff

Exit codes:
    0  — ok / no changes
    1  — --check и файл out of sync
    2  — error (schemas root not found, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

BEGIN_MARKER = "<!-- BEGIN:generated-parameters -->"
END_MARKER = "<!-- END:generated-parameters -->"


def find_repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in [here.parent, here.parent.parent]:
        if (candidate / "schemas").is_dir() and (candidate / "doc_ai").is_dir():
            return candidate
    raise SystemExit("Cannot locate repo root (must contain schemas/ and doc_ai/)")


def load_schemas(schemas_root: Path) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for f in sorted(schemas_root.glob("*.v1.json")):
        name = f.stem.replace(".v1", "")
        data = json.loads(f.read_text())
        out.append((name, data))
    return out


def format_type(defn: dict[str, Any]) -> str:
    if "enum" in defn and isinstance(defn["enum"], list):
        return "enum: " + " \\| ".join(
            f"`{v}`" if isinstance(v, str) else json.dumps(v)
            for v in defn["enum"]
        )
    if "type" in defn:
        t = defn["type"]
        return " \\| ".join(t) if isinstance(t, list) else str(t)
    if "oneOf" in defn or "anyOf" in defn:
        return "oneOf"
    return "—"


def format_constraints(defn: dict[str, Any]) -> str:
    parts = []
    for k in (
        "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
        "minLength", "maxLength", "minItems", "maxItems", "pattern",
    ):
        if k in defn:
            v = defn[k]
            parts.append(f"{k}={v if isinstance(v, (int, float, str)) else json.dumps(v)}")
    if "format" in defn:
        parts.append(f"format={defn['format']}")
    if "default" in defn:
        v = defn["default"]
        parts.append(f"default={v if isinstance(v, (int, float, str, bool)) else json.dumps(v)}")
    return ", ".join(parts)


def collect_properties(
    node: dict[str, Any], prefix: str, rows: list[tuple[str, str, str, bool]],
) -> None:
    if isinstance(node.get("properties"), dict):
        local_required = set(node.get("required", []) or [])
        for key, child in node["properties"].items():
            if not isinstance(child, dict):
                continue
            path = f"{prefix}.{key}" if prefix else key
            is_required = key in local_required
            if isinstance(child.get("properties"), dict):
                rows.append((path, "object", "", is_required))
                collect_properties(child, path, rows)
            else:
                rows.append((
                    path,
                    format_type(child),
                    format_constraints(child),
                    is_required,
                ))
    elif isinstance(node.get("oneOf"), list):
        for i, variant in enumerate(node["oneOf"]):
            if isinstance(variant, dict):
                collect_properties(variant, f"{prefix}(oneOf#{i})", rows)


def generate_section(schemas_root: Path) -> str:
    lines = [
        "## Автогенерируемые таблицы параметров",
        "",
        "> Секция генерируется `python3 tools/generate_authority.py` из `schemas/*.v1.json`.",
        "> НЕ редактируй вручную — изменения будут перезаписаны.",
        "",
    ]
    for name, schema in load_schemas(schemas_root):
        lines.append(f"### `{name}`")
        lines.append("")
        lines.append("| Path | Type | Constraints | Required |")
        lines.append("| --- | --- | --- | --- |")
        rows: list[tuple[str, str, str, bool]] = []
        collect_properties(schema, "", rows)
        rows.sort(key=lambda r: r[0])
        for path, typ, constraints, required in rows:
            lines.append(
                f"| `{path}` | {typ} | {constraints or '—'} | {'✓' if required else ''} |"
            )
        lines.append("")
    return "\n".join(lines)


def build_full_content(existing: str, generated: str) -> str:
    begin = existing.find(BEGIN_MARKER)
    end = existing.find(END_MARKER)
    if begin == -1 or end == -1:
        preamble = existing.rstrip()
        return (
            f"{preamble}\n\n{BEGIN_MARKER}\n\n{generated}\n{END_MARKER}\n"
        )
    preamble = existing[:begin].rstrip()
    epilogue = existing[end + len(END_MARKER):]
    return (
        f"{preamble}\n\n{BEGIN_MARKER}\n\n{generated}\n{END_MARKER}{epilogue}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="CI guard: exit 1 if diff")
    ap.add_argument("--schemas", default=None, help="Override schemas root")
    ap.add_argument("--output", default=None, help="Override output path")
    args = ap.parse_args()

    root = find_repo_root()
    schemas_root = Path(args.schemas) if args.schemas else root / "schemas"
    output = Path(args.output) if args.output else root / "doc_ai" / "04_BACKEND_CORE" / "AUTOMATION_CONFIG_AUTHORITY.md"

    if not schemas_root.is_dir():
        print(f"❌ schemas root not found: {schemas_root}", file=sys.stderr)
        return 2
    if not output.is_file():
        print(f"❌ output file not found: {output}", file=sys.stderr)
        return 2

    existing = output.read_text()
    generated = generate_section(schemas_root)
    new_content = build_full_content(existing, generated)

    if args.dry_run:
        print(generated)
        return 0

    if existing == new_content:
        print("✓ AUTHORITY.md already up-to-date.")
        return 0

    if args.check:
        print("❌ AUTHORITY.md out of sync with schemas/*.v1.json.", file=sys.stderr)
        print("   Run: python3 tools/generate_authority.py && git add -u && git commit", file=sys.stderr)
        return 1

    output.write_text(new_content)
    delta = len(new_content) - len(existing)
    print(f"✓ AUTHORITY.md updated ({len(existing)} → {len(new_content)} bytes, Δ={delta:+d}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
