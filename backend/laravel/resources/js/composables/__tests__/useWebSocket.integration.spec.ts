import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

type UseWebSocketModule = typeof import('../useWebSocket')
let useWebSocketModule: UseWebSocketModule

// Mock logger
vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    isDev: true,
    isProd: false
  }
}))

// Mock echoClient
const mockStateListeners = new Set<Function>()
const mockOnWsStateChange = vi.fn((listener: Function) => {
  mockStateListeners.add(listener)
  return () => mockStateListeners.delete(listener)
})

vi.mock('@/utils/echoClient', () => ({
  onWsStateChange: mockOnWsStateChange,
  getEcho: vi.fn(() => null),
  getReconnectAttempts: vi.fn(() => 0),
  getLastError: vi.fn(() => null),
  getConnectionState: vi.fn(() => ({ state: 'connected', socketId: '123.456' })),
}))

describe('useWebSocket - Integration Tests', () => {
  let mockEcho: any
  let mockZoneChannel: any
  let mockGlobalChannel: any
  let mockConnection: any

  const originalWindow = global.window ?? (global.window = {} as any)
  let previousEcho: any

  beforeEach(async () => {
    vi.clearAllMocks()
    mockStateListeners.clear()

    mockZoneChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn(),
      _events: {},
      _callbacks: {},
      bindings: []
    }

    mockGlobalChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn(),
      _events: {},
      _callbacks: {},
      bindings: []
    }

    mockConnection = {
      state: 'connected',
      socket_id: '123.456',
      bind: vi.fn(),
      unbind: vi.fn(),
      connect: vi.fn(),
      disconnect: vi.fn(),
    }

    const pusherChannels: Record<string, any> = {}

    mockEcho = {
      private: vi.fn((channelName: string) => {
        if (channelName === 'events.global') {
          pusherChannels[channelName] = mockGlobalChannel
          return mockGlobalChannel
        }
        pusherChannels[channelName] = mockZoneChannel
        return mockZoneChannel
      }),
      channel: vi.fn(() => mockZoneChannel),
      leave: vi.fn(),
      connector: {
        pusher: {
          connection: mockConnection,
          channels: {
            channels: pusherChannels
          }
        }
      }
    }

    previousEcho = originalWindow.Echo
    originalWindow.Echo = mockEcho

    vi.resetModules()
    useWebSocketModule = await import('../useWebSocket')
  })

  afterEach(() => {
    vi.clearAllMocks()
    mockStateListeners.clear()

    if (previousEcho === undefined) {
      delete originalWindow.Echo
    } else {
      originalWindow.Echo = previousEcho
    }

    // Reset module state if possible
    if (useWebSocketModule && typeof (useWebSocketModule as any).__reset === 'function') {
      (useWebSocketModule as any).__reset()
    }
  })

  describe('Real-world scenarios', () => {
    it('should handle complete command lifecycle', () => {
      const { useWebSocket } = useWebSocketModule
      const { subscribeToZoneCommands } = useWebSocket()

      const commandUpdates: any[] = []
      const handler = (event: any) => {
        commandUpdates.push(event)
      }

      // Subscribe
      const unsubscribe = subscribeToZoneCommands(1, handler)

      // Simulate command progression
      const statusListener = mockZoneChannel.listen.mock.calls.find(
        (call: any[]) => call[0] === '.App\\Events\\CommandStatusUpdated'
      )?.[1]

      if (statusListener) {
        // Command started
        statusListener({ commandId: 100, status: 'running', zoneId: 1 })
        
        // Command in progress
        statusListener({ commandId: 100, status: 'running', message: 'Processing...', zoneId: 1 })
        
        // Command completed
        statusListener({ commandId: 100, status: 'completed', message: 'Done', zoneId: 1 })
      }

      expect(commandUpdates).toHaveLength(3)
      expect(commandUpdates[0].status).toBe('running')
      expect(commandUpdates[2].status).toBe('completed')

      unsubscribe()
    })

    it('should handle multiple zones simultaneously', () => {
      const { useWebSocket } = useWebSocketModule
      const { subscribeToZoneCommands } = useWebSocket()

      const zone1Updates: any[] = []
      const zone2Updates: any[] = []

      const handler1 = (event: any) => zone1Updates.push(event)
      const handler2 = (event: any) => zone2Updates.push(event)

      // Subscribe to two zones
      const unsubscribe1 = subscribeToZoneCommands(1, handler1)
      const unsubscribe2 = subscribeToZoneCommands(2, handler2)

      // Get listeners for both channels
      const channel1 = mockEcho.private.mock.calls.find((call: any[]) => call[0] === 'commands.1')?.[0]
      const channel2 = mockEcho.private.mock.calls.find((call: any[]) => call[0] === 'commands.2')?.[0]

      // Simulate events for zone 1
      const statusListener1 = mockZoneChannel.listen.mock.calls.find(
        (call: any[]) => call[0] === '.App\\Events\\CommandStatusUpdated'
      )?.[1]

      if (statusListener1) {
        statusListener1({ commandId: 100, status: 'completed', zoneId: 1 })
      }

      // Both zones should be subscribed
      expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
      expect(mockEcho.private).toHaveBeenCalledWith('commands.2')

      unsubscribe1()
      unsubscribe2()
    })

    it('should handle reconnection and resubscription', () => {
      const { useWebSocket, resubscribeAllChannels } = useWebSocketModule
      const { subscribeToZoneCommands, subscribeToGlobalEvents } = useWebSocket()

      const zoneHandler = vi.fn()
      const globalHandler = vi.fn()

      // Subscribe to channels
      subscribeToZoneCommands(1, zoneHandler)
      subscribeToGlobalEvents(globalHandler)

      // Clear mock calls
      mockEcho.private.mockClear()
      mockZoneChannel.listen.mockClear()
      mockGlobalChannel.listen.mockClear()

      // Simulate reconnection - resubscribe all
      resubscribeAllChannels()

      // Should recreate channels
      expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
      expect(mockEcho.private).toHaveBeenCalledWith('events.global')

      // Should reattach listeners
      expect(mockZoneChannel.listen).toHaveBeenCalled()
      expect(mockGlobalChannel.listen).toHaveBeenCalled()
    })

    it('should handle component unmount and cleanup', () => {
      const { useWebSocket } = useWebSocketModule
      const ws1 = useWebSocket(undefined, 'Component1')
      const ws2 = useWebSocket(undefined, 'Component2')

      const handler1 = vi.fn()
      const handler2 = vi.fn()

      // Both components subscribe to same channel
      const unsubscribe1 = ws1.subscribeToZoneCommands(1, handler1)
      const unsubscribe2 = ws2.subscribeToZoneCommands(1, handler2)

      // First component unmounts
      unsubscribe1()

      // Second component should still be subscribed
      expect(mockEcho.leave).not.toHaveBeenCalledWith('commands.1')

      // Second component unmounts
      unsubscribe2()

      // Now channel should be left
      expect(mockEcho.leave).toHaveBeenCalledWith('commands.1')
    })

    it('should handle errors in event handlers gracefully', () => {
      const { useWebSocket } = useWebSocketModule
      const { subscribeToZoneCommands } = useWebSocket()

      const handler = vi.fn(() => {
        throw new Error('Handler error')
      })

      subscribeToZoneCommands(1, handler)

      // Simulate event that would cause error
      const statusListener = mockZoneChannel.listen.mock.calls.find(
        (call: any[]) => call[0] === '.App\\Events\\CommandStatusUpdated'
      )?.[1]

      if (statusListener) {
        // Should not throw, error should be caught
        expect(() => {
          statusListener({ commandId: 100, status: 'completed', zoneId: 1 })
        }).not.toThrow()
      }
    })

    it('should handle connection state changes', () => {
      const { useWebSocket } = useWebSocketModule
      const { subscribeToZoneCommands } = useWebSocket()

      const handler = vi.fn()
      subscribeToZoneCommands(1, handler)

      // Simulate connection state change
      mockStateListeners.forEach(listener => {
        listener('disconnected')
      })

      // Subscription should still be valid (will resubscribe on reconnect)
      expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    })

    it('should handle rapid subscribe/unsubscribe cycles', () => {
      const { useWebSocket } = useWebSocketModule
      const { subscribeToZoneCommands } = useWebSocket()

      // Rapid subscribe/unsubscribe
      for (let i = 0; i < 10; i++) {
        const unsubscribe = subscribeToZoneCommands(1, vi.fn())
        unsubscribe()
      }

      // Should not cause errors or memory leaks
      expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    })

    it('should handle missing Echo gracefully', () => {
      delete originalWindow.Echo

      const { useWebSocket } = useWebSocketModule
      const { subscribeToZoneCommands } = useWebSocket()

      const handler = vi.fn()
      const unsubscribe = subscribeToZoneCommands(1, handler)

      // Should return unsubscribe function even without Echo
      expect(typeof unsubscribe).toBe('function')
      
      // Should not throw on unsubscribe
      expect(() => unsubscribe()).not.toThrow()
    })
  })
})

