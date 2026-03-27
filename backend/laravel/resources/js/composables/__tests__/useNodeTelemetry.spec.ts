import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useNodeTelemetry } from '../useNodeTelemetry'
import { __resetManagedChannelEventsForTests } from '@/ws/managedChannelEvents'

const wsStateListeners: Array<(state: string) => void> = []
let currentEcho: { private: ReturnType<typeof vi.fn> } | null = null

vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/utils/env', () => ({
  readBooleanEnv: vi.fn(() => true),
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

vi.mock('@/ws/nodeTelemetryPayload', () => ({
  parseNodeTelemetryBatch: vi.fn((payload: unknown) => {
    if (!payload || typeof payload !== 'object' || !('updates' in payload)) {
      return []
    }

    return Array.isArray((payload as { updates?: unknown[] }).updates)
      ? (payload as { updates: unknown[] }).updates
      : []
  }),
}))

describe('useNodeTelemetry', () => {
  beforeEach(() => {
    __resetManagedChannelEventsForTests()
    wsStateListeners.splice(0, wsStateListeners.length)
    currentEcho = null
    vi.clearAllMocks()
  })

  it('восстанавливает подписку после reconnect', async () => {
    const firstChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
    }
    const secondChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
    }

    currentEcho = {
      private: vi.fn()
        .mockReturnValueOnce(firstChannel)
        .mockReturnValueOnce(secondChannel),
    }

    const received: Array<Record<string, unknown>> = []

    const TestComponent = defineComponent({
      setup(_, { expose }) {
        const nodeId = ref<number | null>(7)
        const zoneId = ref<number | null>(11)
        const telemetry = useNodeTelemetry(nodeId, zoneId)
        expose(telemetry)
        return () => h('div')
      },
    })

    const wrapper = mount(TestComponent)

    wrapper.vm.subscribe((payload: Record<string, unknown>) => {
      received.push(payload)
    })

    expect(currentEcho.private).toHaveBeenCalledTimes(1)
    expect(currentEcho.private).toHaveBeenCalledWith('hydro.zones.11')
    expect(firstChannel.listen).toHaveBeenCalledWith('.telemetry.batch.updated', expect.any(Function))

    wsStateListeners.forEach(listener => listener('disconnected'))
    expect(firstChannel.stopListening).toHaveBeenCalledWith('.telemetry.batch.updated', expect.any(Function))

    wsStateListeners.forEach(listener => listener('connected'))
    expect(currentEcho.private).toHaveBeenCalledTimes(2)
    expect(secondChannel.listen).toHaveBeenCalledWith('.telemetry.batch.updated', expect.any(Function))

    const reconnectHandler = secondChannel.listen.mock.calls[0][1]
    reconnectHandler({
      updates: [
        { node_id: 7, channel: 'ph', metric_type: 'ph', value: 5.9, ts: 1710000000 },
      ],
    })

    expect(received).toEqual([
      { node_id: 7, channel: 'ph', metric_type: 'ph', value: 5.9, ts: 1710000000 },
    ])

    wrapper.unmount()
    expect(secondChannel.stopListening).toHaveBeenCalledWith('.telemetry.batch.updated', expect.any(Function))
  })

  it('игнорирует устаревшие telemetry batch без snapshot registry по server_ts и sample ts', async () => {
    const channel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
    }

    currentEcho = {
      private: vi.fn(() => channel),
    }

    const received: Array<Record<string, unknown>> = []

    const TestComponent = defineComponent({
      setup(_, { expose }) {
        const nodeId = ref<number | null>(7)
        const zoneId = ref<number | null>(11)
        const telemetry = useNodeTelemetry(nodeId, zoneId)
        expose(telemetry)
        return () => h('div')
      },
    })

    const wrapper = mount(TestComponent)

    wrapper.vm.subscribe((payload: Record<string, unknown>) => {
      received.push(payload)
    })

    const firstListener = channel.listen.mock.calls[0][1]

    firstListener({
      server_ts: 200,
      updates: [
        { node_id: 7, channel: 'ph', metric_type: 'ph', value: 5.9, ts: 1710000000 },
      ],
    })

    firstListener({
      server_ts: 199,
      updates: [
        { node_id: 7, channel: 'ph', metric_type: 'ph', value: 5.8, ts: 1709999990 },
      ],
    })

    firstListener({
      updates: [
        { node_id: 7, channel: 'ph', metric_type: 'ph', value: 5.7, ts: 1709999980 },
      ],
    })

    firstListener({
      server_ts: 201,
      updates: [
        { node_id: 7, channel: 'ph', metric_type: 'ph', value: 6.0, ts: 1710000010 },
      ],
    })

    expect(received).toEqual([
      { node_id: 7, channel: 'ph', metric_type: 'ph', value: 5.9, ts: 1710000000 },
      { node_id: 7, channel: 'ph', metric_type: 'ph', value: 6.0, ts: 1710000010 },
    ])

    wrapper.unmount()
  })
})
