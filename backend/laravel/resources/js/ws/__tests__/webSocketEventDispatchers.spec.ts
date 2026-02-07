import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createWebSocketEventDispatchers } from '../webSocketEventDispatchers'
import { clearSnapshotRegistry, setZoneSnapshot } from '../snapshotRegistry'
import type { ActiveSubscription } from '../subscriptionTypes'
import type { ZoneSnapshot } from '@/types/reconciliation'

vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

function createSnapshot(zoneId: number, serverTs: number): ZoneSnapshot {
  return {
    snapshot_id: `snapshot-${zoneId}-${serverTs}`,
    server_ts: serverTs,
    zone_id: zoneId,
    telemetry: {},
    active_alerts: [],
    recent_commands: [],
    nodes: [],
  }
}

describe('webSocketEventDispatchers', () => {
  beforeEach(() => {
    clearSnapshotRegistry()
  })

  it('нормализует глобальное событие с пустыми полями и zone_id строкой', () => {
    const handler = vi.fn()
    const activeSubscriptions = new Map<string, ActiveSubscription>([
      ['sub-global-1', {
        id: 'sub-global-1',
        channelName: 'events.global',
        kind: 'globalEvents',
        handler,
        componentTag: 'TestComponent',
        instanceId: 1,
      }],
    ])
    const channelSubscribers = new Map<string, Set<string>>([
      ['events.global', new Set(['sub-global-1'])],
    ])

    const { handleGlobalEvent } = createWebSocketEventDispatchers({
      activeSubscriptions,
      channelSubscribers,
    })

    handleGlobalEvent('events.global', {
      zone_id: '42',
      occurred_at: '2026-02-07T00:00:00.000Z',
      server_ts: undefined,
    })

    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      id: undefined,
      kind: 'INFO',
      message: '',
      zoneId: 42,
      occurredAt: '2026-02-07T00:00:00.000Z',
    }))
  })

  it('игнорирует stale global-событие, но принимает не-stale', () => {
    const handler = vi.fn()
    const activeSubscriptions = new Map<string, ActiveSubscription>([
      ['sub-global-1', {
        id: 'sub-global-1',
        channelName: 'events.global',
        kind: 'globalEvents',
        handler,
        componentTag: 'TestComponent',
        instanceId: 1,
      }],
    ])
    const channelSubscribers = new Map<string, Set<string>>([
      ['events.global', new Set(['sub-global-1'])],
    ])

    setZoneSnapshot(10, createSnapshot(10, 2000))
    const { handleGlobalEvent } = createWebSocketEventDispatchers({
      activeSubscriptions,
      channelSubscribers,
    })

    handleGlobalEvent('events.global', {
      id: 1,
      zone_id: 10,
      kind: 'WARNING',
      message: 'stale',
      server_ts: 1999,
    })
    handleGlobalEvent('events.global', {
      id: 2,
      zone_id: 10,
      kind: 'WARNING',
      message: 'fresh',
      server_ts: 2001,
    })

    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      id: 2,
      message: 'fresh',
      zoneId: 10,
    }))
  })

  it('игнорирует stale command-событие, но обрабатывает null/новый server_ts', () => {
    const handler = vi.fn()
    const activeSubscriptions = new Map<string, ActiveSubscription>([
      ['sub-command-1', {
        id: 'sub-command-1',
        channelName: 'commands.5',
        kind: 'zoneCommands',
        handler,
        componentTag: 'TestComponent',
        instanceId: 1,
      }],
    ])
    const channelSubscribers = new Map<string, Set<string>>([
      ['commands.5', new Set(['sub-command-1'])],
    ])

    setZoneSnapshot(5, createSnapshot(5, 1000))
    const { handleCommandEvent } = createWebSocketEventDispatchers({
      activeSubscriptions,
      channelSubscribers,
    })

    handleCommandEvent('commands.5', {
      command_id: 101,
      status: 'DONE',
      message: 'stale',
      server_ts: 999,
    }, false)
    handleCommandEvent('commands.5', {
      command_id: 102,
      status: 'DONE',
      message: 'null-ts',
      server_ts: null,
    }, false)
    handleCommandEvent('commands.5', {
      command_id: 103,
      status: 'DONE',
      message: 'fresh',
      server_ts: 1001,
    }, false)

    expect(handler).toHaveBeenCalledTimes(2)
    expect(handler).toHaveBeenNthCalledWith(1, expect.objectContaining({
      commandId: 102,
      zoneId: 5,
      message: 'null-ts',
    }))
    expect(handler).toHaveBeenNthCalledWith(2, expect.objectContaining({
      commandId: 103,
      zoneId: 5,
      message: 'fresh',
    }))
  })

  it('игнорирует command-событие без command_id и нормализует неизвестный статус в UNKNOWN', () => {
    const handler = vi.fn()
    const activeSubscriptions = new Map<string, ActiveSubscription>([
      ['sub-command-1', {
        id: 'sub-command-1',
        channelName: 'commands.9',
        kind: 'zoneCommands',
        handler,
        componentTag: 'TestComponent',
        instanceId: 1,
      }],
    ])
    const channelSubscribers = new Map<string, Set<string>>([
      ['commands.9', new Set(['sub-command-1'])],
    ])

    const { handleCommandEvent } = createWebSocketEventDispatchers({
      activeSubscriptions,
      channelSubscribers,
    })

    handleCommandEvent('commands.9', {
      status: 'DONE',
      message: 'no-id',
    }, false)

    handleCommandEvent('commands.9', {
      command_id: 200,
      status: 'custom_state',
      message: 'normalized-status',
    }, false)

    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      commandId: 200,
      status: 'UNKNOWN',
      message: 'normalized-status',
      zoneId: 9,
    }))
  })
})
