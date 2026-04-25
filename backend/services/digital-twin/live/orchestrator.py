"""Orchestrator — вход для live-режима DT (Phase C).

Собирает SimWorld из БД (nodes + channels), регистрирует в WorldRegistry,
поднимает MqttBridge при первой live-симуляции, обрабатывает команды и
публикует physics-based telemetry.

Не содержит app-уровневую инициализацию (lifespan), её делает `main.py`.
"""
import logging
from typing import Any, Dict, List, Optional

from common.db import fetch

from .mqtt_bridge import MqttBridge
from .publisher import Publisher
from .sim_world import NodeChannelSpec, SimWorld
from .world_registry import WorldRegistry

logger = logging.getLogger(__name__)


class LiveOrchestrator:
    """Singleton-инстанс на digital-twin process для управления live-режимом."""

    def __init__(
        self,
        mqtt_host: str,
        mqtt_port: int,
        mqtt_username: Optional[str] = None,
        mqtt_password: Optional[str] = None,
    ) -> None:
        self.bridge = MqttBridge(
            host=mqtt_host,
            port=mqtt_port,
            username=mqtt_username,
            password=mqtt_password,
        )
        self.publisher = Publisher(publish_fn=self.bridge.publish)
        self.registry = WorldRegistry(publisher=self.publisher)
        self._started = False

    # ---- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        if self._started:
            return
        await self.bridge.start(cmd_handler=self._handle_command)
        self._started = True
        logger.info("LiveOrchestrator started")

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            await self.registry.shutdown_all()
        finally:
            await self.bridge.stop()
            self._started = False
            logger.info("LiveOrchestrator stopped")

    # ---- public API --------------------------------------------------------

    async def register_simulation(
        self,
        simulation_id: int,
        zone_id: int,
        gh_uid: str,
        zone_uid: str,
        params_by_group: Dict[str, Dict[str, float]],
        initial_state: Dict[str, Any],
        time_scale: float = 1.0,
        tick_seconds: float = 1.0,
    ) -> SimWorld:
        """Считать nodes/channels зоны и зарегистрировать SimWorld."""
        if not self._started:
            await self.start()

        channels = await load_zone_channels(zone_id)
        sim_world = SimWorld(
            simulation_id=simulation_id,
            zone_id=zone_id,
            gh_uid=gh_uid,
            zone_uid=zone_uid,
            channels=channels,
            params_by_group=params_by_group,
            initial_state=initial_state,
            time_scale=time_scale,
        )
        await self.registry.register(sim_world, tick_seconds=tick_seconds)
        await self.bridge.subscribe_zone_commands(gh_uid, zone_uid)
        return sim_world

    async def unregister_simulation(self, simulation_id: int) -> None:
        sim_world = self.registry.get(simulation_id)
        if sim_world:
            await self.bridge.unsubscribe_zone_commands(
                sim_world.gh_uid, sim_world.zone_uid
            )
        await self.registry.unregister(simulation_id)

    # ---- cmd handler -------------------------------------------------------

    async def _handle_command(
        self,
        gh_uid: str,
        zone_uid: str,
        node_uid: str,
        channel: str,
        payload: Dict[str, Any],
    ) -> None:
        sim_world = self.registry.get_by_zone_uid(gh_uid, zone_uid)
        if not sim_world:
            return  # эта зона не симулируется DT — никак не реагируем
        cmd = str(payload.get("cmd") or "").strip()
        cmd_id = payload.get("cmd_id")
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        if not cmd:
            return
        try:
            sim_world.apply_command(node_uid, channel, cmd, params)
        except Exception as exc:
            logger.exception("Failed to apply DT command: %s", exc)
            await self.publisher.publish_command_response(
                gh_uid=gh_uid,
                zone_uid=zone_uid,
                node_uid=node_uid,
                channel=channel,
                cmd_id=cmd_id,
                status="ERROR",
                ts_seconds=_now_seconds(),
                details={"reason": str(exc)},
            )
            return

        # MVP: подтверждение DONE сразу. Реалистичную задержку добавим позже:
        # set_relay → быстрый DONE; dose/run_pump → DONE через duration_ms.
        await self.publisher.publish_command_response(
            gh_uid=gh_uid,
            zone_uid=zone_uid,
            node_uid=node_uid,
            channel=channel,
            cmd_id=cmd_id,
            status="DONE",
            ts_seconds=_now_seconds(),
        )


# --- DB helpers -----------------------------------------------------------


async def load_zone_channels(zone_id: int) -> List[NodeChannelSpec]:
    """Загрузить все каналы всех нод зоны для SimWorld.

    Источник:
        nodes (uid) JOIN node_channels (channel, type, metric_type)
    """
    rows = await fetch(
        """
        SELECT n.uid AS node_uid,
               nc.channel AS channel,
               nc.type AS type,
               nc.metric_type AS metric_type
        FROM nodes n
        JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1 AND n.uid IS NOT NULL
        ORDER BY n.uid, nc.channel
        """,
        zone_id,
    )
    out: List[NodeChannelSpec] = []
    for row in rows or []:
        node_uid = str(row.get("node_uid") or "").strip()
        channel = str(row.get("channel") or "").strip()
        if not node_uid or not channel:
            continue
        out.append(NodeChannelSpec(
            node_uid=node_uid,
            channel=channel,
            type=str(row.get("type") or "SENSOR").strip(),
            metric_type=(row.get("metric_type") or None),
        ))
    return out


def _now_seconds() -> float:
    import time
    return time.time()
