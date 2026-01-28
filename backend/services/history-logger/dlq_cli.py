#!/usr/bin/env python3
"""
CLI инструмент для управления DLQ (Dead Letter Queue) очередей history-logger.

Использование:
    python dlq_cli.py alerts list [--limit 100] [--offset 0]
    python dlq_cli.py alerts replay <dlq_id>
    python dlq_cli.py alerts purge <dlq_id>
    python dlq_cli.py alerts purge-all
    
    python dlq_cli.py status-updates list [--limit 100] [--offset 0]
    python dlq_cli.py status-updates replay <dlq_id>
    python dlq_cli.py status-updates purge <dlq_id>
    python dlq_cli.py status-updates purge-all
    
    python dlq_cli.py metrics
"""
import asyncio
import argparse
import json
import sys
from typing import Optional

# Добавляем путь к common модулям
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.alert_queue import get_alert_queue
from common.command_status_queue import get_status_queue


async def list_alerts_dlq(limit: int = 100, offset: int = 0):
    """Показать список элементов из DLQ алертов."""
    queue = await get_alert_queue()
    items = await queue.list_dlq(limit=limit, offset=offset)
    metrics = await queue.get_queue_metrics()
    
    print(f"\n=== Alerts DLQ (showing {len(items)} of {metrics.get('dlq_size', 0)}) ===")
    if not items:
        print("DLQ is empty")
        return
    
    for item in items:
        print(f"\nID: {item['id']}")
        print(f"  Zone ID: {item['zone_id']}")
        print(f"  Source: {item['source']}")
        print(f"  Code: {item['code']}")
        print(f"  Type: {item['type']}")
        print(f"  Status: {item['status']}")
        print(f"  Retry Count: {item['retry_count']}/{item.get('max_attempts', 'N/A')}")
        print(f"  Last Error: {item['last_error'][:100] if item['last_error'] else 'N/A'}")
        print(f"  Moved to DLQ: {item['moved_to_dlq_at']}")
        print(f"  Created: {item['created_at']}")


async def replay_alert_dlq(dlq_id: int):
    """Переместить элемент из DLQ алертов обратно в очередь."""
    queue = await get_alert_queue()
    success = await queue.replay_dlq_item(dlq_id)
    
    if success:
        print(f"✓ Alert DLQ item {dlq_id} replayed successfully")
    else:
        print(f"✗ Alert DLQ item {dlq_id} not found")
        sys.exit(1)


async def purge_alert_dlq(dlq_id: int):
    """Удалить элемент из DLQ алертов."""
    queue = await get_alert_queue()
    success = await queue.purge_dlq_item(dlq_id)
    
    if success:
        print(f"✓ Alert DLQ item {dlq_id} purged successfully")
    else:
        print(f"✗ Alert DLQ item {dlq_id} not found")
        sys.exit(1)


async def purge_all_alerts_dlq():
    """Удалить все элементы из DLQ алертов."""
    queue = await get_alert_queue()
    count = await queue.purge_dlq_all()
    
    print(f"✓ Purged {count} alert DLQ items")


async def list_status_updates_dlq(limit: int = 100, offset: int = 0):
    """Показать список элементов из DLQ статусов команд."""
    queue = await get_status_queue()
    items = await queue.list_dlq(limit=limit, offset=offset)
    metrics = await queue.get_queue_metrics()
    
    print(f"\n=== Status Updates DLQ (showing {len(items)} of {metrics.get('dlq_size', 0)}) ===")
    if not items:
        print("DLQ is empty")
        return
    
    for item in items:
        print(f"\nID: {item['id']}")
        print(f"  Cmd ID: {item['cmd_id']}")
        print(f"  Status: {item['status']}")
        print(f"  Retry Count: {item['retry_count']}/{item.get('max_attempts', 'N/A')}")
        print(f"  Last Error: {item['last_error'][:100] if item['last_error'] else 'N/A'}")
        print(f"  Moved to DLQ: {item['moved_to_dlq_at']}")
        print(f"  Created: {item['created_at']}")


async def replay_status_update_dlq(dlq_id: int):
    """Переместить элемент из DLQ статусов команд обратно в очередь."""
    queue = await get_status_queue()
    success = await queue.replay_dlq_item(dlq_id)
    
    if success:
        print(f"✓ Status update DLQ item {dlq_id} replayed successfully")
    else:
        print(f"✗ Status update DLQ item {dlq_id} not found")
        sys.exit(1)


async def purge_status_update_dlq(dlq_id: int):
    """Удалить элемент из DLQ статусов команд."""
    queue = await get_status_queue()
    success = await queue.purge_dlq_item(dlq_id)
    
    if success:
        print(f"✓ Status update DLQ item {dlq_id} purged successfully")
    else:
        print(f"✗ Status update DLQ item {dlq_id} not found")
        sys.exit(1)


