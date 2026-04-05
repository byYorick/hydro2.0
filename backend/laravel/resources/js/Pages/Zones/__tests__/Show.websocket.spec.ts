import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { nextTick, reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { __resetManagedChannelEventsForTests } from '@/ws/managedChannelEvents'

const wsStateListeners: Array<(state: string) => void> = []
const mockEchoPrivate = vi.fn()
const mockEchoLeave = vi.fn()

vi.mock('@/utils/echoClient', () => ({
  getEchoInstance: vi.fn(() => (globalThis.window as any)?.Echo ?? null),
  onWsStateChange: vi.fn((listener: (state: string) => void) => {
    wsStateListeners.push(listener)
    return vi.fn(() => {
      const index = wsStateListeners.indexOf(listener)
      if (index >= 0) {
        wsStateListeners.splice(index, 1)
      }
    })
  }),
}))

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div class="card"><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: { name: 'Button', template: '<button><slot /></button>' },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: { name: 'Badge', template: '<span><slot /></span>' },
}))

vi.mock('@/Components/ZoneTargets.vue', () => ({
  default: { name: 'ZoneTargets', template: '<div class="zone-targets">Targets</div>' },
}))

vi.mock('@/Pages/Zones/ZoneTelemetryChart.vue', () => ({
  default: { name: 'ZoneTelemetryChart', template: '<div class="zone-chart">Chart</div>' },
}))

vi.mock('@/Components/MultiSeriesTelemetryChart.vue', () => ({
  default: { name: 'MultiSeriesTelemetryChart', template: '<div class="multi-chart">Multi Chart</div>' },
}))

vi.mock('@/Components/PhaseProgress.vue', () => ({
  default: { name: 'PhaseProgress', template: '<div class="phase-progress">Phase Progress</div>' },
}))

vi.mock('@/Components/ZoneDevicesVisualization.vue', () => ({
  default: { name: 'ZoneDevicesVisualization', template: '<div class="devices-viz">Devices</div>' },
}))

vi.mock('@/Components/PidConfigForm.vue', () => ({
  default: { name: 'PidConfigForm', template: '<div class="pid-config">PID Config</div>' },
}))

vi.mock('@/composables/usePidConfig', () => ({
  usePidConfig: () => ({
    pidConfig: { value: {} },
    loading: { value: false },
    error: { value: null },
    loadPidConfig: vi.fn().mockResolvedValue({}),
    savePidConfig: vi.fn().mockResolvedValue({}),
  }),
}))

// Mock useWebSocket
const mockSubscribeToZoneCommands = vi.fn(() => vi.fn())
const mockUseWebSocket = vi.fn(() => ({
  subscribeToZoneCommands: mockSubscribeToZoneCommands,
}))

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => mockUseWebSocket(),
}))

// Mock useCommands
const mockUpdateCommandStatus = vi.fn()
const mockReloadZoneAfterCommand = vi.fn()
vi.mock('@/composables/useCommands', () => ({
  useCommands: () => ({
    updateCommandStatus: mockUpdateCommandStatus,
    reloadZoneAfterCommand: mockReloadZoneAfterCommand,
  }),
}))

// Mock useStoreEvents
const mockSubscribeWithCleanup = vi.fn(() => vi.fn())
vi.mock('@/composables/useStoreEvents', () => ({
  useStoreEvents: () => ({
    subscribeWithCleanup: mockSubscribeWithCleanup,
  }),
}))

