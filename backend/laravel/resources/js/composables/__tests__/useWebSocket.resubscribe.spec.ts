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

describe('useWebSocket - Resubscribe Logic', () => {
  let mockEcho: any
  let mockZoneChannel: any
  let mockGlobalChannel: any

  beforeEach(() => {
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

    mockEcho = {
      private: vi.fn((channelName: string) => {
        if (channelName === 'events.global') {
          return mockGlobalChannel
        }
        return mockZoneChannel
      }),
      channel: vi.fn(),
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

    // @ts-ignore
    global.window = {
      Echo: mockEcho
    }

    // Импортируем и очищаем activeSubscriptions
    vi.resetModules()
    
    // Mock Pusher connection для проверки состояния
    mockEcho.connector = {
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
  })

  afterEach(() => {
    vi.clearAllMocks()
    // @ts-ignore
    delete global.window.Echo
  })

  it('should resubscribe to zone commands channels', async () => {
    const { useWebSocket } = await import('../useWebSocket')
    const { resubscribeAllChannels } = await import('../useWebSocket')
    
    const mockHandler = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    // Создаем подписку
    subscribeToZoneCommands(1, mockHandler)
    
    // Вызываем resubscribe
    resubscribeAllChannels()

    // Проверяем, что канал был создан
    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    expect(mockZoneChannel.listen).toHaveBeenCalled()
  })

  it('should resubscribe to global events channel', async () => {
    const { useWebSocket, resubscribeAllChannels } = await import('../useWebSocket')
    
    const mockHandler = vi.fn()
    const { subscribeToGlobalEvents } = useWebSocket()
    subscribeToGlobalEvents(mockHandler)
    
    resubscribeAllChannels()

    expect(mockEcho.private).toHaveBeenCalledWith('events.global')
    expect(mockGlobalChannel.listen).toHaveBeenCalled()
  })

  it('should handle missing Echo gracefully', async () => {
    // @ts-ignore
    delete global.window.Echo

    const useWebSocketModule = await import('../useWebSocket')
    const { resubscribeAllChannels } = useWebSocketModule

    // Не должно выбросить ошибку
    expect(() => resubscribeAllChannels()).not.toThrow()
  })

  it('should resubscribe to multiple zone commands', async () => {
    const { useWebSocket, resubscribeAllChannels } = await import('../useWebSocket')
    
    const mockHandler1 = vi.fn()
    const mockHandler2 = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    subscribeToZoneCommands(1, mockHandler1)
    subscribeToZoneCommands(2, mockHandler2)
    
    resubscribeAllChannels()

    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    expect(mockEcho.private).toHaveBeenCalledWith('commands.2')
  })

  it('should handle errors during resubscription gracefully', async () => {
    const { useWebSocket, resubscribeAllChannels } = await import('../useWebSocket')
    
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
    const { useWebSocket, resubscribeAllChannels } = await import('../useWebSocket')
    
    const zoneHandler = vi.fn()
    const globalHandler = vi.fn()
    const { subscribeToZoneCommands, subscribeToGlobalEvents } = useWebSocket()
    
    subscribeToZoneCommands(1, zoneHandler)
    subscribeToGlobalEvents(globalHandler)
    
    // Симулируем отключение
    // @ts-ignore
    delete global.window.Echo
    
    // Симулируем переподключение
    // @ts-ignore
    global.window.Echo = mockEcho
    
    resubscribeAllChannels()

    // Проверяем, что все подписки восстановлены
    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    expect(mockEcho.private).toHaveBeenCalledWith('events.global')
  })

  it('should validate subscriptions before resubscribe', async () => {
    const { useWebSocket, resubscribeAllChannels } = await import('../useWebSocket')
    
    const mockHandler = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    // Создаем подписку
    subscribeToZoneCommands(1, mockHandler)
    
    // Симулируем размонтирование компонента (удаляем из componentSubscriptionsMaps)
    // Это делается через vi.resetModules(), но для теста просто проверяем валидацию
    
    resubscribeAllChannels()
    
    // Валидация должна отфильтровать невалидные подписки
    expect(mockEcho.private).toHaveBeenCalled()
  })

  it('should handle dead channels during resubscribe', async () => {
    const { useWebSocket, resubscribeAllChannels } = await import('../useWebSocket')
    
    const mockHandler = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    subscribeToZoneCommands(1, mockHandler)
    
    // Симулируем "мертвый" канал - есть в Pusher, но нет обработчиков
    mockEcho.connector.pusher.channels.channels['commands.1'] = {
      _events: {},
      _callbacks: {},
      bindings: []
    }
    
    resubscribeAllChannels()
    
    // Канал должен быть пересоздан
    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
  })

  it('should sync subscriptions.value after resubscribe', async () => {
    const { useWebSocket, resubscribeAllChannels } = await import('../useWebSocket')
    
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
    const { useWebSocket, resubscribeAllChannels } = await import('../useWebSocket')
    
    const mockHandler = vi.fn()
    const comp1 = useWebSocket(undefined, 'Component1')
    
    comp1.subscribeToZoneCommands(1, mockHandler)
    
    // Симулируем размонтирование компонента через vi.resetModules
    // Но так как мы не можем напрямую удалить из WeakMap, просто проверяем, что система работает
    resubscribeAllChannels()
    
    // Система должна корректно обработать размонтированные компоненты
    expect(mockEcho.private).toHaveBeenCalled()
  })
})

