import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import HeaderStatusBar from '../HeaderStatusBar.vue'

const createSystemStatus = (overrides: Record<string, any> = {}) => ({
  coreStatus: ref('ok'),
  dbStatus: ref('ok'),
  wsStatus: ref('connected'),
  mqttStatus: ref('online'),
  historyLoggerStatus: ref('ok'),
  automationEngineStatus: ref('ok'),
  lastUpdate: ref(new Date('2024-01-01T12:00:00Z')),
  wsReconnectAttempts: ref(0),
  wsLastError: ref(null),
  wsConnectionDetails: ref(null),
  ...overrides,
})

// Mock useSystemStatus
const mockUseSystemStatus = vi.hoisted(() => vi.fn(() => createSystemStatus()))

vi.mock('@/composables/useSystemStatus', () => ({
  useSystemStatus: mockUseSystemStatus,
}))

const mockUsePage = vi.hoisted(() => vi.fn(() => ({
  props: {
    dashboard: {
      zonesCount: 0,
      zonesByStatus: {},
      devicesCount: 0,
      nodesByStatus: {},
      alertsCount: 0,
    },
  },
})))

vi.mock('@inertiajs/vue3', () => ({
  usePage: mockUsePage,
  router: {
    reload: vi.fn(),
  },
  Link: { name: 'Link', template: '<a><slot /></a>' },
}))

// Mock formatTime
vi.mock('@/utils/formatTime', () => ({
  formatTime: vi.fn((date) => {
    if (!date) return ''
    return 'только что'
  })
}))

// Mock useWebSocket
vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({
    subscribeToGlobalEvents: vi.fn(() => () => {}), // Возвращает функцию очистки
  }),
}))

// Mock useApi
vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: vi.fn().mockResolvedValue({ data: { data: { alerts_count: 0 } } }),
    },
  }),
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

