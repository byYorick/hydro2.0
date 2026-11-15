"""app runtime zone control: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Callable

from fastapi import HTTPException, Path, Request

from ae3lite.api.http_errors import api_error_detail
from ae3lite.api.validation import validate_scheduler_zone
from ae3lite.domain.errors import ManualControlError
from ae3lite.runtime.app_runtime_records import ControlModeRequest, ManualStepRequest, OperatorUnblockRequest


@dataclass(frozen=True)
class AppRuntimeZoneControlPorts:
    utcnow: Callable[..., Any]
    fetch: Callable[..., Any]
    logger: Callable[..., Any]


class AppRuntimeZoneControl:
    def __init__(self, ports: AppRuntimeZoneControlPorts) -> None:
        self._ports = ports

    def bind_zone_control_routes(
        self,
        *,
        app: Any,
        runtime_config: Any,
        bundle: Any,
        zone_read_rate_limiter: Any,
        _validate_scheduler_security_baseline: Any,
        _validate_scheduler_zone: Any,
    ) -> Any:
        def _enforce_zone_read_rate_limit(zone_id: int) -> None:
            if not runtime_config.start_cycle_rate_limit_enabled:
                return
            if zone_read_rate_limiter.check(zone_id=zone_id):
                return
            raise api_error_detail(
                "start_cycle_rate_limited",
                status_code=429,
                zone_id=zone_id,
                window_sec=10,
                max_requests=60,
            )

        @app.get("/zones/{zone_id}/state")
        async def get_zone_state(
            zone_id: Annotated[int, Path(gt=0)],
            request: Request,
        ) -> dict[str, Any]:
            """Возвращает полное automation state зоны: задачи, фазы и ошибки."""
            await _validate_scheduler_security_baseline(request)
            await _validate_scheduler_zone(zone_id)
            _enforce_zone_read_rate_limit(zone_id)
            return await bundle.get_zone_automation_state_use_case.run(zone_id=zone_id)

        @app.get("/zones/{zone_id}/control-mode")
        async def get_zone_control_mode(
            zone_id: Annotated[int, Path(gt=0)],
            request: Request,
        ) -> dict[str, Any]:
            """Возвращает текущий `control_mode` и разрешённые manual step для зоны."""
            await _validate_scheduler_security_baseline(request)
            await _validate_scheduler_zone(zone_id)
            _enforce_zone_read_rate_limit(zone_id)
            result = await bundle.get_zone_control_state_use_case.run(zone_id=zone_id)
            return {"status": "ok", "data": {**result, "zone_id": zone_id}}

        @app.post("/zones/{zone_id}/control-mode")
        async def set_zone_control_mode(
            zone_id: Annotated[int, Path(gt=0)], request: Request, req: ControlModeRequest
        ) -> dict[str, Any]:
            """Сохраняет `control_mode` зоны и синхронизирует snapshot активной задачи."""
            await _validate_scheduler_security_baseline(request)
            await validate_scheduler_zone(zone_id, fetch_fn=self._ports.fetch, logger=self._ports.logger())
            await bundle.set_control_mode_use_case.run(
                zone_id=zone_id,
                control_mode=req.control_mode,
                now=self._ports.utcnow(),
                user_id=req.user_id,
                user_role=req.user_role,
                source=req.source,
                reason=req.reason,
            )
            result = await bundle.get_zone_control_state_use_case.run(zone_id=zone_id)
            bundle.worker.kick()
            return {"status": "ok", "data": {**result, "zone_id": zone_id}}

        @app.post("/zones/{zone_id}/operator-unblock")
        async def operator_unblock_zone(
            zone_id: Annotated[int, Path(gt=0)],
            request: Request,
            req: OperatorUnblockRequest,
        ) -> dict[str, Any]:
            """Fail-safe OFF, fail active task, reset workflow to idle/startup."""
            await _validate_scheduler_security_baseline(request)
            await validate_scheduler_zone(zone_id, fetch_fn=self._ports.fetch, logger=self._ports.logger())
            result = await bundle.operator_unblock_use_case.run(
                zone_id=zone_id,
                now=self._ports.utcnow(),
                source=req.source,
                reason=req.reason,
                user_id=req.user_id,
                user_role=req.user_role,
            )
            bundle.worker.kick()
            return {"status": "ok", "data": result}

        @app.post("/zones/{zone_id}/manual-step")
        async def request_zone_manual_step(
            zone_id: Annotated[int, Path(gt=0)], request: Request, req: ManualStepRequest
        ) -> dict[str, Any]:
            """Сохраняет pending public manual step для активной задачи зоны."""
            await _validate_scheduler_security_baseline(request)
            await validate_scheduler_zone(zone_id, fetch_fn=self._ports.fetch, logger=self._ports.logger())
            try:
                result = await bundle.request_manual_step_use_case.run(
                    zone_id=zone_id,
                    manual_step=req.manual_step,
                    now=self._ports.utcnow(),
                )
            except ManualControlError as exc:
                raise HTTPException(
                    status_code=exc.status_code,
                    detail={
                        "status": "error",
                        "code": exc.code,
                        "message": str(exc),
                        **exc.details,
                    },
                ) from exc
            bundle.worker.kick()
            return {"status": "ok", "data": result}
