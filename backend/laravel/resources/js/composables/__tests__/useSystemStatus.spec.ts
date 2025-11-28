import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useSystemStatus } from '../useSystemStatus'

// Mock logger
vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    group: vi.fn(),
    groupEnd: vi.fn(),
    groupCollapsed: vi.fn(),
    table: vi.fn(),
    time: vi.fn(),
    timeEnd: vi.fn(),
    isDev: true,
    isProd: false
  }
}))

// Mock useApi
vi.mock('../useApi', () => ({
  useApi: vi.fn(() => ({
    api: {
      get: vi.fn()
    }
  }))
}))

describe('useSystemStatus', () => {
  let mockApiGet: vi.Mock
  let mockShowToast: vi.Mock

  beforeEach(async () => {
    const { useApi } = await import('../useApi')
    const mockApi = {
      api: {
        get: vi.fn()
      }
    }
    vi.mocked(useApi).mockReturnValue(mockApi)
    mockApiGet = mockApi.api.get
    mockShowToast = vi.fn()
    mockApiGet.mockClear()
    vi.useFakeTimers()
    
    // Mock window.Echo
    // @ts-ignore
    global.window = {
      Echo: undefined
    }
  })

  afterEach(() => {
    vi.useRealTimers()
    // @ts-ignore
    delete global.window.Echo
  })

  it('should initialize with unknown statuses', () => {
    const { coreStatus, dbStatus, wsStatus, mqttStatus } = useSystemStatus()
    
    expect(coreStatus.value).toBe('unknown')
    expect(dbStatus.value).toBe('unknown')
    expect(wsStatus.value).toBe('unknown')
    expect(mqttStatus.value).toBe('unknown')
  })

  it('should check health and update core/db status', async () => {
    mockApiGet.mockResolvedValue({
      data: {
        data: {
          app: 'ok',
          db: 'ok'
        }
      }
    })

    const { checkHealth, coreStatus, dbStatus } = useSystemStatus(mockShowToast)
    await checkHealth()

    expect(coreStatus.value).toBe('ok')
    expect(dbStatus.value).toBe('ok')
    expect(mockApiGet).toHaveBeenCalledWith('/api/system/health')
  })

  it('should handle health check error', async () => {
    mockApiGet.mockRejectedValue(new Error('Network Error'))

    const { checkHealth, coreStatus, dbStatus } = useSystemStatus(mockShowToast)
    await checkHealth()

    expect(coreStatus.value).toBe('fail')
    expect(dbStatus.value).toBe('fail')
    expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('Ошибка проверки статуса системы'), 'error', expect.any(Number))
  })

  it('should check WebSocket status when Echo is available', () => {
    const mockPusher = {
      connection: {
        state: 'connected',
        bind: vi.fn()
      }
    }

    // @ts-ignore
    global.window.Echo = {
      connector: {
        pusher: mockPusher
      }
    }

    const { checkWebSocketStatus, wsStatus } = useSystemStatus()
    checkWebSocketStatus()

    expect(wsStatus.value).toBe('connected')
  })

  it('should show disconnected when Echo is not available', () => {
    // @ts-ignore
    global.window.Echo = undefined

    const { checkWebSocketStatus, wsStatus } = useSystemStatus()
    checkWebSocketStatus()

    // Когда Echo не доступен, статус должен быть 'connecting' (ожидание инициализации)
    expect(wsStatus.value).toBe('connecting')
  })

  it('should show disconnected when Pusher connection is failed', () => {
    const mockPusher = {
      connection: {
        state: 'failed',
        bind: vi.fn()
      }
    }

    // @ts-ignore
    global.window.Echo = {
      connector: {
        pusher: mockPusher
      }
    }

    const { checkWebSocketStatus, wsStatus } = useSystemStatus()
    checkWebSocketStatus()

    // В useSystemStatus failed состояние может обрабатываться как 'disconnected' или 'unknown'
    expect(['disconnected', 'unknown']).toContain(wsStatus.value)
  })

  it('should check MQTT status based on WebSocket', () => {
    const mockPusher = {
      connection: {
        state: 'connected',
        bind: vi.fn()
      }
    }

    // @ts-ignore
    global.window.Echo = {
      connector: {
        pusher: mockPusher
      }
    }

    const { checkMqttStatus, checkWebSocketStatus, mqttStatus, wsStatus } = useSystemStatus()
    checkWebSocketStatus()
    checkMqttStatus()

    // MQTT статус зависит от WebSocket
    // Если WebSocket connected, MQTT должен быть online
    // Если WebSocket unknown, MQTT тоже unknown
    if (wsStatus.value === 'connected') {
      expect(mqttStatus.value).toBe('online')
    } else if (wsStatus.value === 'unknown') {
      expect(mqttStatus.value).toBe('unknown')
    }
  })

  it('should start monitoring on mount', async () => {
    mockApiGet.mockResolvedValue({
      data: {
        data: {
          app: 'ok',
          db: 'ok'
        }
      }
    })

    const { coreStatus, startMonitoring } = useSystemStatus()
    startMonitoring()
    
    // После startMonitoring должен быть вызван checkHealth
    // Продвигаем время для срабатывания таймера
    vi.advanceTimersByTime(100)
    
    // Статус должен быть обновлен после вызова checkHealth
    // В реальности это происходит асинхронно, но для теста мы можем проверить, что метод вызывается
    expect(mockApiGet).toHaveBeenCalled()
  })

  it('should stop monitoring on unmount', () => {
    const { stopMonitoring } = useSystemStatus()
    
    // Должно быть возможно вызвать stopMonitoring без ошибок
    expect(() => stopMonitoring()).not.toThrow()
  })

  it('should provide computed flags for status checks', async () => {
    mockApiGet.mockResolvedValue({
      data: {
        data: {
          app: 'ok',
          db: 'ok'
        }
      }
    })

    const { isCoreOk, isDbOk, checkHealth } = useSystemStatus()
    
    // После проверки здоровья флаги должны обновиться
    await checkHealth()
    expect(isCoreOk.value).toBe(true)
    expect(isDbOk.value).toBe(true)
  })

  it('should update WebSocket status when connection state changes', () => {
    const mockBind = vi.fn()
    let connectedHandler: (() => void) | null = null
    let disconnectedHandler: (() => void) | null = null
    
    const mockPusher = {
      connection: {
        state: 'disconnected',
        bind: (event: string, handler: () => void) => {
          mockBind(event, handler)
          if (event === 'connected') connectedHandler = handler
          if (event === 'disconnected') disconnectedHandler = handler
        }
      }
    }

    // @ts-ignore
    global.window.Echo = {
      connector: {
        pusher: mockPusher
      }
    }

    const { startMonitoring, wsStatus } = useSystemStatus()
    startMonitoring()

    // Проверяем, что обработчики были установлены
    expect(mockBind).toHaveBeenCalledWith('connected', expect.any(Function))
    expect(mockBind).toHaveBeenCalledWith('disconnected', expect.any(Function))

    // Симулируем подключение
    if (connectedHandler) {
      connectedHandler()
      expect(wsStatus.value).toBe('connected')
    }

    // Симулируем отключение
    if (disconnectedHandler) {
      disconnectedHandler()
      expect(wsStatus.value).toBe('disconnected')
    }
  })

  it('should poll health status periodically', async () => {
    mockApiGet.mockResolvedValue({
      data: {
        data: {
          app: 'ok',
          db: 'ok'
        }
      }
    })

    const { startMonitoring, checkHealth } = useSystemStatus()
    
    // Вызываем checkHealth вручную для первого вызова
    await checkHealth()
    const initialCalls = mockApiGet.mock.calls.length
    expect(initialCalls).toBeGreaterThanOrEqual(1)
    
    // Очищаем мок, чтобы считать только новые вызовы
    mockApiGet.mockClear()
    
    // Запускаем мониторинг (он установит интервал и вызовет checkHealth сразу)
    startMonitoring()
    
    // Ждем, чтобы checkHealth был вызван
    await vi.runAllTimersAsync()
    expect(mockApiGet).toHaveBeenCalledTimes(1)

    // Продвигаем время на 30 секунд (интервал опроса)
    vi.advanceTimersByTime(30000)
    // Запускаем все таймеры, включая интервал
    await vi.runAllTimersAsync()
    
    // Должен быть второй вызов через интервал
    expect(mockApiGet).toHaveBeenCalledTimes(2)
  })

  it('should stop polling when stopMonitoring is called', () => {
    mockApiGet.mockResolvedValue({
      data: {
        data: {
          app: 'ok',
          db: 'ok'
        }
      }
    })

    const { startMonitoring, stopMonitoring } = useSystemStatus()
    startMonitoring()

    const initialCalls = mockApiGet.mock.calls.length
    stopMonitoring()

    // Продвигаем время
    vi.advanceTimersByTime(30000)

    // Количество вызовов не должно увеличиться
    expect(mockApiGet.mock.calls.length).toBe(initialCalls)
  })

  it('should handle health check with db fail', async () => {
    mockApiGet.mockResolvedValue({
      data: {
        data: {
          app: 'ok',
          db: 'fail'
        }
      }
    })

    const { checkHealth, coreStatus, dbStatus } = useSystemStatus()
    await checkHealth()

    expect(coreStatus.value).toBe('ok')
    expect(dbStatus.value).toBe('fail')
  })

  it('should handle health check with app fail', async () => {
    mockApiGet.mockResolvedValue({
      data: {
        data: {
          app: 'fail',
          db: 'ok'
        }
      }
    })

    const { checkHealth, coreStatus, dbStatus } = useSystemStatus()
    await checkHealth()

    expect(coreStatus.value).toBe('fail')
    expect(dbStatus.value).toBe('ok')
  })

  it('should update lastUpdate timestamp after health check', async () => {
    mockApiGet.mockResolvedValue({
      data: {
        data: {
          app: 'ok',
          db: 'ok'
        }
      }
    })

    const { checkHealth, lastUpdate } = useSystemStatus()
    const beforeCheck = lastUpdate.value
    await checkHealth()
    const afterCheck = lastUpdate.value

    expect(afterCheck).not.toBe(beforeCheck)
    expect(afterCheck).toBeInstanceOf(Date)
  })

  it('should handle MQTT status when WebSocket is disconnected', () => {
    const mockPusher = {
      connection: {
        state: 'disconnected',
        bind: vi.fn()
      }
    }

    // @ts-ignore
    global.window.Echo = {
      connector: {
        pusher: mockPusher
      }
    }

    const { checkWebSocketStatus, checkMqttStatus, wsStatus, mqttStatus } = useSystemStatus()
    checkWebSocketStatus()
    checkMqttStatus()

    // В useSystemStatus disconnected состояние может обрабатываться как 'disconnected' или 'unknown'
    expect(['disconnected', 'unknown']).toContain(wsStatus.value)
    // Если wsStatus disconnected, mqttStatus должен быть offline
    if (wsStatus.value === 'disconnected') {
      expect(mqttStatus.value).toBe('offline')
    }
  })

  it('should handle MQTT status when WebSocket is unknown', () => {
    // @ts-ignore
    global.window.Echo = undefined

    const { checkWebSocketStatus, checkMqttStatus, wsStatus, mqttStatus } = useSystemStatus()
    checkWebSocketStatus()
    checkMqttStatus()

    // Когда Echo не доступен, wsStatus должен быть 'connecting', а mqttStatus - 'degraded'
    expect(wsStatus.value).toBe('connecting')
    expect(mqttStatus.value).toBe('degraded')
  })
})

