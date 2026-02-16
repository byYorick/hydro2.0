"""DB query helpers for node resolution in scheduler workflows."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

FetchFn = Callable[..., Awaitable[Sequence[Dict[str, Any]]]]


async def fetch_zone_nodes(
    *,
    fetch_fn: FetchFn,
    zone_id: int,
    node_types: Sequence[str],
) -> List[Dict[str, Any]]:
    normalized_types = [str(item).strip().lower() for item in node_types if str(item).strip()]
    if not normalized_types:
        return []

    rows = await fetch_fn(
        """
        SELECT n.uid, n.type, COALESCE(nc.channel, 'default') AS channel
        FROM nodes n
        LEFT JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1
          AND LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
          AND LOWER(TRIM(COALESCE(n.type, ''))) = ANY($2::text[])
          AND (
            nc.id IS NULL
            OR UPPER(TRIM(COALESCE(nc.type, ''))) = 'ACTUATOR'
          )
        """,
        zone_id,
        normalized_types,
    )
    result: List[Dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "node_uid": row["uid"],
                "type": row["type"],
                "channel": row["channel"] or "default",
            }
        )
    return result


async def resolve_online_node_for_channel(
    *,
    fetch_fn: FetchFn,
    zone_id: int,
    channel: str,
    node_types: Sequence[str],
) -> Optional[Dict[str, Any]]:
    normalized_channel = str(channel or "").strip().lower()
    if not normalized_channel:
        return None
    normalized_node_types = [str(item).strip().lower() for item in node_types if str(item).strip()]
    if not normalized_node_types:
        return None

    rows = await fetch_fn(
        """
        SELECT
            n.uid AS node_uid,
            LOWER(COALESCE(n.type, '')) AS node_type,
            LOWER(COALESCE(nc.channel, 'default')) AS channel
        FROM nodes n
        JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1
          AND LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
          AND LOWER(COALESCE(nc.channel, 'default')) = $2
          AND UPPER(TRIM(COALESCE(nc.type, ''))) = 'ACTUATOR'
          AND LOWER(COALESCE(n.type, '')) = ANY($3::text[])
        ORDER BY n.id ASC, nc.id ASC
        LIMIT 1
        """,
        zone_id,
        normalized_channel,
        normalized_node_types,
    )
    if not rows:
        return None

    row = rows[0]
    node_uid = str(row.get("node_uid") or "").strip()
    if not node_uid:
        return None
    return {
        "node_uid": node_uid,
        "type": str(row.get("node_type") or "").strip().lower(),
        "channel": str(row.get("channel") or normalized_channel).strip().lower() or normalized_channel,
    }


async def check_required_nodes_online(
    *,
    fetch_fn: FetchFn,
    zone_id: int,
    required_types: Sequence[str],
) -> Dict[str, Any]:
    normalized_types = [str(item).strip().lower() for item in required_types if str(item).strip()]
    if not normalized_types:
        return {"required_types": [], "online_counts": {}, "missing_types": []}

    rows = await fetch_fn(
        """
        SELECT
            LOWER(COALESCE(n.type, '')) AS node_type,
            COUNT(*)::int AS online_count
        FROM nodes n
        WHERE n.zone_id = $1
          AND LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
          AND LOWER(COALESCE(n.type, '')) = ANY($2::text[])
        GROUP BY LOWER(COALESCE(n.type, ''))
        """,
        zone_id,
        normalized_types,
    )

    online_counts: Dict[str, int] = {}
    for row in rows:
        node_type = str(row.get("node_type") or "").strip().lower()
        if not node_type:
            continue
        try:
            online_counts[node_type] = int(row.get("online_count") or 0)
        except (TypeError, ValueError):
            online_counts[node_type] = 0

    missing = [node_type for node_type in normalized_types if online_counts.get(node_type, 0) <= 0]
    return {
        "required_types": normalized_types,
        "online_counts": online_counts,
        "missing_types": missing,
    }


async def resolve_refill_node(
    *,
    fetch_fn: FetchFn,
    zone_id: int,
    node_types: Sequence[str],
    preferred_channels: Sequence[str],
    requested_channel: str,
) -> Optional[Dict[str, Any]]:
    normalized_types = [str(item).strip().lower() for item in node_types if str(item).strip()]
    normalized_channels = [str(item).strip().lower() for item in preferred_channels if str(item).strip()]
    normalized_requested = str(requested_channel or "").strip().lower()
    if not normalized_types and not normalized_channels:
        return None

    rows = await fetch_fn(
        """
        SELECT
            n.uid AS node_uid,
            LOWER(COALESCE(n.type, '')) AS node_type,
            LOWER(COALESCE(nc.channel, 'default')) AS channel
        FROM nodes n
        LEFT JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1
          AND LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
          AND (
              LOWER(COALESCE(n.type, '')) = ANY($2::text[])
              OR LOWER(COALESCE(nc.channel, '')) = ANY($3::text[])
          )
        ORDER BY n.id ASC, nc.id ASC
        """,
        zone_id,
        normalized_types,
        normalized_channels,
    )
    if not rows:
        return None

    candidates: List[Dict[str, Any]] = []
    for row in rows:
        node_uid = str(row.get("node_uid") or "").strip()
        if not node_uid:
            continue
        candidates.append(
            {
                "node_uid": node_uid,
                "type": str(row.get("node_type") or "").strip().lower(),
                "channel": str(row.get("channel") or "default").strip().lower() or "default",
            }
        )
    if not candidates:
        return None

    selected: Optional[Dict[str, Any]] = None
    if normalized_requested:
        selected = next((item for item in candidates if item["channel"] == normalized_requested), None)
    if selected is None:
        node_type_set = set(normalized_types)
        channel_rank = {channel: idx for idx, channel in enumerate(normalized_channels)}
        selected = sorted(
            candidates,
            key=lambda item: (
                channel_rank.get(item["channel"], len(channel_rank) + 10),
                item["type"] not in node_type_set,
                item["node_uid"],
            ),
        )[0]

    return selected


__all__ = [
    "check_required_nodes_online",
    "fetch_zone_nodes",
    "resolve_refill_node",
    "resolve_online_node_for_channel",
]