async def purge_all_status_updates_dlq():
    """Удалить все элементы из DLQ статусов команд."""
    queue = await get_status_queue()
    count = await queue.purge_dlq_all()
    
    print(f"✓ Purged {count} status update DLQ items")


async def show_metrics():
    """Показать метрики всех DLQ очередей."""
    alert_queue = await get_alert_queue()
    status_queue = await get_status_queue()
    
    alert_metrics = await alert_queue.get_queue_metrics()
    status_metrics = await status_queue.get_queue_metrics()
    
    print("\n=== DLQ Metrics ===")
    print("\nAlerts Queue:")
    print(f"  Size: {alert_metrics.get('size', 0)}")
    print(f"  Oldest Age: {alert_metrics.get('oldest_age_seconds', 0.0):.1f} seconds")
    print(f"  DLQ Size: {alert_metrics.get('dlq_size', 0)}")
    print(f"  Success Rate: {alert_metrics.get('success_rate', 1.0):.2%}")
    
    print("\nStatus Updates Queue:")
    print(f"  Size: {status_metrics.get('size', 0)}")
    print(f"  Oldest Age: {status_metrics.get('oldest_age_seconds', 0.0):.1f} seconds")
    print(f"  DLQ Size: {status_metrics.get('dlq_size', 0)}")
    print(f"  Success Rate: {status_metrics.get('success_rate', 1.0):.2%}")


def main():
    parser = argparse.ArgumentParser(description='DLQ Management CLI for history-logger')
    subparsers = parser.add_subparsers(dest='queue_type', help='Queue type')
    
    # Alerts commands
    alerts_parser = subparsers.add_parser('alerts', help='Manage alerts DLQ')
    alerts_subparsers = alerts_parser.add_subparsers(dest='action', help='Action')
    
    alerts_list = alerts_subparsers.add_parser('list', help='List DLQ items')
    alerts_list.add_argument('--limit', type=int, default=100, help='Limit (default: 100)')
    alerts_list.add_argument('--offset', type=int, default=0, help='Offset (default: 0)')
    
    alerts_replay = alerts_subparsers.add_parser('replay', help='Replay DLQ item')
    alerts_replay.add_argument('dlq_id', type=int, help='DLQ item ID')
    
    alerts_purge = alerts_subparsers.add_parser('purge', help='Purge DLQ item')
    alerts_purge.add_argument('dlq_id', type=int, help='DLQ item ID')
    
    alerts_subparsers.add_parser('purge-all', help='Purge all DLQ items')
    
    # Status updates commands
    status_parser = subparsers.add_parser('status-updates', help='Manage status updates DLQ')
    status_subparsers = status_parser.add_subparsers(dest='action', help='Action')
    
    status_list = status_subparsers.add_parser('list', help='List DLQ items')
    status_list.add_argument('--limit', type=int, default=100, help='Limit (default: 100)')
    status_list.add_argument('--offset', type=int, default=0, help='Offset (default: 0)')
    
    status_replay = status_subparsers.add_parser('replay', help='Replay DLQ item')
    status_replay.add_argument('dlq_id', type=int, help='DLQ item ID')
    
    status_purge = status_subparsers.add_parser('purge', help='Purge DLQ item')
    status_purge.add_argument('dlq_id', type=int, help='DLQ item ID')
    
    status_subparsers.add_parser('purge-all', help='Purge all DLQ items')
    
    # Metrics command
    subparsers.add_parser('metrics', help='Show DLQ metrics')
    
    args = parser.parse_args()
    
    if not args.queue_type:
        parser.print_help()
        sys.exit(1)
    
    # Выполняем соответствующую команду
    if args.queue_type == 'alerts':
        if args.action == 'list':
            asyncio.run(list_alerts_dlq(limit=args.limit, offset=args.offset))
        elif args.action == 'replay':
            asyncio.run(replay_alert_dlq(args.dlq_id))
        elif args.action == 'purge':
            asyncio.run(purge_alert_dlq(args.dlq_id))
        elif args.action == 'purge-all':
            asyncio.run(purge_all_alerts_dlq())
        else:
            alerts_parser.print_help()
    elif args.queue_type == 'status-updates':
        if args.action == 'list':
            asyncio.run(list_status_updates_dlq(limit=args.limit, offset=args.offset))
        elif args.action == 'replay':
            asyncio.run(replay_status_update_dlq(args.dlq_id))
        elif args.action == 'purge':
            asyncio.run(purge_status_update_dlq(args.dlq_id))
        elif args.action == 'purge-all':
            asyncio.run(purge_all_status_updates_dlq())
        else:
            status_parser.print_help()
    elif args.queue_type == 'metrics':
        asyncio.run(show_metrics())
    else:
        parser.print_help()


if __name__ == '__main__':
    main()

