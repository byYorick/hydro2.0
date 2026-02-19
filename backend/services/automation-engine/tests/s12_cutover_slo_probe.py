"""Local S12 SLO probe for scheduler cutover/bootstrap ingress.

This script is non-blocking (no hard threshold asserts). It reports latency
percentiles so S12 docs can capture a reproducible local baseline.
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
import time
from pathlib import Path
from typing import Dict, List
from unittest.mock import AsyncMock, Mock

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import api
from api import app, set_command_bus


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = int(math.ceil((p / 100.0) * len(ordered))) - 1
    rank = max(0, min(rank, len(ordered) - 1))
    return ordered[rank]


async def _probe_endpoint(
    client: httpx.AsyncClient,
    *,
    requests_count: int,
    concurrency: int,
    call_name: str,
    call_fn,
) -> Dict[str, float]:
    semaphore = asyncio.Semaphore(concurrency)
    latencies_ms: List[float] = []

    async def _single(i: int) -> None:
        async with semaphore:
            started = time.perf_counter()
            response = await call_fn(i)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if response.status_code != 200:
                raise RuntimeError(f"{call_name}: status={response.status_code}, body={response.text}")
            latencies_ms.append(elapsed_ms)

    await asyncio.gather(*(_single(i) for i in range(requests_count)))
    return {
        "count": float(len(latencies_ms)),
        "p50_ms": _percentile(latencies_ms, 50),
        "p95_ms": _percentile(latencies_ms, 95),
        "p99_ms": _percentile(latencies_ms, 99),
        "max_ms": max(latencies_ms) if latencies_ms else 0.0,
    }


async def main() -> None:
    requests_count = max(20, int(os.getenv("AE2_SLO_PROBE_REQUESTS", "120")))
    concurrency = max(1, int(os.getenv("AE2_SLO_PROBE_CONCURRENCY", "20")))
    output_mode = str(os.getenv("AE2_SLO_PROBE_OUTPUT_MODE", "human")).strip().lower()

    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    old_scheduler_tasks = dict(api._scheduler_tasks)
    old_bootstrap_leases = dict(api._scheduler_bootstrap_leases)
    try:
        api._scheduler_tasks.clear()
        api._scheduler_bootstrap_leases.clear()
        command_bus = Mock()
        command_bus.publish_command = AsyncMock(return_value=True)
        set_command_bus(command_bus, "gh-1")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            bootstrap = await client.post(
                "/scheduler/bootstrap",
                json={
                    "scheduler_id": "scheduler-s12-slo",
                    "scheduler_version": "s12-probe",
                    "protocol_version": "2.0",
                },
            )
            if bootstrap.status_code != 200:
                raise RuntimeError(f"bootstrap failed: status={bootstrap.status_code}, body={bootstrap.text}")
            lease_id = bootstrap.json()["data"]["lease_id"]
            cutover = await _probe_endpoint(
                client,
                requests_count=requests_count,
                concurrency=concurrency,
                call_name="GET /scheduler/cutover/state",
                call_fn=lambda _i: client.get("/scheduler/cutover/state"),
            )
            integration = await _probe_endpoint(
                client,
                requests_count=requests_count,
                concurrency=concurrency,
                call_name="GET /scheduler/integration/contracts",
                call_fn=lambda _i: client.get("/scheduler/integration/contracts"),
            )
            observability = await _probe_endpoint(
                client,
                requests_count=requests_count,
                concurrency=concurrency,
                call_name="GET /scheduler/observability/contracts",
                call_fn=lambda _i: client.get("/scheduler/observability/contracts"),
            )
            heartbeat = await _probe_endpoint(
                client,
                requests_count=requests_count,
                concurrency=concurrency,
                call_name="POST /scheduler/bootstrap/heartbeat",
                call_fn=lambda _i: client.post(
                    "/scheduler/bootstrap/heartbeat",
                    json={"scheduler_id": "scheduler-s12-slo", "lease_id": lease_id},
                ),
            )

        csv_payload = (
            "endpoint,count,p50_ms,p95_ms,p99_ms,max_ms\n"
            f"cutover_state,{int(cutover['count'])},{cutover['p50_ms']:.2f},{cutover['p95_ms']:.2f},{cutover['p99_ms']:.2f},{cutover['max_ms']:.2f}\n"
            f"integration_contracts,{int(integration['count'])},{integration['p50_ms']:.2f},{integration['p95_ms']:.2f},{integration['p99_ms']:.2f},{integration['max_ms']:.2f}\n"
            f"observability_contracts,{int(observability['count'])},{observability['p50_ms']:.2f},{observability['p95_ms']:.2f},{observability['p99_ms']:.2f},{observability['max_ms']:.2f}\n"
            f"bootstrap_heartbeat,{int(heartbeat['count'])},{heartbeat['p50_ms']:.2f},{heartbeat['p95_ms']:.2f},{heartbeat['p99_ms']:.2f},{heartbeat['max_ms']:.2f}"
        )
        if output_mode == "csv":
            print(csv_payload)
        else:
            print("S12 Local SLO Probe Results (milliseconds):")
            print(csv_payload)
    finally:
        api._scheduler_tasks.clear()
        api._scheduler_tasks.update(old_scheduler_tasks)
        api._scheduler_bootstrap_leases.clear()
        api._scheduler_bootstrap_leases.update(old_bootstrap_leases)
        set_command_bus(old_command_bus, old_gh_uid)


if __name__ == "__main__":
    asyncio.run(main())
