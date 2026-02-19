#!/usr/bin/env python3
"""Machine-checkable invariants for scheduler split facade architecture."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_FILES = [
    "backend/services/scheduler/app/runtime_state.py",
    "backend/services/scheduler/app/bootstrap_sync.py",
    "backend/services/scheduler/app/leader_election.py",
    "backend/services/scheduler/app/dispatch_service.py",
    "backend/services/scheduler/app/reconcile_service.py",
    "backend/services/scheduler/app/internal_enqueue_service.py",
    "backend/services/scheduler/app/runtime_loop.py",
    "backend/services/scheduler/domain/planning_engine.py",
    "backend/services/scheduler/infrastructure/ae_client.py",
]

FACADE_FUNCTIONS = [
    "_load_pending_internal_enqueues",
    "process_internal_enqueued_tasks",
    "ensure_scheduler_leader",
    "ensure_scheduler_bootstrap_ready",
    "send_scheduler_bootstrap_heartbeat",
    "submit_task_to_automation_engine",
    "wait_task_completion",
    "_fetch_task_status_once",
    "recover_active_tasks_after_restart",
    "reconcile_active_tasks",
    "execute_scheduled_task",
    "check_and_execute_schedules",
    "main",
]

REQUIRED_IMPORT_MARKERS = [
    "from app import bootstrap_sync as _bootstrap_sync_mod",
    "from app import dispatch_service as _dispatch_service_mod",
    "from app import internal_enqueue_service as _internal_enqueue_service_mod",
    "from app import leader_election as _leader_election_mod",
    "from app import reconcile_service as _reconcile_service_mod",
    "from app import runtime_loop as _runtime_loop_mod",
    "from domain import planning_engine as _planning_engine_mod",
]


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def main() -> int:
    failures = 0

    for rel in REQUIRED_FILES:
        p = REPO_ROOT / rel
        if not p.exists():
            _fail(f"missing required file: {rel}")
            failures += 1
        else:
            _ok(f"file exists: {rel}")

    main_py = REPO_ROOT / "backend/services/scheduler/main.py"
    if not main_py.exists():
        _fail("missing backend/services/scheduler/main.py")
        return 1

    text = main_py.read_text(encoding="utf-8")

    for marker in REQUIRED_IMPORT_MARKERS:
        if marker not in text:
            _fail(f"missing facade import marker: {marker}")
            failures += 1
        else:
            _ok(f"marker found: {marker}")

    for fn in FACADE_FUNCTIONS:
        pattern = rf"^async def {re.escape(fn)}\(" if fn != "_self_module" else rf"^def {re.escape(fn)}\("
        count = len(re.findall(pattern, text, flags=re.MULTILINE))
        if count != 1:
            _fail(f"function definition count mismatch for {fn}: expected=1 actual={count}")
            failures += 1
        else:
            _ok(f"single definition: {fn}")

    if "async with httpx.AsyncClient" in text:
        _fail("main.py must not create httpx.AsyncClient directly after split")
        failures += 1
    else:
        _ok("main.py does not create httpx.AsyncClient directly")

    line_count = text.count("\n") + 1
    if line_count > 1400:
        _fail(f"main.py too large after split: {line_count} lines")
        failures += 1
    else:
        _ok(f"main.py size check passed: {line_count} lines")

    if failures:
        print(f"\nScheduler split invariants: FAILED ({failures} issue(s))")
        return 1

    print("\nScheduler split invariants: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
