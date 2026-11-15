"""runtime cache: explicit dependencies and invocation data."""

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class RuntimeCachePorts:
    node_cache: Callable[..., Any]
    parse_node_info: Callable[..., Any]
    sensor_cache: Callable[..., Any]
    sensor_cache_max_size: Callable[..., Any]
    sensor_cache_pop_oldest: Callable[..., Any]
    sensor_cache_touch: Callable[..., Any]
    set_cache_last_update: Callable[..., Any]
    store_node_cache_entry: Callable[..., Any]
    zone_cache: Callable[..., Any]
    zone_greenhouse_cache: Callable[..., Any]
    fetch: Callable[..., Any]
    logger: Callable[..., Any]
    refresh_node_cache_for_uid: Callable[..., Any]


class RuntimeCache:
    def __init__(self, ports: RuntimeCachePorts) -> None:
        self._ports = ports

    def sensor_cache_touch(self, key: tuple[int, Optional[int], str, str]) -> None:
        if hasattr(self._ports.sensor_cache(), "move_to_end"):
            self._ports.sensor_cache().move_to_end(key)

    def sensor_cache_pop_oldest(self) -> None:
        try:
            self._ports.sensor_cache().popitem(last=False)
            return
        except TypeError:
            pass
        try:
            oldest_key = next(iter(self._ports.sensor_cache()))
        except StopIteration:
            return
        del self._ports.sensor_cache()[oldest_key]

    def sensor_cache_get(self, key: tuple[int, Optional[int], str, str]) -> Optional[int]:
        sensor_id = self._ports.sensor_cache().get(key)
        if sensor_id is not None:
            self._ports.sensor_cache_touch(key)
        return sensor_id

    def sensor_cache_set(self, key: tuple[int, Optional[int], str, str], sensor_id: int) -> None:
        self._ports.sensor_cache()[key] = sensor_id
        self._ports.sensor_cache_touch(key)
        if self._ports.sensor_cache_max_size() <= 0:
            return
        while len(self._ports.sensor_cache()) > self._ports.sensor_cache_max_size():
            self._ports.sensor_cache_pop_oldest()

    def store_node_cache_entry(
        self,
        *,
        node_uid: str,
        gh_uid: Optional[str],
        node_id: int,
        zone_id: Optional[int],
        pending_zone_id: Optional[int],
    ) -> None:
        info: tuple[int, Optional[int], Optional[int]] = (
            node_id,
            zone_id,
            pending_zone_id,
        )
        if gh_uid:
            self._ports.node_cache()[(node_uid, gh_uid)] = info
        if (node_uid, None) not in self._ports.node_cache():
            self._ports.node_cache()[(node_uid, None)] = info

    async def refresh_node_cache_for_uid(self, node_uid: str) -> bool:
        """Перечитать assignment узла из БД и обновить telemetry node cache."""
        normalized_uid = str(node_uid or "").strip()
        if not normalized_uid:
            return False

        rows = await self._ports.fetch(
            """
            SELECT n.id, n.zone_id, n.pending_zone_id, g.uid as gh_uid
            FROM nodes n
            LEFT JOIN zones z ON z.id = n.zone_id
            LEFT JOIN greenhouses g ON g.id = z.greenhouse_id
            WHERE n.uid = $1
            LIMIT 1
            """,
            normalized_uid,
        )
        if not rows:
            return False

        row = rows[0]
        node_id = row.get("id")
        if node_id is None:
            return False

        zone_id = row.get("zone_id")
        pending_zone_id = row.get("pending_zone_id")
        gh_uid = row.get("gh_uid")
        self._ports.store_node_cache_entry(
            node_uid=normalized_uid,
            gh_uid=gh_uid,
            node_id=int(node_id),
            zone_id=int(zone_id) if zone_id is not None else None,
            pending_zone_id=int(pending_zone_id) if pending_zone_id is not None else None,
        )
        return True

    async def prewarm_stale_node_assignments(
        self,
        node_uid_to_info: dict[
            tuple[str, Optional[str]], tuple[int, Optional[int], Optional[int]] | tuple[int, Optional[int]]
        ],
        node_gh_pairs: list[tuple[str, Optional[str]]],
    ) -> None:
        """Обновить из БД узлы с устаревшим zone_id=None до обработки сэмплов батча."""
        stale_node_uids: set[str] = set()
        for node_uid, gh_uid in node_gh_pairs:
            if not node_uid:
                continue
            info = node_uid_to_info.get((node_uid, gh_uid))
            if info is None:
                info = node_uid_to_info.get((node_uid, None))
            if info is None:
                continue
            _, node_zone_id, node_pending_zone_id = self._ports.parse_node_info(info)
            if node_zone_id is None and node_pending_zone_id is None:
                stale_node_uids.add(node_uid)

        for node_uid in stale_node_uids:
            if not await self._ports.refresh_node_cache_for_uid(node_uid):
                continue
            for cache_key, cache_info in list(self._ports.node_cache().items()):
                if cache_key[0] == node_uid:
                    node_uid_to_info[cache_key] = cache_info

    async def refresh_caches(self) -> None:
        """Обновить кеши zone_id и node_id."""

        try:
            zones = await self._ports.fetch(
                """
                SELECT z.id, z.uid, g.uid as gh_uid, g.id as greenhouse_id
                FROM zones z
                JOIN greenhouses g ON g.id = z.greenhouse_id
                """
            )
            if zones:
                self._ports.zone_cache().clear()
                self._ports.zone_greenhouse_cache().clear()
                for zone in zones:
                    zone_uid = zone.get("uid")
                    zone_id = zone.get("id")
                    if not zone_uid or zone_id is None:
                        continue
                    gh_uid = zone.get("gh_uid")
                    key = (zone_uid, gh_uid)
                    self._ports.zone_cache()[key] = zone_id
                    if (zone_uid, None) not in self._ports.zone_cache():
                        self._ports.zone_cache()[(zone_uid, None)] = zone_id
                    greenhouse_id = zone.get("greenhouse_id")
                    if greenhouse_id is not None:
                        self._ports.zone_greenhouse_cache()[zone_id] = greenhouse_id
            else:
                self._ports.logger().info(
                    "refresh_caches: zones query returned 0 rows, keeping existing cache to avoid data loss"
                )

            nodes = await self._ports.fetch(
                """
                SELECT n.id, n.uid, n.zone_id, n.pending_zone_id, g.uid as gh_uid
                FROM nodes n
                LEFT JOIN zones z ON z.id = n.zone_id
                LEFT JOIN greenhouses g ON g.id = z.greenhouse_id
                """
            )
            if not nodes:
                self._ports.logger().info(
                    "refresh_caches: nodes query returned 0 rows, keeping existing cache to avoid data loss"
                )
                self._ports.set_cache_last_update(time.time())
                self._ports.logger().info(
                    f"Cache refreshed: {len(self._ports.zone_cache())} zone entries, {len(self._ports.node_cache())} node entries"
                )
                return
            self._ports.node_cache().clear()
            for node in nodes:
                node_uid = node.get("uid")
                node_id = node.get("id")
                if not node_uid or node_id is None:
                    continue
                gh_uid = node.get("gh_uid")
                zone_id = node.get("zone_id")
                pending_zone_id = node.get("pending_zone_id")
                self._ports.store_node_cache_entry(
                    node_uid=str(node_uid),
                    gh_uid=gh_uid,
                    node_id=int(node_id),
                    zone_id=int(zone_id) if zone_id is not None else None,
                    pending_zone_id=int(pending_zone_id) if pending_zone_id is not None else None,
                )

            self._ports.set_cache_last_update(time.time())
            self._ports.logger().info(
                f"Cache refreshed: {len(self._ports.zone_cache())} zone entries, {len(self._ports.node_cache())} node entries"
            )
        except Exception as e:
            self._ports.logger().error(f"Failed to refresh caches: {e}", exc_info=True)
