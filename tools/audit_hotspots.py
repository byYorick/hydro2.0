#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple


@dataclass
class SearchSpec:
    label: str
    pattern: str
    paths: List[str]


@dataclass
class CategorySpec:
    name: str
    priority: str
    searches: List[SearchSpec]


def ensure_rg() -> None:
    try:
        subprocess.run(["rg", "--version"], check=True, capture_output=True, text=True)
    except Exception:
        print("rg (ripgrep) not found. Install ripgrep and retry.", file=sys.stderr)
        sys.exit(1)


def run_rg(pattern: str, paths: List[str]) -> List[Tuple[str, int, str]]:
    command = ["rg", "-n", "--no-heading", "-S", "--", pattern, *paths]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "rg failed")
    hits: List[Tuple[str, int, str]] = []
    for line in result.stdout.splitlines():
        try:
            path, line_no, match = line.split(":", 2)
            hits.append((path, int(line_no), match.strip()))
        except ValueError:
            continue
    return hits


def build_specs() -> List[CategorySpec]:
    return [
        CategorySpec(
            name="schema drift",
            priority="P0",
            searches=[
                SearchSpec(
                    label="telemetry_samples references",
                    pattern="telemetry_samples",
                    paths=["backend/", "backend/services/", "firmware/"],
                ),
                SearchSpec(
                    label="metric_type/node_id/channel references",
                    pattern="metric_type|node_id|channel",
                    paths=["backend/", "backend/services/"],
                ),
                SearchSpec(
                    label="telemetry_agg_/telemetry_last references",
                    pattern="telemetry_agg_|telemetry_last",
                    paths=["backend/", "backend/services/"],
                ),
            ],
        ),
        CategorySpec(
            name="realtime",
            priority="P1",
            searches=[
                SearchSpec(
                    label="Laravel broadcasting",
                    pattern="ShouldBroadcast|broadcast|Reverb|PrivateChannel",
                    paths=["backend/laravel/app/"],
                ),
                SearchSpec(
                    label="async task fanout",
                    pattern="create_task\\(|asyncio\\.create_task",
                    paths=["backend/services/"],
                ),
            ],
        ),
        CategorySpec(
            name="retention",
            priority="P1",
            searches=[
                SearchSpec(
                    label="telemetry retention/delete",
                    pattern="DELETE FROM telemetry_samples|retention",
                    paths=["backend/services/", "backend/laravel/database/"],
                ),
            ],
        ),
        CategorySpec(
            name="N+1 (heuristic)",
            priority="P2",
            searches=[
                SearchSpec(
                    label="controller queries (review for eager loading)",
                    pattern="->get\\(|->first\\(|->find\\(",
                    paths=["backend/laravel/app/Http/Controllers/"],
                ),
                SearchSpec(
                    label="relationship access in loops (review)",
                    pattern="foreach \\(|for \\(|->load\\(|->loadMissing\\(",
                    paths=["backend/laravel/app/"],
                ),
            ],
        ),
        CategorySpec(
            name="queue hotpath",
            priority="P2",
            searches=[
                SearchSpec(
                    label="Laravel queue usage",
                    pattern="ShouldQueue|dispatch\\(|dispatchSync\\(|Queue::|Bus::",
                    paths=["backend/laravel/app/"],
                ),
                SearchSpec(
                    label="Python background tasks",
                    pattern="asyncio\\.create_task|run_in_executor|ThreadPoolExecutor",
                    paths=["backend/services/"],
                ),
            ],
        ),
    ]


def render_markdown(report: Dict) -> str:
    lines: List[str] = []
    lines.append("# Audit report: hotspots")
    lines.append("")
    lines.append(f"- generated_at: `{report['generated_at']}`")
    lines.append(f"- root: `{report['root']}`")
    lines.append("")
    lines.append("Heuristics:")
    lines.append("- N+1 and queue hotpath are heuristics and require manual review.")
    lines.append("")
    for category in report["categories"]:
        lines.append(f"## {category['name']} ({category['priority']})")
        lines.append(f"- total_hits: {category['total_hits']}")
        lines.append("")
        for search in category["searches"]:
            lines.append(f"### {search['label']}")
            lines.append(f"- pattern: `{search['pattern']}`")
            lines.append(f"- hits: {len(search['hits'])}")
            if not search["hits"]:
                lines.append("")
                continue
            lines.append("")
            for hit in search["hits"]:
                lines.append(f"- `{hit['file']}:{hit['line']}`")
            lines.append("")
    lines.append("## Raw JSON")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report, ensure_ascii=True, indent=2))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit hotspots for schema drift and runtime risks.")
    parser.add_argument(
        "--output",
        default="artifacts/audit_report.md",
        help="Path to output markdown report",
    )
    args = parser.parse_args()

    ensure_rg()

    root = Path(__file__).resolve().parents[1]
    os.chdir(root)

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "root": str(root),
        "categories": [],
    }

    for category in build_specs():
        cat_payload = {
            "name": category.name,
            "priority": category.priority,
            "total_hits": 0,
            "searches": [],
        }
        for search in category.searches:
            hits = run_rg(search.pattern, search.paths)
            hit_payload = [
                {"file": file, "line": line_no, "match": match}
                for file, line_no, match in hits
            ]
            cat_payload["total_hits"] += len(hit_payload)
            cat_payload["searches"].append(
                {"label": search.label, "pattern": search.pattern, "hits": hit_payload}
            )
        report["categories"].append(cat_payload)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(report))
    print(f"Report written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
