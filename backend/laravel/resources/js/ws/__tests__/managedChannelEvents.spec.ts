import { beforeEach, describe, expect, it, vi } from 'vitest'
import { __resetManagedChannelEventsForTests, subscribeManagedChannelEvents } from '../managedChannelEvents'
import { clearSnapshotRegistry, setZoneSnapshot } from '../snapshotRegistry'
import type { ZoneSnapshot } from '@/types/reconciliation'

const wsStateListeners: Array<(state: string) => void> = []
let currentEcho: {
  private: ReturnType<typeof vi.fn>
  channel: ReturnType<typeof vi.fn>
  leave: ReturnType<typeof vi.fn>
} | null = null

vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/ws/invariants', () => ({
  registerSubscription: vi.fn(),
  unregisterSubscription: vi.fn(),
}))

vi.mock('@/utils/echoClient', () => ({
  getEchoInstance: vi.fn(() => currentEcho),
  onWsStateChange: vi.fn((listener: (state: string) => void) => {
    wsStateListeners.push(listener)
    return () => {
      const index = wsStateListeners.indexOf(listener)
      if (index >= 0) {
        wsStateListeners.splice(index, 1)
      }
    }
  }),
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

describe('managedChannelEvents', () => {
  beforeEach(() => {
    __resetManagedChannelEventsForTests()
    clearSnapshotRegistry()
    wsStateListeners.splice(0, wsStateListeners.length)
    vi.clearAllMocks()
  })

  it('делает leave канала при cleanup по умолчанию', () => {
    const channel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
    }

    currentEcho = {
      private: vi.fn(() => channel),
      channel: vi.fn(() => channel),
      leave: vi.fn(),
    }

    const stop = subscribeManagedChannelEvents({
      channelName: 'hydro.zones.5',
      eventHandlers: {
        '.App\\Events\\GrowCycleUpdated': vi.fn(),
      },
    })

    stop()

    expect(channel.stopListening).toHaveBeenCalledWith('.App\\Events\\GrowCycleUpdated', expect.any(Function))
    expect(currentEcho.leave).toHaveBeenCalledWith('hydro.zones.5')
  })

  it('игнорирует stale raw event по snapshot server_ts', () => {
    const handlers = new Map<string, (payload: Record<string, unknown>) => void>()
    const channel = {
      listen: vi.fn((eventName: string, handler: (payload: Record<string, unknown>) => void) => {
        handlers.set(eventName, handler)
      }),
      stopListening: vi.fn(),
    }

    currentEcho = {
      private: vi.fn(() => channel),
      channel: vi.fn(() => channel),
      leave: vi.fn(),
    }

    setZoneSnapshot(5, createSnapshot(5, 2000))
    const rawHandler = vi.fn()

    const stop = subscribeManagedChannelEvents({
      channelName: 'hydro.zones.5',
      eventHandlers: {
        '.telemetry.batch.updated': rawHandler,
      },
    })

    const listener = handlers.get('.telemetry.batch.updated')
    expect(listener).toBeTypeOf('function')

    listener?.({
      server_ts: 1999,
      updates: [{ node_id: 7, metric_type: 'ph', value: 5.8, ts: 1710000000 }],
    })
    listener?.({
      server_ts: 2001,
      updates: [{ node_id: 7, metric_type: 'ph', value: 5.9, ts: 1710000010 }],
    })

    expect(rawHandler).toHaveBeenCalledTimes(1)
    expect(rawHandler).toHaveBeenCalledWith(expect.objectContaining({
      server_ts: 2001,
    }))

    stop()
  })

  it('не делает leave shared channel, пока есть другие подписчики', () => {
    const handlers = new Map<string, Array<(payload: Record<string, unknown>) => void>>()
    const channel = {
      listen: vi.fn((eventName: string, handler: (payload: Record<string, unknown>) => void) => {
        const listeners = handlers.get(eventName) || []
        listeners.push(handler)
        handlers.set(eventName, listeners)
      }),
      stopListening: vi.fn((eventName: string, handler?: (payload: Record<string, unknown>) => void) => {
        if (!handler) {
          handlers.delete(eventName)
          return
        }

        const listeners = handlers.get(eventName) || []
        handlers.set(eventName, listeners.filter(listener => listener !== handler))
      }),
    }

    currentEcho = {
      private: vi.fn(() => channel),
      channel: vi.fn(() => channel),
      leave: vi.fn(),
    }

    const firstHandler = vi.fn()
    const secondHandler = vi.fn()

    const stopFirst = subscribeManagedChannelEvents({
      channelName: 'hydro.zones.5',
      componentTag: 'first',
      eventHandlers: {
        '.App\\Events\\GrowCycleUpdated': firstHandler,
      },
    })

    const stopSecond = subscribeManagedChannelEvents({
      channelName: 'hydro.zones.5',
      componentTag: 'second',
      eventHandlers: {
        '.App\\Events\\GrowCycleUpdated': secondHandler,
      },
    })

    expect(currentEcho.private).toHaveBeenCalledTimes(1)
    expect(handlers.get('.App\\Events\\GrowCycleUpdated')).toHaveLength(2)

    stopFirst()

    expect(currentEcho.leave).not.toHaveBeenCalled()
    expect(handlers.get('.App\\Events\\GrowCycleUpdated')).toHaveLength(1)

    const remainingHandler = handlers.get('.App\\Events\\GrowCycleUpdated')?.[0]
    remainingHandler?.({ server_ts: 2005 })

    expect(firstHandler).not.toHaveBeenCalled()
    expect(secondHandler).toHaveBeenCalledTimes(1)

    stopSecond()

    expect(currentEcho.leave).toHaveBeenCalledWith('hydro.zones.5')
  })

  it('не пересоздает активный канал на повторном connected без disconnect', () => {
    const channel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
    }

    currentEcho = {
      private: vi.fn(() => channel),
      channel: vi.fn(() => channel),
      leave: vi.fn(),
    }

    const stop = subscribeManagedChannelEvents({
      channelName: 'hydro.zones.8',
      eventHandlers: {
        '.telemetry.batch.updated': vi.fn(),
      },
    })

    expect(currentEcho.private).toHaveBeenCalledTimes(1)

    wsStateListeners.forEach(listener => listener('connected'))
    wsStateListeners.forEach(listener => listener('connected'))

    expect(currentEcho.private).toHaveBeenCalledTimes(1)
    expect(currentEcho.leave).not.toHaveBeenCalled()

    wsStateListeners.forEach(listener => listener('disconnected'))
    wsStateListeners.forEach(listener => listener('connected'))

    expect(currentEcho.private).toHaveBeenCalledTimes(2)

    stop()
  })
})