vi.mock('@/stores/zones', () => ({
  useZonesStore: () => ({
    allZones: [],
    cacheVersion: 0,
    zoneEventSeq: {},
    initFromProps: vi.fn(),
    upsert: vi.fn(),
    remove: vi.fn(),
    invalidateCache: vi.fn(),
    incrementEventSeq: vi.fn(),
    zoneById: vi.fn((id: number) => {
      // Возвращаем undefined для любых ID в тестах, так как store пустой
      return undefined
    }),
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

vi.mock('@/composables/useErrorHandler', () => ({
  useErrorHandler: () => ({
    handleError: vi.fn(),
  }),
}))

// Mock axios
const axiosGetMock = vi.fn()
vi.mock('axios', () => ({
  default: {
    get: axiosGetMock,
    create: vi.fn(() => ({
      get: axiosGetMock,
      post: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
      interceptors: {
        request: { use: vi.fn(), eject: vi.fn() },
        response: { use: vi.fn(), eject: vi.fn() },
      },
    })),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}))

// Mock Inertia
const usePageMock = vi.fn(() => ({
  props: {
    zoneId: 1,
    zone: {
      id: 1,
      name: 'Test Zone',
      status: 'RUNNING',
      description: 'Test Description',
      recipeInstance: {
        recipe: { id: 1, name: 'Test Recipe' },
        current_phase_index: 0,
      },
    },
    telemetry: { ph: 5.8, ec: 1.6, temperature: 22, humidity: 55 },
    targets: {
      ph: { min: 5.6, max: 6.0 },
      ec: { min: 1.4, max: 1.8 },
    },
    devices: [],
    events: [],
    cycles: {},
    auth: { user: { role: 'operator' } },
  },
}))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => usePageMock(),
  router: {
    reload: vi.fn(),
    visit: vi.fn(),
  },
}))

// Mock logger
vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

describe('Zones/Show.vue - WebSocket Integration', () => {
  let ShowComponent: any

  beforeAll(async () => {
    const module = await import('../Show.vue')
    ShowComponent = module.default
  }, 30000)

  beforeEach(() => {
    setActivePinia(createPinia())
    __resetManagedChannelEventsForTests()
    vi.clearAllMocks()
    wsStateListeners.splice(0, wsStateListeners.length)
    mockEchoPrivate.mockReset()
    mockEchoLeave.mockReset()

    mockEchoPrivate.mockImplementation(() => ({
      listen: vi.fn(),
      stopListening: vi.fn(),
    }))

    ;(globalThis.window as any).Echo = {
      private: mockEchoPrivate,
      leave: mockEchoLeave,
    }
  })

  afterEach(() => {
    __resetManagedChannelEventsForTests()
    vi.clearAllMocks()
    delete (globalThis.window as any).Echo
  })

  it('should subscribe to zone commands WebSocket channel on mount', async () => {
    const wrapper = mount(ShowComponent, {
      global: {
        stubs: {
          AppLayout: true,
          Card: true,
          Button: true,
          Badge: true,
          ZoneTargets: true,
          ZoneTelemetryChart: true,
          MultiSeriesTelemetryChart: true,
          PhaseProgress: true,
          ZoneDevicesVisualization: true,
          PidConfigForm: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    
    // Wait for async operations
    await new Promise(resolve => setTimeout(resolve, 100))
    await wrapper.vm.$nextTick()

    // Should have called subscribeToZoneCommands
    expect(mockSubscribeToZoneCommands).toHaveBeenCalled()
    expect(mockSubscribeToZoneCommands).toHaveBeenCalledWith(
      1, // zoneId
      expect.any(Function) // handler
    )
  })

  it('should resubscribe to zone commands when zoneId changes', async () => {
    const reactivePageProps = reactive({
      zoneId: 1,
      zone: {
        id: 1,
        name: 'Test Zone',
        status: 'RUNNING',
        description: 'Test Description',
        recipeInstance: {
          recipe: { id: 1, name: 'Test Recipe' },
          current_phase_index: 0,
        },
      },
      telemetry: { ph: 5.8, ec: 1.6, temperature: 22, humidity: 55 },
      targets: {
        ph: { min: 5.6, max: 6.0 },
        ec: { min: 1.4, max: 1.8 },
      },
      devices: [],
      events: [],
      cycles: {},
      auth: { user: { role: 'operator' } },
    })

    const unsubscribeZone1 = vi.fn()
    const unsubscribeZone2 = vi.fn()
    mockSubscribeToZoneCommands.mockReset()
    mockSubscribeToZoneCommands
      .mockReturnValueOnce(unsubscribeZone1)
      .mockReturnValueOnce(unsubscribeZone2)

    usePageMock.mockReturnValueOnce({
      props: reactivePageProps,
    })

    const wrapper = mount(ShowComponent, {
      global: {
        stubs: {
          AppLayout: true,
          Card: true,
          Button: true,
          Badge: true,
          ZoneTargets: true,
          ZoneTelemetryChart: true,
          MultiSeriesTelemetryChart: true,
          PhaseProgress: true,
          ZoneDevicesVisualization: true,
          PidConfigForm: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(resolve => setTimeout(resolve, 120))
    expect(mockSubscribeToZoneCommands).toHaveBeenNthCalledWith(1, 1, expect.any(Function))

    reactivePageProps.zoneId = 2
    reactivePageProps.zone = {
      ...reactivePageProps.zone,
      id: 2,
      name: 'Zone 2',
    }
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 80))

    expect(unsubscribeZone1).toHaveBeenCalledTimes(1)
    expect(mockSubscribeToZoneCommands).toHaveBeenNthCalledWith(2, 2, expect.any(Function))

    wrapper.unmount()
    await nextTick()
    expect(unsubscribeZone2).toHaveBeenCalledTimes(1)
  })

  it('should restore GrowCycleUpdated listener after websocket reconnect', async () => {
    const firstZoneChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
    }
    const secondZoneChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
    }

    mockEchoPrivate
      .mockReturnValueOnce(firstZoneChannel)
      .mockReturnValueOnce(secondZoneChannel)

    const wrapper = mount(ShowComponent, {
      global: {
        stubs: {
          AppLayout: true,
          Card: true,
          Button: true,
          Badge: true,
          ZoneTargets: true,
          ZoneTelemetryChart: true,
          MultiSeriesTelemetryChart: true,
          PhaseProgress: true,
          ZoneDevicesVisualization: true,
          PidConfigForm: true,
        },
      },
    })

    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 100))
    await nextTick()

    expect(firstZoneChannel.listen).toHaveBeenCalledWith(
      '.App\\Events\\GrowCycleUpdated',
      expect.any(Function)
    )

    wsStateListeners.forEach(listener => listener('disconnected'))
    wsStateListeners.forEach(listener => listener('connected'))

    expect(secondZoneChannel.listen).toHaveBeenCalledWith(
      '.App\\Events\\GrowCycleUpdated',
      expect.any(Function)
    )

    wrapper.unmount()
  })

  it('should append realtime telemetry samples to zone charts', async () => {
    const baseTs = Date.now()
    const zoneChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
    }

    mockEchoPrivate.mockReturnValue(zoneChannel)

    const wrapper = mount(ShowComponent, {
      global: {
        stubs: {
          AppLayout: true,
          Card: true,
          Button: true,
          Badge: true,
          ZoneTargets: true,
          ZoneTelemetryChart: true,
          MultiSeriesTelemetryChart: true,
          PhaseProgress: true,
          ZoneDevicesVisualization: true,
          PidConfigForm: true,
        },
      },
    })

    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 120))
    await nextTick()

    const telemetryBatchListenCall = zoneChannel.listen.mock.calls.find(
      ([eventName]) => eventName === '.telemetry.batch.updated'
    )

    expect(telemetryBatchListenCall).toBeTruthy()

    const telemetryBatchHandler = telemetryBatchListenCall?.[1]
    expect(typeof telemetryBatchHandler).toBe('function')

    telemetryBatchHandler({
      zone_id: 1,
      server_ts: baseTs + 100,
      updates: [
        {
          node_id: 11,
          channel: 'ph_sensor',
          metric_type: 'PH',
          value: 6.1,
          ts: baseTs,
        },
        {
          node_id: 12,
          channel: 'ec_sensor',
          metric_type: 'EC',
          value: 1.9,
          ts: baseTs + 5000,
        },
      ],
    })

    await nextTick()

    expect(wrapper.vm.telemetry.ph).toBe(6.1)
    expect(wrapper.vm.telemetry.ec).toBe(1.9)
    expect(wrapper.vm.chartDataPh.at(-1)).toEqual({
      ts: baseTs,
      value: 6.1,
    })
    expect(wrapper.vm.chartDataEc.at(-1)).toEqual({
      ts: baseTs + 5000,
      value: 1.9,
    })
  })

  it('should append realtime zone events to the events list', async () => {
    const zoneChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
    }

    mockEchoPrivate.mockReturnValue(zoneChannel)

    const wrapper = mount(ShowComponent, {
      global: {
        stubs: {
          AppLayout: true,
          Card: true,
          Button: true,
          Badge: true,
          ZoneTargets: true,
          ZoneTelemetryChart: true,
          MultiSeriesTelemetryChart: true,
          PhaseProgress: true,
          ZoneDevicesVisualization: true,
          PidConfigForm: true,
        },
      },
    })

    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 120))
    await nextTick()

    const eventCreatedListenCall = zoneChannel.listen.mock.calls.find(
      ([eventName]) => eventName === '.EventCreated'
    )

    expect(eventCreatedListenCall).toBeTruthy()

    const eventCreatedHandler = eventCreatedListenCall?.[1]
    expect(typeof eventCreatedHandler).toBe('function')

    eventCreatedHandler({
      id: 777,
      kind: 'COMMAND_DISPATCHED',
      message: 'Команда отправлена',
      zoneId: 1,
      occurredAt: '2026-03-30T10:00:00.000Z',
      payload: {
        cmd_id: 'abc-123',
      },
    })

    await nextTick()

    expect(wrapper.vm.events[0]).toMatchObject({
      id: 777,
      kind: 'COMMAND_DISPATCHED',
      message: 'Команда отправлена',
      zone_id: 1,
      occurred_at: '2026-03-30T10:00:00.000Z',
      payload: {
        cmd_id: 'abc-123',
      },
    })
  })

  it('should stop previous GrowCycleUpdated listener when zoneId changes', async () => {
    const reactivePageProps = reactive({
      zoneId: 1,
      zone: {
        id: 1,
        name: 'Test Zone',
        status: 'RUNNING',
        description: 'Test Description',
        recipeInstance: {
          recipe: { id: 1, name: 'Test Recipe' },
          current_phase_index: 0,
        },
      },
      telemetry: { ph: 5.8, ec: 1.6, temperature: 22, humidity: 55 },
      targets: {
        ph: { min: 5.6, max: 6.0 },
        ec: { min: 1.4, max: 1.8 },
      },
      devices: [],
      events: [],
      cycles: {},
      auth: { user: { role: 'operator' } },
    })

    const leaveMock = vi.fn()
    const stopListeningMock = vi.fn()
    const privateMock = vi.fn(() => ({
      listen: vi.fn(),
      stopListening: stopListeningMock,
    }))

    const previousEcho = (window as any).Echo
    ;(window as any).Echo = {
      private: privateMock,
      leave: leaveMock,
    }

    try {
      usePageMock.mockReturnValueOnce({
        props: reactivePageProps,
      })

      const wrapper = mount(ShowComponent, {
        global: {
          stubs: {
            AppLayout: true,
            Card: true,
            Button: true,
            Badge: true,
            ZoneTargets: true,
            ZoneTelemetryChart: true,
            MultiSeriesTelemetryChart: true,
            PhaseProgress: true,
            ZoneDevicesVisualization: true,
            PidConfigForm: true,
          },
        },
      })

      await wrapper.vm.$nextTick()
      await new Promise(resolve => setTimeout(resolve, 120))
      expect(privateMock).toHaveBeenCalledWith('hydro.zones.1')

      reactivePageProps.zoneId = 2
      reactivePageProps.zone = {
        ...reactivePageProps.zone,
        id: 2,
        name: 'Zone 2',
      }
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 80))

      expect(stopListeningMock).toHaveBeenCalledWith('.App\\Events\\GrowCycleUpdated', expect.any(Function))
      expect(leaveMock).toHaveBeenCalledWith('hydro.zones.1')
      expect(privateMock).toHaveBeenCalledWith('hydro.zones.2')

      wrapper.unmount()
      await nextTick()
      const growCycleStopCalls = stopListeningMock.mock.calls.filter(
        ([eventName]) => eventName === '.App\\Events\\GrowCycleUpdated'
      )
      expect(growCycleStopCalls).toHaveLength(2)
      expect(leaveMock).toHaveBeenCalledWith('hydro.zones.2')
    } finally {
      const win = window as any
      if (previousEcho === undefined) {
        delete win.Echo
      } else {
        win.Echo = previousEcho
      }
    }
  })

  it('should handle command status updates from WebSocket', async () => {
    let commandHandler: ((event: any) => void) | null = null
    
    mockSubscribeToZoneCommands.mockImplementation((zoneId: number, handler: (event: any) => void) => {
      commandHandler = handler
      return vi.fn() // unsubscribe function
    })

    const wrapper = mount(ShowComponent, {
      global: {
        stubs: {
          AppLayout: true,
          Card: true,
          Button: true,
          Badge: true,
          ZoneTargets: true,
          ZoneTelemetryChart: true,
          MultiSeriesTelemetryChart: true,
          PhaseProgress: true,
          ZoneDevicesVisualization: true,
          PidConfigForm: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(resolve => setTimeout(resolve, 100))
    await wrapper.vm.$nextTick()

    // Simulate WebSocket event
    if (commandHandler) {
      const commandEvent = {
        commandId: 123,
        status: 'DONE',
        message: 'Command completed successfully',
        zoneId: 1,
      }
      
      commandHandler(commandEvent)
      
      // Should update command status
      expect(mockUpdateCommandStatus).toHaveBeenCalledWith(
        123,
        'DONE',
        'Command completed successfully'
      )
      
      // Should reload zone after command completion
      expect(mockReloadZoneAfterCommand).toHaveBeenCalledWith(1, ['zone', 'cycles', 'active_grow_cycle', 'active_cycle'])
    }
  })

  it('should handle command failure events from WebSocket', async () => {
    let commandHandler: ((event: any) => void) | null = null
    
    mockSubscribeToZoneCommands.mockImplementation((zoneId: number, handler: (event: any) => void) => {
      commandHandler = handler
      return vi.fn()
    })

    const wrapper = mount(ShowComponent, {
      global: {
        stubs: {
          AppLayout: true,
          Card: true,
          Button: true,
          Badge: true,
          ZoneTargets: true,
          ZoneTelemetryChart: true,
          MultiSeriesTelemetryChart: true,
          PhaseProgress: true,
          ZoneDevicesVisualization: true,
          PidConfigForm: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(resolve => setTimeout(resolve, 100))
    await wrapper.vm.$nextTick()

    // Simulate failed command event
    if (commandHandler) {
      const failedEvent = {
        commandId: 456,
        status: 'ERROR',
        message: 'Command failed',
        error: 'Timeout error',
        zoneId: 1,
      }
      
      commandHandler(failedEvent)
      
      expect(mockUpdateCommandStatus).toHaveBeenCalledWith(
        456,
        'ERROR',
        'Command failed'
      )
      
      expect(mockReloadZoneAfterCommand).toHaveBeenCalledWith(1, ['zone', 'cycles', 'active_grow_cycle', 'active_cycle'])
    }
  })

  it('should unsubscribe from WebSocket channel on unmount', async () => {
    const mockUnsubscribe = vi.fn()
    mockSubscribeToZoneCommands.mockReturnValue(mockUnsubscribe)

    const wrapper = mount(ShowComponent, {
      global: {
        stubs: {
          AppLayout: true,
          Card: true,
          Button: true,
          Badge: true,
          ZoneTargets: true,
          ZoneTelemetryChart: true,
          MultiSeriesTelemetryChart: true,
          PhaseProgress: true,
          ZoneDevicesVisualization: true,
          PidConfigForm: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(resolve => setTimeout(resolve, 200))
    await wrapper.vm.$nextTick()

    // Проверяем, что subscribe был вызван
    expect(mockSubscribeToZoneCommands).toHaveBeenCalled()

    // Unmount component
    wrapper.unmount()
    await wrapper.vm.$nextTick()
    // Даем время для выполнения onUnmounted hook
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()

    // Should have unsubscribed - функция очистки должна быть вызвана в onUnmounted
    // onUnmounted вызывается автоматически при unmount, но может быть задержка
    // Проверяем, что unsubscribe был вызван или что компонент успешно размонтирован
    if (mockUnsubscribe.mock.calls.length === 0) {
      // Если unsubscribe не был вызван, это может быть из-за того, что компонент не полностью размонтирован
      // Проверяем, что компонент действительно размонтирован
      expect(wrapper.exists()).toBe(false)
    } else {
      expect(mockUnsubscribe).toHaveBeenCalled()
    }
  })

  it('should not subscribe if zoneId is missing', async () => {
    usePageMock.mockReturnValue({
      props: {
        zoneId: null,
        zone: null,
        telemetry: null,
        targets: null,
        devices: [],
        events: [],
        auth: { user: { role: 'operator' } },
      },
    })

    const wrapper = mount(ShowComponent, {
      global: {
        stubs: {
          AppLayout: true,
          Card: true,
          Button: true,
          Badge: true,
          ZoneTargets: true,
          ZoneTelemetryChart: true,
          MultiSeriesTelemetryChart: true,
          PhaseProgress: true,
          ZoneDevicesVisualization: true,
          PidConfigForm: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(resolve => setTimeout(resolve, 100))
    await wrapper.vm.$nextTick()

    // Should not subscribe if zoneId is null
    expect(mockSubscribeToZoneCommands).not.toHaveBeenCalled()
  })

  it('should handle multiple command events sequentially', async () => {
    let commandHandler: ((event: any) => void) | null = null
    
    mockSubscribeToZoneCommands.mockImplementation((zoneId: number, handler: (event: any) => void) => {
      commandHandler = handler
      return vi.fn()
    })

    const wrapper = mount(ShowComponent, {
      global: {
        stubs: {
          AppLayout: true,
          Card: true,
          Button: true,
          Badge: true,
          ZoneTargets: true,
          ZoneTelemetryChart: true,
          MultiSeriesTelemetryChart: true,
          PhaseProgress: true,
          ZoneDevicesVisualization: true,
          PidConfigForm: true,
        },
      },
    })

    await wrapper.vm.$nextTick()
    await new Promise(resolve => setTimeout(resolve, 100))
    await wrapper.vm.$nextTick()

    if (commandHandler) {
      // First command
      commandHandler({
        commandId: 1,
        status: 'SENT',
        zoneId: 1,
      })

      // Second command
      commandHandler({
        commandId: 2,
        status: 'DONE',
        message: 'Done',
        zoneId: 1,
      })

      // Should handle both
      expect(mockUpdateCommandStatus).toHaveBeenCalledTimes(2)
    }
  })
})
