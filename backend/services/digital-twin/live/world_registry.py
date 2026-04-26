"""WorldRegistry — реестр активных SimWorld-ов.

Per simulation_id держит:
- SimWorld instance,
- фоновую asyncio task, которая шагает мир каждые `tick_seconds` real time
  и публикует samples/level events через переданный Publisher.

Регистрация/снятие происходит из live-orchestrator при start/stop симуляции.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .publisher import Publisher
from .sim_world import SimWorld

logger = logging.getLogger(__name__)


@dataclass
class _Entry:
    sim_world: SimWorld
    task: asyncio.Task
    tick_seconds: float


class WorldRegistry:
    """Глобальный per-process реестр live SimWorld'ов."""

    def __init__(self, publisher: Publisher) -> None:
        self.publisher = publisher
        self._entries: Dict[int, _Entry] = {}
        self._lock = asyncio.Lock()

    # ---- public API --------------------------------------------------------

    async def register(
        self,
        sim_world: SimWorld,
        tick_seconds: float = 1.0,
    ) -> None:
        async with self._lock:
            existing = self._entries.get(sim_world.simulation_id)
            if existing and not existing.task.done():
                logger.warning(
                    "SimWorld already registered for simulation_id=%s — skipping",
                    sim_world.simulation_id,
                )
                return

            # Опубликовать initial level latches.
            initial_events = sim_world.emit_initial_levels()
            await self.publisher.publish_level_events(
                sim_world.gh_uid, sim_world.zone_uid, initial_events
            )

            task = asyncio.create_task(
                self._run_tick_loop(sim_world, max(0.1, tick_seconds))
            )
            self._entries[sim_world.simulation_id] = _Entry(
                sim_world=sim_world,
                task=task,
                tick_seconds=max(0.1, tick_seconds),
            )
            logger.info(
                "SimWorld registered",
                extra={
                    "simulation_id": sim_world.simulation_id,
                    "zone_id": sim_world.zone_id,
                    "tick_seconds": tick_seconds,
                },
            )

    async def unregister(self, simulation_id: int) -> None:
        async with self._lock:
            entry = self._entries.pop(simulation_id, None)
        if not entry:
            return
        entry.task.cancel()
        try:
            await entry.task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning(
                "SimWorld task ended with exception on unregister: %s", exc
            )

    def get(self, simulation_id: int) -> Optional[SimWorld]:
        entry = self._entries.get(simulation_id)
        if entry and not entry.task.done():
            return entry.sim_world
        return None

    def get_by_zone_uid(self, gh_uid: str, zone_uid: str) -> Optional[SimWorld]:
        for entry in self._entries.values():
            if (
                entry.sim_world.gh_uid == gh_uid
                and entry.sim_world.zone_uid == zone_uid
                and not entry.task.done()
            ):
                return entry.sim_world
        return None

    @property
    def active_count(self) -> int:
        return sum(
            1 for e in self._entries.values() if not e.task.done()
        )

    async def shutdown_all(self) -> None:
        async with self._lock:
            sim_ids = list(self._entries.keys())
        for sid in sim_ids:
            await self.unregister(sid)

    # ---- internals ---------------------------------------------------------

    async def _run_tick_loop(self, sim_world: SimWorld, tick_seconds: float) -> None:
        """Фоновый цикл: каждый tick прошагать мир и опубликовать samples/events."""
        try:
            while True:
                await asyncio.sleep(tick_seconds)
                samples, level_events = sim_world.step(tick_seconds)
                if samples:
                    await self.publisher.publish_samples(
                        sim_world.gh_uid, sim_world.zone_uid, samples
                    )
                if level_events:
                    await self.publisher.publish_level_events(
                        sim_world.gh_uid, sim_world.zone_uid, level_events
                    )
        except asyncio.CancelledError:
            logger.debug(
                "SimWorld tick loop cancelled for simulation_id=%s",
                sim_world.simulation_id,
            )
            raise
        except Exception as exc:
            logger.exception(
                "SimWorld tick loop failed for simulation_id=%s: %s",
                sim_world.simulation_id,
                exc,
            )
