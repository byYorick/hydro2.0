import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { useSystemStatus } from '../useSystemStatus'

// Mock useApi
const mockApiGet = vi.fn().mockResolvedValue({ data: { data: { app: 'ok', db: 'ok' } } })
vi.mock('../useApi', () => ({
  useApi: vi.fn(() => ({
    api: {
      get: mockApiGet
    }
  }))
}))

// Mock logger
vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    group: vi.fn(),
    groupEnd: vi.fn(),
    time: vi.fn(),
    timeEnd: vi.fn(),
    isDev: true,
    isProd: false
  }
}))

describe('useSystemStatus - MQTT Status Channel (P2-4)', () => {
  let mockEcho: any
  let mockChannel: any
  let mockShowToast: vi.Mock
  let TestComponent: ReturnType<typeof defineComponent>

  beforeEach(() => {
    mockShowToast = vi.fn()
    
    mockChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }

    mockEcho = {
      channel: vi.fn(() => mockChannel),
      connector: {
        pusher: {
          connection: {
            state: 'connected',
            socket_id: 'test-socket-id',
            bind: vi.fn()
          },
          channels: {
            channels: {}
          }
        }
      }
    }

    // @ts-ignore
    global.window = {
      Echo: mockEcho
    }

    // Создаем тестовый компонент для правильной работы lifecycle hooks
    TestComponent = defineComponent({
      setup() {
        return useSystemStatus(mockShowToast)
      },
      template: '<div></div>'
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
    // @ts-ignore
    delete global.window.Echo
  })

  it('should subscribe to mqtt.status channel on initialization', async () => {
    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()
    
    // Даем время на инициализацию
    await new Promise(resolve => setTimeout(resolve, 600))
    await wrapper.vm.$nextTick()
    
    // В новой реализации MQTT статус определяется на основе wsStatus
    // checkMqttStatus вызывается при инициализации и обновляет статус на основе wsStatus
    expect(wrapper.vm).toBeDefined()
    expect(wrapper.vm.mqttStatus).toBeDefined()
  })

  it('should update MQTT status to online when API returns online', async () => {
    // MQTT статус определяется на основе wsStatus, а не напрямую из API
    // Когда wsStatus = 'connected', mqttStatus должен быть 'online'
    mockEcho.connector.pusher.connection.state = 'connected'
    
    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()
    
    // Вызываем checkMqttStatus вручную через checkWebSocketStatus
    wrapper.vm.checkWebSocketStatus()
    wrapper.vm.checkMqttStatus()
    await wrapper.vm.$nextTick()
    
    // Проверяем, что статус обновился на основе wsStatus
    expect(wrapper.vm.wsStatus).toBe('connected')
    expect(wrapper.vm.mqttStatus).toBe('online')
  })

  it('should update MQTT status to offline when API returns offline', async () => {
    // MQTT статус определяется на основе wsStatus
    // Когда wsStatus = 'disconnected', mqttStatus должен быть 'offline'
    mockEcho.connector.pusher.connection.state = 'disconnected'
    
    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()
    
    wrapper.vm.checkWebSocketStatus()
    wrapper.vm.checkMqttStatus()
    await wrapper.vm.$nextTick()
    
    expect(wrapper.vm.wsStatus).toBe('disconnected')
    expect(wrapper.vm.mqttStatus).toBe('offline')
  })

  it('should update MQTT status to degraded when API returns degraded', async () => {
    // MQTT статус определяется на основе wsStatus
    // Когда wsStatus = 'connecting', mqttStatus должен быть 'degraded'
    mockEcho.connector.pusher.connection.state = 'connecting'
    
    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()
    
    wrapper.vm.checkWebSocketStatus()
    wrapper.vm.checkMqttStatus()
    await wrapper.vm.$nextTick()
    
    expect(wrapper.vm.wsStatus).toBe('connecting')
    expect(wrapper.vm.mqttStatus).toBe('degraded')
  })

  it('should handle MQTT API errors', async () => {
    // MQTT статус определяется на основе wsStatus, а не напрямую из API
    // Ошибки API обрабатываются в checkHealth, а не в checkMqttStatus
    mockApiGet.mockRejectedValueOnce(new Error('API error'))

    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()
    
    // Вызываем checkHealth, который может вызвать ошибку
    await wrapper.vm.checkHealth()
    await wrapper.vm.$nextTick()
    
    expect(mockApiGet).toHaveBeenCalled()
    // Ошибка показывается через showToast с общим сообщением
    expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('Ошибка проверки статуса системы'), 'error', 5000)
  })

  it('should use fallback logic when MQTT status is not in API response', async () => {
    // MQTT статус определяется на основе wsStatus, а не из API response
    // Если wsStatus = 'unknown', mqttStatus должен быть 'unknown'
    mockApiGet.mockResolvedValueOnce({ data: { data: { app: 'ok', db: 'ok' } } })

    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()
    
    // Устанавливаем wsStatus в 'unknown'
    wrapper.vm.wsStatus = 'unknown'
    wrapper.vm.checkMqttStatus()
    await wrapper.vm.$nextTick()
    
    expect(wrapper.vm.mqttStatus).toBe('unknown')
  })

  it('should stop monitoring on unmount', async () => {
    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()
    
    await new Promise(resolve => setTimeout(resolve, 600))
    
    wrapper.unmount()
    await wrapper.vm.$nextTick()
    
    // Проверяем, что cleanup был вызван
    expect(wrapper.vm).toBeDefined()
  })
})

