"""app runtime lifespan: explicit dependencies and invocation data."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Optional

import asyncpg
from fastapi import FastAPI


@dataclass(frozen=True)
class AppRuntimeLifespanPorts:
    intentstatuslistener: Callable[..., Any]
    zoneeventlistener: Callable[..., Any]
    build_intent_listener_callback: Callable[..., Any]
    build_zone_event_listener_callback: Callable[..., Any]
    drain_background_tasks: Callable[..., Any]
    spawn_background_task: Callable[..., Any]
    utcnow: Callable[..., Any]
    get_pool: Callable[..., Any]
    initialize_counter_series: Callable[..., Any]
    logger: Callable[..., Any]


class AppRuntimeLifespan:
    def __init__(self, ports: AppRuntimeLifespanPorts) -> None:
        self._ports = ports

    def build_app_lifespan(
        self, *, bundle: Any, runtime_config: Any, background_tasks: Any, critical_background_tasks: Any
    ) -> Any:
        @asynccontextmanager
        async def _app_lifespan(app: FastAPI) -> AsyncIterator[None]:
            # Retry get_pool на случай race condition при старте контейнера:
            # PostgreSQL может быть healthy, но docker-network DNS / TLS handshake
            # успевает дать transient connect error до того, как сеть стабилизируется.
            # Без retry FastAPI lifespan сразу падает и контейнер уходит в unhealthy.
            pool_attempts = 30
            pool_backoff_sec = 2.0
            for attempt in range(1, pool_attempts + 1):
                try:
                    await self._ports.get_pool()
                    break
                except (OSError, ConnectionError, asyncpg.exceptions.PostgresConnectionError) as exc:
                    if attempt >= pool_attempts:
                        self._ports.logger().error(
                            "AE3 lifespan: PostgreSQL pool init failed after %d attempts: %s",
                            attempt,
                            exc,
                        )
                        raise
                    self._ports.logger().warning(
                        "AE3 lifespan: PostgreSQL pool init transient error (attempt %d/%d): %s — retry in %.1fs",
                        attempt,
                        pool_attempts,
                        exc,
                        pool_backoff_sec,
                    )
                    await asyncio.sleep(pool_backoff_sec)
            self._ports.initialize_counter_series()
            await bundle.worker.recover_on_startup()
            bundle.worker.kick()
            app.state.ae3_runtime_bundle = bundle
            app.state.ae3_runtime_config = runtime_config
            app.state.ae3_critical_background_tasks = critical_background_tasks

            # Запустить listener статусов intent, если доступен DB DSN.
            intent_listener_task: Optional[asyncio.Task] = None
            intent_listener: Optional[self._ports.intentstatuslistener] = None
            zone_event_listener_task: Optional[asyncio.Task] = None
            zone_event_listener: Optional[self._ports.zoneeventlistener] = None
            if runtime_config.db_dsn:
                intent_listener = self._ports.intentstatuslistener(
                    dsn=runtime_config.db_dsn,
                    on_terminal_intent=self._ports.build_intent_listener_callback(
                        worker=bundle.worker, logger=self._ports.logger()
                    ),
                )
                intent_listener_task = self._ports.spawn_background_task(
                    intent_listener.run(),
                    background_tasks=background_tasks,
                    task_name="ae3-intent-status-listener",
                )
                critical_background_tasks["ae3-intent-status-listener"] = intent_listener_task
                zone_event_listener = self._ports.zoneeventlistener(
                    dsn=runtime_config.db_dsn,
                    on_zone_event=self._ports.build_zone_event_listener_callback(
                        worker=bundle.worker,
                        solution_tank_startup_guard_use_case=bundle.solution_tank_startup_guard_use_case,
                        trigger_solution_topup_from_level_event_use_case=bundle.trigger_solution_topup_from_level_event_use_case,
                        now_fn=self._ports.utcnow,
                        logger=self._ports.logger(),
                    ),
                )
                zone_event_listener_task = self._ports.spawn_background_task(
                    zone_event_listener.run(),
                    background_tasks=background_tasks,
                    task_name="ae3-zone-event-listener",
                )
                critical_background_tasks["ae3-zone-event-listener"] = zone_event_listener_task

            try:
                yield
            finally:
                if intent_listener_task is not None and not intent_listener_task.done():
                    intent_listener.stop()
                if zone_event_listener_task is not None and not zone_event_listener_task.done():
                    zone_event_listener.stop()
                await bundle.worker.shutdown(grace_sec=runtime_config.shutdown_grace_sec)
                await self._ports.drain_background_tasks(background_tasks)
                await bundle.http_client.aclose()

        return _app_lifespan
