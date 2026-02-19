"""S12 SLO probe for scheduler cutover/bootstrap ingress.

Supports two modes:
- `local` (default): in-process ASGI probe against local app.
- `remote`: real HTTP probe against a staging base URL.

The script is non-blocking (no hard threshold asserts). It reports latency
percentiles so S12 docs can capture reproducible baselines.
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = int(math.ceil((p / 100.0) * len(ordered))) - 1
    rank = max(0, min(rank, len(ordered) - 1))
    return ordered[rank]


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, str(default))).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _build_base_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    auth = str(os.getenv("AE2_SLO_PROBE_AUTHORIZATION", "")).strip()
    if auth:
        headers["Authorization"] = auth
    return headers


def _build_call_headers(base_headers: Dict[str, str], *, trace_prefix: str, call_name: str, index: int) -> Dict[str, str]:
    headers = dict(base_headers)
    if trace_prefix:
        headers["X-Trace-Id"] = f"{trace_prefix}-{call_name}-{index}"
    return headers


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


async def _obtain_lease_id(
    client: httpx.AsyncClient,
    *,
    base_headers: Dict[str, str],
    trace_prefix: str,
    scheduler_id: str,
    scheduler_version: str,
    protocol_version: str,
    bootstrap_wait_sec: float,
    bootstrap_poll_default_sec: float,
) -> str:
    started = time.perf_counter()
    attempt = 0
    while True:
        attempt += 1
        headers = _build_call_headers(
            base_headers,
            trace_prefix=trace_prefix,
            call_name="bootstrap",
            index=attempt,
        )
        response = await client.post(
            "/scheduler/bootstrap",
            headers=headers,
            json={
                "scheduler_id": scheduler_id,
                "scheduler_version": scheduler_version,
                "protocol_version": protocol_version,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if response.status_code != 200:
            raise RuntimeError(f"bootstrap failed: status={response.status_code}, body={response.text}")
        payload = response.json().get("data") or {}
        status = str(payload.get("bootstrap_status") or "").strip().lower()
        if status == "ready":
            lease_id = str(payload.get("lease_id") or "").strip()
            if not lease_id:
                raise RuntimeError("bootstrap status=ready but lease_id is empty")
            return lease_id
        if status == "deny":
            reason = str(payload.get("reason") or payload.get("readiness_reason") or "unknown")
            raise RuntimeError(f"bootstrap denied: reason={reason}")
        elapsed = time.perf_counter() - started
        if elapsed >= bootstrap_wait_sec:
            reason = str(payload.get("reason") or payload.get("readiness_reason") or "timeout")
            raise RuntimeError(f"bootstrap wait timeout: reason={reason}, waited={elapsed:.2f}s")
        poll_sec = float(payload.get("poll_interval_sec") or bootstrap_poll_default_sec)
        await asyncio.sleep(max(0.05, poll_sec))


def _build_csv_payload(
    *,
    cutover: Dict[str, float],
    integration: Dict[str, float],
    observability: Dict[str, float],
    heartbeat: Dict[str, float],
) -> str:
    return (
        "endpoint,count,p50_ms,p95_ms,p99_ms,max_ms\n"
        f"cutover_state,{int(cutover['count'])},{cutover['p50_ms']:.2f},{cutover['p95_ms']:.2f},{cutover['p99_ms']:.2f},{cutover['max_ms']:.2f}\n"
        f"integration_contracts,{int(integration['count'])},{integration['p50_ms']:.2f},{integration['p95_ms']:.2f},{integration['p99_ms']:.2f},{integration['max_ms']:.2f}\n"
        f"observability_contracts,{int(observability['count'])},{observability['p50_ms']:.2f},{observability['p95_ms']:.2f},{observability['p99_ms']:.2f},{observability['max_ms']:.2f}\n"
        f"bootstrap_heartbeat,{int(heartbeat['count'])},{heartbeat['p50_ms']:.2f},{heartbeat['p95_ms']:.2f},{heartbeat['p99_ms']:.2f},{heartbeat['max_ms']:.2f}"
    )


async def _run_probe(
    client: httpx.AsyncClient,
    *,
    requests_count: int,
    concurrency: int,
    base_headers: Dict[str, str],
    trace_prefix: str,
    scheduler_id: str,
    scheduler_version: str,
    protocol_version: str,
    bootstrap_wait_sec: float,
    bootstrap_poll_default_sec: float,
) -> str:
    lease_id = await _obtain_lease_id(
        client,
        base_headers=base_headers,
        trace_prefix=trace_prefix,
        scheduler_id=scheduler_id,
        scheduler_version=scheduler_version,
        protocol_version=protocol_version,
        bootstrap_wait_sec=bootstrap_wait_sec,
        bootstrap_poll_default_sec=bootstrap_poll_default_sec,
    )
    cutover = await _probe_endpoint(
        client,
        requests_count=requests_count,
        concurrency=concurrency,
        call_name="GET /scheduler/cutover/state",
        call_fn=lambda i: client.get(
            "/scheduler/cutover/state",
            headers=_build_call_headers(base_headers, trace_prefix=trace_prefix, call_name="cutover", index=i),
        ),
    )
    integration = await _probe_endpoint(
        client,
        requests_count=requests_count,
        concurrency=concurrency,
        call_name="GET /scheduler/integration/contracts",
        call_fn=lambda i: client.get(
            "/scheduler/integration/contracts",
            headers=_build_call_headers(base_headers, trace_prefix=trace_prefix, call_name="integration", index=i),
        ),
    )
    observability = await _probe_endpoint(
        client,
        requests_count=requests_count,
        concurrency=concurrency,
        call_name="GET /scheduler/observability/contracts",
        call_fn=lambda i: client.get(
            "/scheduler/observability/contracts",
            headers=_build_call_headers(base_headers, trace_prefix=trace_prefix, call_name="observability", index=i),
        ),
    )
    heartbeat = await _probe_endpoint(
        client,
        requests_count=requests_count,
        concurrency=concurrency,
        call_name="POST /scheduler/bootstrap/heartbeat",
        call_fn=lambda i: client.post(
            "/scheduler/bootstrap/heartbeat",
            headers=_build_call_headers(base_headers, trace_prefix=trace_prefix, call_name="heartbeat", index=i),
            json={"scheduler_id": scheduler_id, "lease_id": lease_id},
        ),
    )
    return _build_csv_payload(
        cutover=cutover,
        integration=integration,
        observability=observability,
        heartbeat=heartbeat,
    )


async def _local_probe_fetch_stub(_query: str, *_args) -> List[Dict[str, int]]:
    return [{"ready": 1}]


async def _local_probe_noop(*_args, **_kwargs) -> None:
    return None


async def main() -> None:
    requests_count = max(20, int(os.getenv("AE2_SLO_PROBE_REQUESTS", "120")))
    concurrency = max(1, int(os.getenv("AE2_SLO_PROBE_CONCURRENCY", "20")))
    output_mode = str(os.getenv("AE2_SLO_PROBE_OUTPUT_MODE", "human")).strip().lower()
    probe_mode = str(os.getenv("AE2_SLO_PROBE_MODE", "local")).strip().lower()
    base_url = str(os.getenv("AE2_SLO_PROBE_BASE_URL", "")).strip().rstrip("/")
    trace_prefix = str(os.getenv("AE2_SLO_PROBE_TRACE_ID_PREFIX", "ae2-s12-slo")).strip()
    scheduler_id = str(os.getenv("AE2_SLO_PROBE_SCHEDULER_ID", "scheduler-s12-slo")).strip()
    scheduler_version = str(os.getenv("AE2_SLO_PROBE_SCHEDULER_VERSION", "s12-probe")).strip()
    protocol_version = str(os.getenv("AE2_SLO_PROBE_PROTOCOL_VERSION", "2.0")).strip()
    bootstrap_wait_sec = max(0.5, float(os.getenv("AE2_SLO_PROBE_BOOTSTRAP_WAIT_SEC", "30")))
    bootstrap_poll_default_sec = max(0.05, float(os.getenv("AE2_SLO_PROBE_BOOTSTRAP_POLL_SEC", "1")))
    http_timeout_sec = max(1.0, float(os.getenv("AE2_SLO_PROBE_HTTP_TIMEOUT_SEC", "15")))
    verify_tls = _env_bool("AE2_SLO_PROBE_VERIFY_TLS", True)
    base_headers = _build_base_headers()

    if probe_mode not in {"local", "remote"}:
        raise ValueError("AE2_SLO_PROBE_MODE must be local or remote")
    if probe_mode == "remote" and not base_url:
        raise ValueError("AE2_SLO_PROBE_BASE_URL is required for remote mode")
    effective_base_url: Optional[str] = base_url if probe_mode == "remote" else None

    csv_payload = ""
    if probe_mode == "local":
        import api as api_module
        from api import app, set_command_bus

        old_command_bus = api_module._command_bus
        old_gh_uid = api_module._gh_uid
        old_fetch = api_module.fetch
        old_create_scheduler_log = api_module.create_scheduler_log
        old_send_infra_alert = api_module.send_infra_alert
        old_scheduler_tasks = dict(api_module._scheduler_tasks)
        old_bootstrap_leases = dict(api_module._scheduler_bootstrap_leases)
        try:
            api_module._scheduler_tasks.clear()
            api_module._scheduler_bootstrap_leases.clear()
            api_module.fetch = _local_probe_fetch_stub
            api_module.create_scheduler_log = _local_probe_noop
            api_module.send_infra_alert = _local_probe_noop
            command_bus = Mock()
            command_bus.publish_command = AsyncMock(return_value=True)
            set_command_bus(command_bus, "gh-1")

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                timeout=http_timeout_sec,
            ) as client:
                csv_payload = await _run_probe(
                    client,
                    requests_count=requests_count,
                    concurrency=concurrency,
                    base_headers=base_headers,
                    trace_prefix=trace_prefix,
                    scheduler_id=scheduler_id,
                    scheduler_version=scheduler_version,
                    protocol_version=protocol_version,
                    bootstrap_wait_sec=bootstrap_wait_sec,
                    bootstrap_poll_default_sec=bootstrap_poll_default_sec,
                )
        finally:
            api_module._scheduler_tasks.clear()
            api_module._scheduler_tasks.update(old_scheduler_tasks)
            api_module._scheduler_bootstrap_leases.clear()
            api_module._scheduler_bootstrap_leases.update(old_bootstrap_leases)
            api_module.fetch = old_fetch
            api_module.create_scheduler_log = old_create_scheduler_log
            api_module.send_infra_alert = old_send_infra_alert
            set_command_bus(old_command_bus, old_gh_uid)
    else:
        async with httpx.AsyncClient(
            base_url=str(effective_base_url),
            timeout=http_timeout_sec,
            verify=verify_tls,
        ) as client:
            csv_payload = await _run_probe(
                client,
                requests_count=requests_count,
                concurrency=concurrency,
                base_headers=base_headers,
                trace_prefix=trace_prefix,
                scheduler_id=scheduler_id,
                scheduler_version=scheduler_version,
                protocol_version=protocol_version,
                bootstrap_wait_sec=bootstrap_wait_sec,
                bootstrap_poll_default_sec=bootstrap_poll_default_sec,
            )

    if output_mode == "csv":
        print(csv_payload)
    else:
        if probe_mode == "remote":
            print(f"S12 Remote SLO Probe Results (base_url={effective_base_url}):")
        else:
            print("S12 Local SLO Probe Results (in-process ASGI):")
        print(csv_payload)


if __name__ == "__main__":
    asyncio.run(main())
