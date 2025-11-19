import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('useWebSocket - Resubscribe (P1-2)', () => {
  let mockEcho: any
  let mockChannel: any
  let mockPrivateChannel: any

  beforeEach(() => {
    mockChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }

    mockPrivateChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }

    mockEcho = {
      private: vi.fn(() => mockPrivateChannel),
      channel: vi.fn(() => mockChannel)
    }

    // @ts-ignore
    global.window = {
      Echo: mockEcho
    }

    // Импортируем и очищаем activeSubscriptions
    vi.resetModules()
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
    expect(mockPrivateChannel.listen).toHaveBeenCalled()
  })

  it('should resubscribe to global events channel', async () => {
    const { useWebSocket, resubscribeAllChannels } = await import('../useWebSocket')
    
    const mockHandler = vi.fn()
    const { subscribeToGlobalEvents } = useWebSocket()
    subscribeToGlobalEvents(mockHandler)
    
    resubscribeAllChannels()

    expect(mockEcho.channel).toHaveBeenCalledWith('events.global')
    expect(mockChannel.listen).toHaveBeenCalled()
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
    expect(mockEcho.channel).toHaveBeenCalledWith('events.global')
  })
})

