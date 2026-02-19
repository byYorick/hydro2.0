#!/usr/bin/env python3
"""Build AE2 S12 gate summary from baseline CSV + decision artifact."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def _load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [row for row in reader]
    if not rows:
        raise ValueError(f"empty baseline csv: {path}")
    return rows


def _read_decision(path: Path) -> str:
    with path.open("r", encoding="utf-8") as fh:
        first = fh.readline().strip()
    if not first.startswith("decision="):
        raise ValueError(f"invalid decision first line: {first!r}")
    return first


def _as_float(row: Dict[str, str], key: str) -> float:
    return float(str(row.get(key, "0")).strip() or "0")


def _render_markdown(
    *,
    mode: str,
    baseline_path: Path,
    decision_path: Path,
    rows: List[Dict[str, str]],
    decision_line: str,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    lines: List[str] = []
    lines.append("# AE2 S12 Gate Summary")
    lines.append("")
    lines.append(f"- Generated-At: {generated_at}")
    lines.append(f"- Mode: {mode}")
    lines.append(f"- Baseline: `{baseline_path}`")
    lines.append(f"- Decision: `{decision_path}`")
    lines.append(f"- Result: `{decision_line}`")
    lines.append("")
    lines.append("| endpoint | count | p50_ms | p95_ms | p99_ms | max_ms |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in rows:
        endpoint = str(row.get("endpoint", "")).strip()
        if not endpoint:
            continue
        count = int(_as_float(row, "count"))
        p50 = _as_float(row, "p50_ms")
        p95 = _as_float(row, "p95_ms")
        p99 = _as_float(row, "p99_ms")
        max_ms = _as_float(row, "max_ms")
        lines.append(f"| {endpoint} | {count} | {p50:.2f} | {p95:.2f} | {p99:.2f} | {max_ms:.2f} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-csv", required=True)
    parser.add_argument("--decision-txt", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--mode", default="remote")
    args = parser.parse_args()

    baseline = Path(args.baseline_csv)
    decision = Path(args.decision_txt)
    output = Path(args.output_md)

    rows = _load_csv(baseline)
    decision_line = _read_decision(decision)
    markdown = _render_markdown(
        mode=str(args.mode).strip().lower() or "remote",
        baseline_path=baseline,
        decision_path=decision,
        rows=rows,
        decision_line=decision_line,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(f"summary_written={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
