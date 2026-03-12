#!/usr/bin/env python3
"""Build AE2 S12 gate metadata artifact (json)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _decision_first_line(path: Path) -> str:
    with path.open("r", encoding="utf-8") as fh:
        line = fh.readline().strip()
    if not line.startswith("decision="):
        raise ValueError(f"invalid decision first line: {line!r}")
    return line


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--baseline-csv", required=True)
    parser.add_argument("--decision-txt", required=True)
    parser.add_argument("--summary-md", default="")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--requests", default="")
    parser.add_argument("--concurrency", default="")
    parser.add_argument("--bootstrap-wait-sec", default="")
    parser.add_argument("--run-bundle-check", default="")
    parser.add_argument("--expect-decision", default="")
    args = parser.parse_args()

    baseline = Path(args.baseline_csv)
    decision = Path(args.decision_txt)
    summary = Path(args.summary_md) if str(args.summary_md).strip() else None
    output = Path(args.output_json)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": str(args.mode).strip().lower(),
        "base_url": str(args.base_url).strip(),
        "artifacts": {
            "baseline_csv": str(baseline),
            "decision_txt": str(decision),
            "summary_md": str(summary) if summary else "",
        },
        "decision": {
            "recorded": _decision_first_line(decision),
            "expected": str(args.expect_decision).strip(),
        },
        "probe_profile": {
            "requests": str(args.requests).strip(),
            "concurrency": str(args.concurrency).strip(),
            "bootstrap_wait_sec": str(args.bootstrap_wait_sec).strip(),
        },
        "checks": {
            "bundle_check_enabled": str(args.run_bundle_check).strip().lower(),
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"metadata_written={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
