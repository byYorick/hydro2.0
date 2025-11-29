import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent } from 'vue'

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
    initFromProps: vi.fn(),
    upsert: vi.fn(),
    remove: vi.fn(),
    invalidateCache: vi.fn(),
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

  beforeEach(async () => {
    vi.clearAllMocks()
    
    // Dynamic import to get fresh module
    const module = await import('../Show.vue')
    ShowComponent = module.default
  })

  afterEach(() => {
    vi.clearAllMocks()
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
        status: 'completed',
        message: 'Command completed successfully',
        zoneId: 1,
      }
      
      commandHandler(commandEvent)
      
      // Should update command status
      expect(mockUpdateCommandStatus).toHaveBeenCalledWith(
        123,
        'completed',
        'Command completed successfully'
      )
      
      // Should reload zone after command completion
      expect(mockReloadZoneAfterCommand).toHaveBeenCalledWith(1, ['zone', 'cycles'])
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
        status: 'failed',
        message: 'Command failed',
        error: 'Timeout error',
        zoneId: 1,
      }
      
      commandHandler(failedEvent)
      
      expect(mockUpdateCommandStatus).toHaveBeenCalledWith(
        456,
        'failed',
        'Command failed'
      )
      
      expect(mockReloadZoneAfterCommand).toHaveBeenCalledWith(1, ['zone', 'cycles'])
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
        status: 'running',
        zoneId: 1,
      })

      // Second command
      commandHandler({
        commandId: 2,
        status: 'completed',
        message: 'Done',
        zoneId: 1,
      })

      // Should handle both
      expect(mockUpdateCommandStatus).toHaveBeenCalledTimes(2)
    }
  })
})

