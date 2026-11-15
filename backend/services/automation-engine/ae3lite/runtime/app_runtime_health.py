"""app runtime health: explicit dependencies and invocation data."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import httpx
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class AppRuntimeHealthPorts:
    hl_ready_check_cache: Callable[..., Any]
    hl_ready_check_timeout_sec: Callable[..., Any]
    hl_ready_check_ttl_sec: Callable[..., Any]
    critical_background_tasks_health: Callable[..., Any]
    probe_history_logger_ready: Callable[..., Any]
    fetch: Callable[..., Any]
    logger: Callable[..., Any]


class AppRuntimeHealth:
    def __init__(self, ports: AppRuntimeHealthPorts) -> None:
        self._ports = ports

    async def probe_history_logger_ready(self, *, base_url: str) -> tuple[bool, str]:
        now = time.monotonic()
        cached_at = float(self._ports.hl_ready_check_cache()["monotonic_at"])
        if now - cached_at < self._ports.hl_ready_check_ttl_sec():
            return bool(self._ports.hl_ready_check_cache()["ok"]), str(self._ports.hl_ready_check_cache()["reason"])

        ok = False
        reason = "history_logger_unreachable"
        try:
            async with httpx.AsyncClient(timeout=self._ports.hl_ready_check_timeout_sec()) as client:
                response = await client.get(f"{str(base_url).rstrip('/')}/health")
            if response.status_code == 200:
                ok = True
                reason = "ok"
        except Exception as exc:
            self._ports.logger().warning(
                "Проверка готовности AE3 через HL probe завершилась ошибкой: %s", exc, exc_info=True
            )

        self._ports.hl_ready_check_cache()["monotonic_at"] = now
        self._ports.hl_ready_check_cache()["ok"] = ok
        self._ports.hl_ready_check_cache()["reason"] = reason
        return ok, reason

    def critical_background_tasks_health(self, background_tasks: Mapping[str, Any]) -> tuple[bool, str]:
        if not background_tasks:
            return True, "ok"
        for task_name, task in background_tasks.items():
            if task is None:
                return False, f"{task_name}:missing"
            done = getattr(task, "done", None)
            if not callable(done):
                return False, f"{task_name}:invalid"
            if not done():
                continue
            cancelled = getattr(task, "cancelled", None)
            if callable(cancelled) and cancelled():
                return False, f"{task_name}:cancelled"
            exception = getattr(task, "exception", None)
            if callable(exception):
                try:
                    exc = exception()
                except Exception:
                    return False, f"{task_name}:exception_unknown"
                if exc is not None:
                    return False, f"{task_name}:crashed:{type(exc).__name__}"
            return False, f"{task_name}:stopped"
        return True, "ok"

    def bind_health_routes(self, *, app: Any, runtime_config: Any, bundle: Any) -> Any:
        @app.get("/health/live")
        async def health_live() -> dict[str, Any]:
            return {"status": "ok", "service": "automation-engine"}

        @app.get("/health/ready")
        async def health_ready() -> Any:
            db_ready = True
            db_reason = "ok"
            try:
                await self._ports.fetch("SELECT 1 AS ready")
            except Exception as exc:
                db_ready = False
                db_reason = type(exc).__name__
                self._ports.logger().warning(
                    "Проверка готовности AE3 через DB probe завершилась ошибкой: %s", exc, exc_info=True
                )

            worker_ok, worker_reason = await bundle.worker.drain_health()
            critical_ok, critical_reason = self._ports.critical_background_tasks_health(
                getattr(app.state, "ae3_critical_background_tasks", {}),
            )
            hl_ready, hl_reason = await self._ports.probe_history_logger_ready(
                base_url=runtime_config.history_logger_url
            )
            all_ok = db_ready and worker_ok and critical_ok and hl_ready
            payload = {
                "status": "ok" if all_ok else "degraded",
                "service": "automation-engine",
                "ready": all_ok,
                "checks": {
                    "db": {"ok": db_ready, "reason": db_reason},
                    "worker": {"ok": worker_ok, "reason": worker_reason},
                    "critical_background_tasks": {"ok": critical_ok, "reason": critical_reason},
                    "history_logger": {"ok": hl_ready, "reason": hl_reason},
                },
            }
            return payload if all_ok else JSONResponse(status_code=503, content=payload)
