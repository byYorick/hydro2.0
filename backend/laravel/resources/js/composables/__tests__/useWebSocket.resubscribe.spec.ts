import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

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

// Mock echoClient - создаем переменную для динамического возврата mockEcho
let mockEchoInstance: any = null

const mockGetEchoInstance = vi.fn(() => mockEchoInstance)
const mockGetEcho = vi.fn(() => mockEchoInstance)

vi.mock('@/utils/echoClient', () => ({
  onWsStateChange: vi.fn(() => vi.fn()), // Returns unsubscribe function
  getEchoInstance: mockGetEchoInstance,
  getEcho: mockGetEcho,
  getReconnectAttempts: vi.fn(() => 0),
  getLastError: vi.fn(() => null),
  getConnectionState: vi.fn(() => 'disconnected'),
}))

describe('useWebSocket - Resubscribe Logic', () => {
  let mockEcho: any
  let mockZoneChannel: any
  let mockGlobalChannel: any

  beforeEach(() => {
    // Очищаем все моки перед каждым тестом
    vi.clearAllMocks()
    
    // Устанавливаем window перед созданием моков
    if (!(global as any).window) {
      (global as any).window = {}
    }
    (global as any).window.setInterval = (global.setInterval as any)
    ;(global as any).window.clearInterval = (global.clearInterval as any)
    ;(global as any).window.document = global.document || {
      readyState: 'complete',
      createElement: vi.fn(() => ({})),
      querySelector: vi.fn(() => null),
      querySelectorAll: vi.fn(() => []),
    }
    
    mockZoneChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }

    mockGlobalChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }

    // Создаем новый mockEcho для каждого теста, чтобы каналы создавались заново
    mockEcho = {
      private: vi.fn((channelName: string) => {
        if (channelName === 'events.global') {
          return mockGlobalChannel
        }
        return mockZoneChannel
      }),
      channel: vi.fn(),
      leave: vi.fn(),
      connector: {
        pusher: {
          connection: {
            state: 'connected',
            socket_id: '123.456'
          },
          channels: {
            channels: {}
          }
        }
      }
    }

    // Устанавливаем mockEchoInstance для getEchoInstance
    mockEchoInstance = mockEcho
    mockGetEchoInstance.mockReturnValue(mockEcho)
    mockGetEcho.mockReturnValue(mockEcho)

    // Устанавливаем window.Echo после создания mockEcho
    ;(global as any).window.Echo = mockEcho
  })

  afterEach(() => {
    vi.clearAllMocks()
    // @ts-ignore
    if (global.window) {
      // @ts-ignore
      delete global.window.Echo
    }
  })

  it('should resubscribe to zone commands channels', async () => {
    // Импортируем модуль после установки window.Echo
    const { useWebSocket, resubscribeAllChannels, cleanupWebSocketChannels } = await import('../useWebSocket')
    
    // Очищаем состояние перед тестом
    if (cleanupWebSocketChannels) {
      cleanupWebSocketChannels()
    }
    
    const mockHandler = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    // Создаем подписку
    subscribeToZoneCommands(1, mockHandler)
    
    // Очищаем счетчики вызовов перед resubscribe
    mockEcho.private.mockClear()
    mockZoneChannel.listen.mockClear()
    
    // Вызываем resubscribe
    resubscribeAllChannels()

    // Проверяем, что канал был создан
    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    expect(mockZoneChannel.listen).toHaveBeenCalled()
  })

  it('should resubscribe to global events channel', async () => {
    const { useWebSocket, resubscribeAllChannels, cleanupWebSocketChannels } = await import('../useWebSocket')
    
    // Очищаем состояние перед тестом
    if (cleanupWebSocketChannels) {
      cleanupWebSocketChannels()
    }
    
    const mockHandler = vi.fn()
    const { subscribeToGlobalEvents } = useWebSocket()
    subscribeToGlobalEvents(mockHandler)
    
    // Очищаем счетчики вызовов перед resubscribe
    mockEcho.private.mockClear()
    mockGlobalChannel.listen.mockClear()
    
    resubscribeAllChannels()

    expect(mockEcho.private).toHaveBeenCalledWith('events.global')
    expect(mockGlobalChannel.listen).toHaveBeenCalled()
  })

  it('should handle missing Echo gracefully', async () => {
    const { cleanupWebSocketChannels } = await import('../useWebSocket')
    
    // Очищаем состояние
    if (cleanupWebSocketChannels) {
      cleanupWebSocketChannels()
    }
    
    // Удаляем Echo
    if ((global as any).window) {
      delete (global as any).window.Echo
    }

    const useWebSocketModule = await import('../useWebSocket')
    const { resubscribeAllChannels } = useWebSocketModule

    // Не должно выбросить ошибку
    expect(() => resubscribeAllChannels()).not.toThrow()
    
    // Восстанавливаем Echo для следующих тестов
    if ((global as any).window) {
      (global as any).window.Echo = mockEcho
    }
  })

  it('should resubscribe to multiple zone commands', async () => {
    const { useWebSocket, resubscribeAllChannels, cleanupWebSocketChannels } = await import('../useWebSocket')
    
    // Очищаем состояние перед тестом
    if (cleanupWebSocketChannels) {
      cleanupWebSocketChannels()
    }
    
    const mockHandler1 = vi.fn()
    const mockHandler2 = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    subscribeToZoneCommands(1, mockHandler1)
    subscribeToZoneCommands(2, mockHandler2)
    
    mockEcho.private.mockClear()
    
    resubscribeAllChannels()

    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    expect(mockEcho.private).toHaveBeenCalledWith('commands.2')
  })

  it('should handle errors during resubscription gracefully', async () => {
    const { useWebSocket, resubscribeAllChannels, cleanupWebSocketChannels } = await import('../useWebSocket')
    
    // Очищаем состояние перед тестом
    if (cleanupWebSocketChannels) {
      cleanupWebSocketChannels()
    }
    
    const mockHandler = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    subscribeToZoneCommands(1, mockHandler)
    
    // Мокируем ошибку при resubscribe
    mockEcho.private.mockImplementationOnce(() => {
      throw new Error('Connection error')
    })
    
    // Не должно выбросить ошибку
    expect(() => resubscribeAllChannels()).not.toThrow()
  })

  it('should restore all active subscriptions after reconnect', async () => {
    const { useWebSocket, resubscribeAllChannels, cleanupWebSocketChannels } = await import('../useWebSocket')
    
    // Очищаем состояние перед тестом
    if (cleanupWebSocketChannels) {
      cleanupWebSocketChannels()
    }
    
    const zoneHandler = vi.fn()
    const globalHandler = vi.fn()
    const { subscribeToZoneCommands, subscribeToGlobalEvents } = useWebSocket()
    
    subscribeToZoneCommands(1, zoneHandler)
    subscribeToGlobalEvents(globalHandler)
    
    // Симулируем отключение
    if ((global as any).window) {
      delete (global as any).window.Echo
    }
    
    // Симулируем переподключение
    if ((global as any).window) {
      (global as any).window.Echo = mockEcho
    }
    
    mockEcho.private.mockClear()
    
    resubscribeAllChannels()

    // Проверяем, что все подписки восстановлены
    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    expect(mockEcho.private).toHaveBeenCalledWith('events.global')
  })

  it('should validate subscriptions before resubscribe', async () => {
    const { useWebSocket, resubscribeAllChannels, cleanupWebSocketChannels } = await import('../useWebSocket')
    
    // Очищаем состояние перед тестом
    if (cleanupWebSocketChannels) {
      cleanupWebSocketChannels()
    }
    
    const mockHandler = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    // Создаем подписку
    subscribeToZoneCommands(1, mockHandler)
    
    mockEcho.private.mockClear()
    
    resubscribeAllChannels()
    
    // Валидация должна отфильтровать невалидные подписки
    expect(mockEcho.private).toHaveBeenCalled()
  })

  it('should handle dead channels during resubscribe', async () => {
    const { useWebSocket, resubscribeAllChannels, cleanupWebSocketChannels } = await import('../useWebSocket')
    
    // Очищаем состояние перед тестом
    if (cleanupWebSocketChannels) {
      cleanupWebSocketChannels()
    }
    
    const mockHandler = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    subscribeToZoneCommands(1, mockHandler)
    
    // Симулируем "мертвый" канал - есть в Pusher, но нет обработчиков
    mockEcho.connector.pusher.channels.channels['private-commands.1'] = {
      _events: {},
      _callbacks: {},
      bindings: []
    }
    
    mockEcho.private.mockClear()
    
    resubscribeAllChannels()
    
    // Канал должен быть пересоздан
    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
  })

  it('should sync subscriptions.value after resubscribe', async () => {
    const { useWebSocket, resubscribeAllChannels, cleanupWebSocketChannels } = await import('../useWebSocket')
    
    // Очищаем состояние перед тестом
    if (cleanupWebSocketChannels) {
      cleanupWebSocketChannels()
    }
    
    const mockHandler = vi.fn()
    const { subscribeToZoneCommands, subscriptions } = useWebSocket(undefined, 'TestComponent')
    
    subscribeToZoneCommands(1, mockHandler)
    
    // Проверяем, что подписка есть в subscriptions.value
    expect(subscriptions.value.has('commands.1')).toBe(true)
    
    // Симулируем reconnect и resubscribe
    resubscribeAllChannels()
    
    // После resubscribe подписка должна остаться в subscriptions.value
    expect(subscriptions.value.has('commands.1')).toBe(true)
  })

  it('should handle unmounted components during resubscribe', async () => {
    const { useWebSocket, resubscribeAllChannels, cleanupWebSocketChannels } = await import('../useWebSocket')
    
    // Очищаем состояние перед тестом
    if (cleanupWebSocketChannels) {
      cleanupWebSocketChannels()
    }
    
    const mockHandler = vi.fn()
    const comp1 = useWebSocket(undefined, 'Component1')
    
    comp1.subscribeToZoneCommands(1, mockHandler)
    
    mockEcho.private.mockClear()
    
    // Симулируем размонтирование компонента - вызываем unsubscribeAll
    comp1.unsubscribeAll()
    
    // Но канал должен остаться в channelControls, поэтому resubscribe все равно должен работать
    resubscribeAllChannels()
    
    // Система должна корректно обработать размонтированные компоненты
    // После unsubscribeAll канал может быть удален, но это нормально
    expect(mockEcho.private).toHaveBeenCalled()
  })
})