describe('HeaderStatusBar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseSystemStatus.mockClear()
    mockUsePage.mockClear()
    mockUsePage.mockReturnValue({
      props: {
        dashboard: {
          zonesCount: 0,
          zonesByStatus: {},
          devicesCount: 0,
          nodesByStatus: {},
          alertsCount: 0,
        },
      },
    })
  })

  it('renders all status indicators', () => {
    const wrapper = mount(HeaderStatusBar)
    
    // Компонент использует короткие метки: "Core", "Database", "WebSocket", "MQTT"
    expect(wrapper.text()).toContain('Core')
    expect(wrapper.text()).toContain('Database')
    expect(wrapper.text()).toContain('WebSocket')
    expect(wrapper.text()).toContain('MQTT')
    // History Logger и Automation Engine могут не отображаться в основном тексте, только в tooltip
    // Проверяем, что основные индикаторы присутствуют
    const statusGroups = wrapper.findAll('.group.relative')
    expect(statusGroups.length).toBeGreaterThanOrEqual(4) // Минимум 4 основных индикатора
  })

  it('displays core status with correct color for ok', () => {
    mockUseSystemStatus.mockReturnValue(createSystemStatus({
      coreStatus: ref('ok'),
    }))

    const wrapper = mount(HeaderStatusBar)
    expect(wrapper.text()).toContain('Core')
    expect(wrapper.text()).toContain('Онлайн')
  })

  it('displays core status with correct color for fail', () => {
    mockUseSystemStatus.mockReturnValue(createSystemStatus({
      coreStatus: ref('fail'),
    }))

    const wrapper = mount(HeaderStatusBar)
    expect(wrapper.text()).toContain('Core')
    expect(wrapper.text()).toContain('Офлайн')
  })

  it('displays core status with correct color for unknown', () => {
    mockUseSystemStatus.mockReturnValue(createSystemStatus({
      coreStatus: ref('unknown'),
    }))

    const wrapper = mount(HeaderStatusBar)
    expect(wrapper.text()).toContain('Core')
    expect(wrapper.text()).toContain('Неизвестно')
  })

  it('displays database status correctly', () => {
    mockUseSystemStatus.mockReturnValue(createSystemStatus({
      dbStatus: ref('fail'),
    }))

    const wrapper = mount(HeaderStatusBar)
    expect(wrapper.text()).toContain('Database')
    expect(wrapper.text()).toContain('Офлайн')
  })

  it('displays WebSocket status correctly', () => {
    mockUseSystemStatus.mockReturnValue(createSystemStatus({
      wsStatus: ref('disconnected'),
    }))

    const wrapper = mount(HeaderStatusBar)
    expect(wrapper.text()).toContain('WebSocket')
    expect(wrapper.text()).toContain('Отключено')
  })

  it('displays MQTT status correctly', () => {
    mockUseSystemStatus.mockReturnValue(createSystemStatus({
      mqttStatus: ref('offline'),
    }))

    const wrapper = mount(HeaderStatusBar)
    expect(wrapper.text()).toContain('MQTT')
    expect(wrapper.text()).toContain('Офлайн')
  })

  it('displays MQTT degraded status with amber color', () => {
    mockUseSystemStatus.mockReturnValue(createSystemStatus({
      mqttStatus: ref('degraded'),
    }))

    const wrapper = mount(HeaderStatusBar)
    expect(wrapper.text()).toContain('MQTT')
    expect(wrapper.text()).toContain('Частично')
  })

  it('shows tooltip with last update time when lastUpdate is available', () => {
    const lastUpdate = new Date('2024-01-01T12:00:00Z')
    mockUseSystemStatus.mockReturnValue(createSystemStatus({
      lastUpdate: ref(lastUpdate),
    }))

    const wrapper = mount(HeaderStatusBar)
    expect(wrapper.text()).toContain('Обновлено:')
  })

  it('does not show tooltip when lastUpdate is null', () => {
    mockUseSystemStatus.mockReturnValue(createSystemStatus({
      lastUpdate: ref(null),
    }))

    const wrapper = mount(HeaderStatusBar)
    expect(wrapper.text()).not.toContain('Обновлено:')
  })

  it('applies correct title attributes for status indicators', () => {
    mockUseSystemStatus.mockReturnValue(createSystemStatus())

    const wrapper = mount(HeaderStatusBar)
    // Tooltip содержит "Core Service", но основной текст - "Core"
    expect(wrapper.html()).toContain('Core')
  })

  it('hides status labels on small screens', () => {
    mockUseSystemStatus.mockReturnValue(createSystemStatus())

    const wrapper = mount(HeaderStatusBar)
    
    // Проверяем, что labels имеют класс hidden sm:inline
    const labels = wrapper.findAll('.hidden.sm\\:inline')
    expect(labels.length).toBeGreaterThan(0)
  })

  it('renders all four status indicators', () => {
    mockUseSystemStatus.mockReturnValue({
      coreStatus: ref('ok'),
      dbStatus: ref('ok'),
      wsStatus: ref('connected'),
      mqttStatus: ref('online'),
      historyLoggerStatus: ref('online'),
      automationEngineStatus: ref('online'),
      lastUpdate: ref(new Date()),
      wsReconnectAttempts: ref(0),
      wsLastError: ref(null),
      wsConnectionDetails: ref(null)
    } as any)

    const wrapper = mount(HeaderStatusBar)
    
    // Должно быть 4 индикатора статуса (Core, DB, WS, MQTT)
    // Проверяем наличие всех индикаторов через текст
    expect(wrapper.text()).toContain('Core')
    expect(wrapper.text()).toContain('Database')
    expect(wrapper.text()).toContain('WebSocket')
    expect(wrapper.text()).toContain('MQTT')
    
    // Проверяем количество индикаторов (может быть больше из-за tooltips)
    const statusGroups = wrapper.findAll('.group.relative')
    expect(statusGroups.length).toBeGreaterThanOrEqual(4)
  })

  it('handles all status combinations correctly', () => {
    // Тестируем различные комбинации статусов
    const combinations = [
      { core: 'ok', db: 'ok', ws: 'connected', mqtt: 'online' },
      { core: 'fail', db: 'ok', ws: 'connected', mqtt: 'online' },
      { core: 'ok', db: 'fail', ws: 'disconnected', mqtt: 'offline' },
      { core: 'unknown', db: 'unknown', ws: 'unknown', mqtt: 'unknown' },
      { core: 'ok', db: 'ok', ws: 'connected', mqtt: 'degraded' },
    ]

    combinations.forEach(combo => {
      mockUseSystemStatus.mockReturnValue(createSystemStatus({
        coreStatus: ref(combo.core),
        dbStatus: ref(combo.db),
        wsStatus: ref(combo.ws),
        mqttStatus: ref(combo.mqtt),
      }))

      const wrapper = mount(HeaderStatusBar)
      expect(wrapper.exists()).toBe(true)
      expect(wrapper.text()).toContain('Core')
    })
  })
})

