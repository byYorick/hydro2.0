#!/usr/bin/env python3
"""
CLI для управления dead-list телеметрии (hydro:telemetry:dead).

Использование:
    python telemetry_dead_cli.py list [--limit 100] [--offset 0]
    python telemetry_dead_cli.py replay <index>
    python telemetry_dead_cli.py purge <index>
    python telemetry_dead_cli.py purge-all
    python telemetry_dead_cli.py metrics
"""
import argparse
import asyncio
import json
import sys

from common.redis_queue import TelemetryQueue


async def list_dead(limit: int = 100, offset: int = 0) -> None:
    queue = TelemetryQueue()
    metrics = await queue.get_dead_metrics()
    items = await queue.list_dead(limit=limit, offset=offset)

    print(
        f"\n=== Telemetry dead list (showing {len(items)} of {metrics.get('size', 0)}) ==="
    )
    if not items:
        print("Dead list is empty")
        return

    for item in items:
        print(f"\nIndex: {item.get('index')}")
        if item.get("parse_error"):
            print(f"  Parse error, raw: {item.get('raw', '')[:200]}")
            continue
        print(f"  Reason: {item.get('reason')}")
        print(f"  Retry: {item.get('retry')}")
        print(f"  Moved At: {item.get('moved_at')}")
        age = item.get("age_seconds")
        if age is not None:
            print(f"  Age: {age:.1f} seconds")
        payload_b64 = item.get("payload_b64") or ""
        print(f"  Payload (b64 prefix): {payload_b64[:80]}{'...' if len(payload_b64) > 80 else ''}")


async def replay_dead(index: int) -> None:
    queue = TelemetryQueue()
    success = await queue.replay_dead(index)
    if success:
        print(f"✓ Telemetry dead list item {index} replayed to queue")
    else:
        print(f"✗ Telemetry dead list item {index} not found or invalid")
        sys.exit(1)


async def purge_dead(index: int) -> None:
    queue = TelemetryQueue()
    success = await queue.purge_dead(index)
    if success:
        print(f"✓ Telemetry dead list item {index} purged")
    else:
        print(f"✗ Telemetry dead list item {index} not found")
        sys.exit(1)


async def purge_all_dead() -> None:
    queue = TelemetryQueue()
    count = await queue.purge_dead_all()
    print(f"✓ Purged {count} telemetry dead list items")


async def show_metrics() -> None:
    queue = TelemetryQueue()
    metrics = await queue.get_dead_metrics()
    print("\n=== Telemetry Dead List Metrics ===")
    print(json.dumps(metrics, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Telemetry dead-list CLI for history-logger")
    subparsers = parser.add_subparsers(dest="action", help="Action")

    list_parser = subparsers.add_parser("list", help="List dead-list items")
    list_parser.add_argument("--limit", type=int, default=100, help="Limit (default: 100)")
    list_parser.add_argument("--offset", type=int, default=0, help="Offset (default: 0)")

    replay_parser = subparsers.add_parser("replay", help="Replay dead-list item to queue")
    replay_parser.add_argument("index", type=int, help="Dead-list index")

    purge_parser = subparsers.add_parser("purge", help="Purge dead-list item")
    purge_parser.add_argument("index", type=int, help="Dead-list index")

    subparsers.add_parser("purge-all", help="Purge all dead-list items")
    subparsers.add_parser("metrics", help="Show dead-list metrics")

    args = parser.parse_args()
    if args.action == "list":
        asyncio.run(list_dead(limit=args.limit, offset=args.offset))
    elif args.action == "replay":
        asyncio.run(replay_dead(args.index))
    elif args.action == "purge":
        asyncio.run(purge_dead(args.index))
    elif args.action == "purge-all":
        asyncio.run(purge_all_dead())
    elif args.action == "metrics":
        asyncio.run(show_metrics())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
