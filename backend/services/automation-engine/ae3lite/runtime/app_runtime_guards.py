"""app runtime guards: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Request

from ae3lite.api.security import validate_scheduler_security_baseline
from ae3lite.api.validation import validate_scheduler_zone
from common.trace_context import extract_trace_id_from_headers


@dataclass(frozen=True)
class AppRuntimeGuardsPorts:
    fetch: Callable[..., Any]
    logger: Callable[..., Any]


class AppRuntimeGuards:
    def __init__(self, ports: AppRuntimeGuardsPorts) -> None:
        self._ports = ports

    def build_ingress_guards(self, *, runtime_config: Any) -> Any:
        async def _validate_scheduler_zone(zone_id: int) -> None:
            await validate_scheduler_zone(zone_id, fetch_fn=self._ports.fetch, logger=self._ports.logger())

        async def _validate_scheduler_security_baseline(request: Request) -> None:
            validate_scheduler_security_baseline(
                headers=request.headers,
                enforce=runtime_config.scheduler_security_baseline_enforce,
                scheduler_api_token=runtime_config.scheduler_api_token,
                require_trace_id=runtime_config.scheduler_require_trace_id,
                extract_trace_id_from_headers_fn=extract_trace_id_from_headers,
            )

        async def _load_zone_workflow_phase(zone_id: int) -> str | None:
            rows = await self._ports.fetch(
                """
                SELECT workflow_phase
                FROM zone_workflow_state
                WHERE zone_id = $1
                LIMIT 1
                """,
                int(zone_id),
            )
            if not rows:
                return None
            return str((rows[0] or {}).get("workflow_phase") or "").strip().lower() or None

        return _validate_scheduler_zone, _validate_scheduler_security_baseline, _load_zone_workflow_phase
