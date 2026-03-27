import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiGetMock = vi.hoisted(() => vi.fn())
const echoHolder = vi.hoisted(() => ({ current: null as any }))

vi.mock('@/utils/env', () => ({
  readBooleanEnv: () => true,
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    warn: vi.fn(),
  },
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    get: apiGetMock,
  }),
}))

vi.mock('@/utils/echoClient', () => ({
  getEchoInstance: () => echoHolder.current,
  getConnectionState: () => ({ state: 'connected' }),
  onWsStateChange: () => () => {},
}))

import AutomationProcessPanel from '../AutomationProcessPanel.vue'

type EventHandler = (payload: Record<string, unknown>) => void

interface MockChannel {
  handlers: Map<string, EventHandler>
  listen: ReturnType<typeof vi.fn>
  stopListening: ReturnType<typeof vi.fn>
}

function createMockChannel(): MockChannel {
  const handlers = new Map<string, EventHandler>()

  const channel: MockChannel = {
    handlers,
    listen: vi.fn((eventName: string, handler: EventHandler) => {
      handlers.set(eventName, handler)
      return channel
    }),
    stopListening: vi.fn((eventName: string) => {
      handlers.delete(eventName)
      return channel
    }),
  }

  return channel
}

describe('AutomationProcessPanel realtime refresh', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    apiGetMock.mockReset()
    apiGetMock.mockResolvedValue({
      data: {
        zone_id: 7,
        state: 'TANK_FILLING',
        state_label: 'Набор бака с раствором',
        state_details: {
          started_at: '2026-03-03T11:00:00Z',
          elapsed_sec: 30,
          progress_percent: 22,
          failed: false,
        },
        system_config: {
          tanks_count: 2,
          system_type: 'drip',
          clean_tank_capacity_l: 300,
          nutrient_tank_capacity_l: 280,
        },
        current_levels: {
          clean_tank_level_percent: 80,
          nutrient_tank_level_percent: 15,
          buffer_tank_level_percent: null,
          ph: 5.9,
          ec: 1.4,
        },
        active_processes: {
          pump_in: true,
          circulation_pump: false,
          ph_correction: false,
          ec_correction: false,
        },
        timeline: [],
        next_state: 'TANK_RECIRC',
        estimated_completion_sec: 120,
      },
    })
  })

  afterEach(() => {
    echoHolder.current = null
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('обновляет состояние после EventCreated для текущей зоны', async () => {
    const channels = new Map<string, MockChannel>()
    echoHolder.current = {
      private: vi.fn((channelName: string) => {
        if (!channels.has(channelName)) {
          channels.set(channelName, createMockChannel())
        }
        return channels.get(channelName)
      }),
      leave: vi.fn(),
    }

    const wrapper = shallowMount(AutomationProcessPanel, {
      props: {
        zoneId: 7,
      },
    })

    await flushPromises()
    await vi.advanceTimersByTimeAsync(1300)
    await flushPromises()

    expect(echoHolder.current.private).toHaveBeenCalledWith('hydro.events.global')

    const eventsChannel = channels.get('hydro.events.global')
    const eventHandler = eventsChannel?.handlers.get('.App\\Events\\EventCreated')
    expect(eventHandler).toBeTypeOf('function')

    const callsBefore = apiGetMock.mock.calls.length
    eventHandler?.({
      id: 1001,
      kind: 'IRR_STATE_SNAPSHOT',
      zoneId: 7,
      message: 'snapshot',
      occurredAt: '2026-03-03T11:48:00Z',
    })

    await vi.advanceTimersByTimeAsync(1300)
    await flushPromises()

    expect(apiGetMock.mock.calls.length).toBeGreaterThan(callsBefore)

    wrapper.unmount()
  })
})
