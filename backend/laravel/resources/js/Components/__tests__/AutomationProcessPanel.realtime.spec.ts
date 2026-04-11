import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

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

async function unwrapRealtime(rawPromise: Promise<unknown>): Promise<unknown> {
  const raw = await rawPromise
  if (raw && typeof raw === 'object' && 'data' in (raw as Record<string, unknown>)) {
    return (raw as { data: unknown }).data
  }
  return raw
}

vi.mock('@/services/api', () => ({
  api: {
    zones: {
      getState: (zoneId: number) =>
        unwrapRealtime(apiGetMock(`/api/zones/${zoneId}/state`)),
    },
  },
}))

vi.mock('@/utils/echoClient', () => ({
  getEchoInstance: () => echoHolder.current,
  getConnectionState: () => ({ state: 'connected' }),
  onWsStateChange: () => () => {},
}))

import AutomationProcessPanel from '../AutomationProcessPanel.vue'
import { useZonesStore } from '@/stores/zones'

const mockStateResponse = {
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
}

describe('AutomationProcessPanel realtime refresh', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    apiGetMock.mockReset()
    apiGetMock.mockResolvedValue(mockStateResponse)
  })

  afterEach(() => {
    echoHolder.current = null
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('обновляет состояние при incrementEventSeq через zonesStore', async () => {
    echoHolder.current = {
      private: vi.fn((channelName: string) => ({
        listen: vi.fn().mockReturnThis(),
        stopListening: vi.fn().mockReturnThis(),
      })),
      leave: vi.fn(),
    }

    const wrapper = shallowMount(AutomationProcessPanel, {
      props: { zoneId: 7 },
    })

    await flushPromises()
    await vi.advanceTimersByTimeAsync(1300)
    await flushPromises()

    // hydro.zones.7 больше НЕ подписывается — только hydro.commands.7
    expect(echoHolder.current.private).not.toHaveBeenCalledWith('hydro.zones.7')
    expect(echoHolder.current.private).toHaveBeenCalledWith('hydro.commands.7')

    const callsBefore = apiGetMock.mock.calls.length

    // Имитируем зональное событие через zonesStore — как это делает useZonePageState
    const zonesStore = useZonesStore()
    zonesStore.incrementEventSeq(7)

    await vi.advanceTimersByTimeAsync(1300)
    await flushPromises()

    expect(apiGetMock.mock.calls.length).toBeGreaterThan(callsBefore)

    wrapper.unmount()
  })

  it('команды на hydro.commands.{id} по-прежнему триггерят рефреш', async () => {
    const commandsChannel = {
      handlers: new Map<string, (payload: Record<string, unknown>) => void>(),
      listen: vi.fn(function (this: typeof commandsChannel, eventName: string, handler: (p: Record<string, unknown>) => void) {
        this.handlers.set(eventName, handler)
        return this
      }),
      stopListening: vi.fn().mockReturnThis(),
    }

    echoHolder.current = {
      private: vi.fn((channelName: string) => {
        if (channelName === 'hydro.commands.7') return commandsChannel
        return { listen: vi.fn().mockReturnThis(), stopListening: vi.fn().mockReturnThis() }
      }),
      leave: vi.fn(),
    }

    const wrapper = shallowMount(AutomationProcessPanel, {
      props: { zoneId: 7 },
    })

    await flushPromises()
    await vi.advanceTimersByTimeAsync(1300)
    await flushPromises()

    const commandHandler = commandsChannel.handlers.get('.App\\Events\\CommandStatusUpdated')
    expect(commandHandler).toBeTypeOf('function')

    const callsBefore = apiGetMock.mock.calls.length
    commandHandler?.({ commandId: 'cmd-1', status: 'DONE' })

    await vi.advanceTimersByTimeAsync(1300)
    await flushPromises()

    expect(apiGetMock.mock.calls.length).toBeGreaterThan(callsBefore)

    wrapper.unmount()
  })
})
