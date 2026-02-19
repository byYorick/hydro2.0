"""S12 release decision helper based on SLO CSV baseline artifact."""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class EndpointThreshold:
    min_count: int
    max_p95_ms: float
    max_p99_ms: float


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _build_thresholds() -> Dict[str, EndpointThreshold]:
    return {
        "cutover_state": EndpointThreshold(
            min_count=_env_int("AE2_SLO_MIN_COUNT_CUTOVER_STATE", 120),
            max_p95_ms=_env_float("AE2_SLO_MAX_P95_CUTOVER_STATE_MS", 60.0),
            max_p99_ms=_env_float("AE2_SLO_MAX_P99_CUTOVER_STATE_MS", 80.0),
        ),
        "integration_contracts": EndpointThreshold(
            min_count=_env_int("AE2_SLO_MIN_COUNT_INTEGRATION_CONTRACTS", 120),
            max_p95_ms=_env_float("AE2_SLO_MAX_P95_INTEGRATION_CONTRACTS_MS", 70.0),
            max_p99_ms=_env_float("AE2_SLO_MAX_P99_INTEGRATION_CONTRACTS_MS", 90.0),
        ),
        "observability_contracts": EndpointThreshold(
            min_count=_env_int("AE2_SLO_MIN_COUNT_OBSERVABILITY_CONTRACTS", 120),
            max_p95_ms=_env_float("AE2_SLO_MAX_P95_OBSERVABILITY_CONTRACTS_MS", 90.0),
            max_p99_ms=_env_float("AE2_SLO_MAX_P99_OBSERVABILITY_CONTRACTS_MS", 120.0),
        ),
        "bootstrap_heartbeat": EndpointThreshold(
            min_count=_env_int("AE2_SLO_MIN_COUNT_BOOTSTRAP_HEARTBEAT", 120),
            max_p95_ms=_env_float("AE2_SLO_MAX_P95_BOOTSTRAP_HEARTBEAT_MS", 250.0),
            max_p99_ms=_env_float("AE2_SLO_MAX_P99_BOOTSTRAP_HEARTBEAT_MS", 320.0),
        ),
    }


def _load_csv_rows(raw: str) -> List[Dict[str, str]]:
    reader = csv.DictReader(io.StringIO(raw))
    rows = [row for row in reader]
    if not rows:
        raise ValueError("empty_csv")
    return rows


def _parse_metrics(rows: List[Dict[str, str]]) -> Dict[str, Tuple[int, float, float]]:
    result: Dict[str, Tuple[int, float, float]] = {}
    for row in rows:
        endpoint = str(row.get("endpoint", "")).strip()
        if not endpoint:
            continue
        count = int(float(str(row.get("count", "0")).strip() or "0"))
        p95 = float(str(row.get("p95_ms", "0")).strip() or "0")
        p99 = float(str(row.get("p99_ms", "0")).strip() or "0")
        result[endpoint] = (count, p95, p99)
    return result


def _evaluate(metrics: Dict[str, Tuple[int, float, float]], thresholds: Dict[str, EndpointThreshold]) -> Tuple[str, List[str]]:
    violations: List[str] = []
    for endpoint, threshold in thresholds.items():
        if endpoint not in metrics:
            violations.append(f"{endpoint}:missing")
            continue
        count, p95, p99 = metrics[endpoint]
        if count < threshold.min_count:
            violations.append(f"{endpoint}:count<{threshold.min_count} ({count})")
        if p95 > threshold.max_p95_ms:
            violations.append(f"{endpoint}:p95>{threshold.max_p95_ms} ({p95:.2f})")
        if p99 > threshold.max_p99_ms:
            violations.append(f"{endpoint}:p99>{threshold.max_p99_ms} ({p99:.2f})")
    decision = "ALLOW_FULL_ROLLOUT" if not violations else "HOLD_AND_INVESTIGATE"
    return decision, violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-path", default="", help="Path to SLO CSV artifact.")
    parser.add_argument("--stdin", action="store_true", help="Read CSV payload from stdin.")
    args = parser.parse_args()

    if args.stdin:
        raw = sys.stdin.read()
    elif args.csv_path:
        with open(args.csv_path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    else:
        raise ValueError("csv_input_required")

    rows = _load_csv_rows(raw)
    metrics = _parse_metrics(rows)
    thresholds = _build_thresholds()
    decision, violations = _evaluate(metrics, thresholds)

    print(f"decision={decision}")
    for endpoint in thresholds.keys():
        count, p95, p99 = metrics.get(endpoint, (0, 0.0, 0.0))
        t = thresholds[endpoint]
        print(
            f"{endpoint}: count={count} (min {t.min_count}), "
            f"p95={p95:.2f}ms (max {t.max_p95_ms:.2f}), "
            f"p99={p99:.2f}ms (max {t.max_p99_ms:.2f})"
        )
    if violations:
        print("violations:")
        for item in violations:
            print(f"- {item}")
    return 0 if decision == "ALLOW_FULL_ROLLOUT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
