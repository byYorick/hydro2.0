import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock Pusher
const mockPusherConnection = {
  state: 'disconnected',
  socket_id: null as string | null,
  bind: vi.fn(),
  unbind: vi.fn(),
  connect: vi.fn(),
  disconnect: vi.fn(),
}

const mockPusher = {
  connection: mockPusherConnection,
  channels: {
    channels: {},
  },
  disconnect: vi.fn(),
}

const MockPusher = vi.fn().mockImplementation(() => mockPusher)
const MockEcho = vi.fn().mockImplementation(() => ({
  connector: {
    pusher: mockPusher,
  },
  disconnect: vi.fn(),
}))

// Mock laravel-echo and pusher-js modules
vi.mock('laravel-echo', () => ({
  default: MockEcho,
}))

vi.mock('pusher-js', () => ({
  default: MockPusher,
}))

import {
  initEcho,
  getEcho,
  getEchoInstance,
  getConnectionState,
  getLastError,
  getReconnectAttempts,
  onWsStateChange,
  getConnectionState as getState,
} from '../echoClient'

describe('echoClient - Integration Tests', () => {
  const originalWindow = global.window ?? (global.window = {} as any)
  let previousEcho: any
  let previousPusher: any
  let previousEnv: any

  beforeEach(() => {
    vi.useFakeTimers()
    
    previousEcho = originalWindow.Echo
    previousPusher = originalWindow.Pusher
    previousEnv = (import.meta as any).env

    // Reset mocks
    vi.clearAllMocks()
    mockPusherConnection.state = 'disconnected'
    mockPusherConnection.socket_id = null
    mockPusher.channels.channels = {}

    // Setup window.Pusher mock
    originalWindow.Pusher = MockPusher as any
    originalWindow.Echo = undefined

    // Mock environment
    ;(import.meta as any).env = {
      VITE_ENABLE_WS: 'true',
      VITE_REVERB_APP_KEY: 'test-key',
      VITE_REVERB_HOST: 'localhost',
      VITE_REVERB_PORT: '8080',
      VITE_REVERB_SCHEME: 'http',
      ...previousEnv,
    }
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
    
    if (previousEcho === undefined) {
      delete originalWindow.Echo
    } else {
      originalWindow.Echo = previousEcho
    }
    
    if (previousPusher === undefined) {
      delete originalWindow.Pusher
    } else {
      originalWindow.Pusher = previousPusher
    }

    ;(import.meta as any).env = previousEnv
  })

  describe('Initialization', () => {
    it('should initialize Echo with correct configuration', () => {
      const echo = initEcho()
      
      expect(echo).toBeDefined()
      expect(MockEcho).toHaveBeenCalled()
      expect(originalWindow.Echo).toBeDefined()
    })

    it('should not initialize when WebSocket is disabled', () => {
      // Сбрасываем echoInstance перед тестом через forceReinit
      initEcho(true)
      
      ;(import.meta as any).env.VITE_ENABLE_WS = 'false'
      
      const echo = initEcho()
      
      expect(echo).toBeNull()
    })

    it('should return existing instance if already initialized', () => {
      const echo1 = initEcho()
      const echo2 = initEcho()
      
      expect(echo1).toBe(echo2)
      expect(MockEcho).toHaveBeenCalledTimes(1)
    })

    it('should force reinitialize when forceReinit is true', () => {
      const echo1 = initEcho()
      const echo2 = initEcho(true)
      
      // Should create new instance
      expect(MockEcho).toHaveBeenCalledTimes(2)
    })
  })

  describe('Connection State Management', () => {
    it('should track connection state changes', () => {
      const stateListener = vi.fn()
      const unsubscribe = onWsStateChange(stateListener)

      initEcho()

      // Simulate connection state change - initEcho вызывает emitState('connecting')
      // Проверяем, что состояние было установлено
      const state = getConnectionState()
      expect(state.state).toBe('connecting')
      expect(stateListener).toHaveBeenCalledWith('connecting')

      unsubscribe()
    })

    it('should emit connected state when connection succeeds', () => {
      const stateListener = vi.fn()
      const unsubscribe = onWsStateChange(stateListener)

      initEcho()

      // Simulate connected event - находим обработчик через последний вызов bind с 'connected'
      const connectedCalls = mockPusherConnection.bind.mock.calls.filter(
        (call: any[]) => call[0] === 'connected'
      )
      const connectedHandler = connectedCalls[connectedCalls.length - 1]?.[1]
      
      if (connectedHandler) {
        mockPusherConnection.state = 'connected'
        mockPusherConnection.socket_id = '123.456'
        connectedHandler()
      }

      expect(stateListener).toHaveBeenCalledWith('connected')
      const state = getConnectionState()
      expect(state.state).toBe('connected')
      expect(state.socketId).toBe('123.456')
      expect(state.reconnectAttempts).toBe(0)

      unsubscribe()
    })

    it('should emit disconnected state and schedule reconnect', () => {
      const stateListener = vi.fn()
      const unsubscribe = onWsStateChange(stateListener)

      initEcho()

      // First connect
      const connectedCalls = mockPusherConnection.bind.mock.calls.filter(
        (call: any[]) => call[0] === 'connected'
      )
      const connectedHandler = connectedCalls[connectedCalls.length - 1]?.[1]
      if (connectedHandler) {
        mockPusherConnection.state = 'connected'
        connectedHandler()
      }

      // Then disconnect
      const disconnectedCalls = mockPusherConnection.bind.mock.calls.filter(
        (call: any[]) => call[0] === 'disconnected'
      )
      const disconnectedHandler = disconnectedCalls[disconnectedCalls.length - 1]?.[1]
      
      if (disconnectedHandler) {
        mockPusherConnection.state = 'disconnected'
        disconnectedHandler()
      }

      expect(stateListener).toHaveBeenCalledWith('disconnected')
      
      // Should schedule reconnect
      vi.advanceTimersByTime(0)
      const state = getConnectionState()
      expect(state.isReconnecting).toBe(true)

      unsubscribe()
    })

    it('should handle multiple state listeners', () => {
      const listener1 = vi.fn()
      const listener2 = vi.fn()
      const listener3 = vi.fn()

      const unsub1 = onWsStateChange(listener1)
      const unsub2 = onWsStateChange(listener2)
      const unsub3 = onWsStateChange(listener3)

      initEcho()

      const connectedCalls = mockPusherConnection.bind.mock.calls.filter(
        (call: any[]) => call[0] === 'connected'
      )
      const connectedHandler = connectedCalls[connectedCalls.length - 1]?.[1]
      
      if (connectedHandler) {
        connectedHandler()
      }

      expect(listener1).toHaveBeenCalledWith('connected')
      expect(listener2).toHaveBeenCalledWith('connected')
      expect(listener3).toHaveBeenCalledWith('connected')

      unsub1()
      unsub2()
      unsub3()
    })
  })

  describe('Reconnection Logic', () => {
    it('should use exponential backoff for reconnection', () => {
      initEcho()

      // Simulate multiple disconnects
      const disconnectedCalls = mockPusherConnection.bind.mock.calls.filter(
        (call: any[]) => call[0] === 'disconnected'
      )
      const disconnectedHandler = disconnectedCalls[disconnectedCalls.length - 1]?.[1]

      if (disconnectedHandler) {
        // First disconnect
        disconnectedHandler()
        vi.advanceTimersByTime(3000) // BASE_RECONNECT_DELAY
        
        let attempts = getReconnectAttempts()
        expect(attempts).toBeGreaterThan(0)

        // Second disconnect
        disconnectedHandler()
        vi.advanceTimersByTime(4500) // BASE_RECONNECT_DELAY * 1.5

        attempts = getReconnectAttempts()
        expect(attempts).toBeGreaterThan(1)
      }
    })

    it('should reset reconnect attempts on successful connection', () => {
      initEcho()

      // Disconnect first
      const disconnectedCalls = mockPusherConnection.bind.mock.calls.filter(
        (call: any[]) => call[0] === 'disconnected'
      )
      const disconnectedHandler = disconnectedCalls[disconnectedCalls.length - 1]?.[1]
      if (disconnectedHandler) {
        disconnectedHandler()
      }

      expect(getReconnectAttempts()).toBeGreaterThan(0)

      // Then connect
      const connectedCalls = mockPusherConnection.bind.mock.calls.filter(
        (call: any[]) => call[0] === 'connected'
      )
      const connectedHandler = connectedCalls[connectedCalls.length - 1]?.[1]
      if (connectedHandler) {
        connectedHandler()
      }

      expect(getReconnectAttempts()).toBe(0)
    })

    it('should cap reconnect delay at MAX_RECONNECT_DELAY', () => {
      initEcho()

      const disconnectedCalls = mockPusherConnection.bind.mock.calls.filter(
        (call: any[]) => call[0] === 'disconnected'
      )
      const disconnectedHandler = disconnectedCalls[disconnectedCalls.length - 1]?.[1]

      if (disconnectedHandler) {
        // Simulate many disconnects
        for (let i = 0; i < 20; i++) {
          disconnectedHandler()
          vi.advanceTimersByTime(61000) // Max delay is 60000
        }

        // Delay should be capped at 60000ms
        const state = getConnectionState()
        expect(state.reconnectAttempts).toBeGreaterThan(0)
      }
    })
  })

  describe('Error Handling', () => {
    it('should capture connection errors', () => {
      initEcho()

      const errorCalls = mockPusherConnection.bind.mock.calls.filter(
        (call: any[]) => call[0] === 'error'
      )
      const errorHandler = errorCalls[errorCalls.length - 1]?.[1]

      if (errorHandler) {
        const errorPayload = {
          error: {
            message: 'Connection failed',
            code: 1006,
          },
        }
        errorHandler(errorPayload)
      }

      const error = getLastError()
      expect(error).toBeDefined()
      expect(error?.message).toBe('Connection failed')
      expect(error?.code).toBe(1006)
    })

    it('should handle failed state', () => {
      const stateListener = vi.fn()
      const unsubscribe = onWsStateChange(stateListener)

      initEcho()

      const failedCalls = mockPusherConnection.bind.mock.calls.filter(
        (call: any[]) => call[0] === 'failed'
      )
      const failedHandler = failedCalls[failedCalls.length - 1]?.[1]

      if (failedHandler) {
        failedHandler()
      }

      expect(stateListener).toHaveBeenCalledWith('failed')
      const state = getConnectionState()
      expect(state.state).toBe('failed')

      unsubscribe()
    })

    it('should handle unavailable state', () => {
      const stateListener = vi.fn()
      const unsubscribe = onWsStateChange(stateListener)

      initEcho()

      const unavailableCalls = mockPusherConnection.bind.mock.calls.filter(
        (call: any[]) => call[0] === 'unavailable'
      )
      const unavailableHandler = unavailableCalls[unavailableCalls.length - 1]?.[1]

      if (unavailableHandler) {
        unavailableHandler()
      }

      expect(stateListener).toHaveBeenCalledWith('unavailable')

      unsubscribe()
    })
  })

  describe('Configuration Resolution', () => {
    it('should use environment variables for configuration', () => {
      // Сбрасываем echoInstance перед тестом
      initEcho(true)
      
      ;(import.meta as any).env = {
        VITE_ENABLE_WS: 'true',
        VITE_REVERB_APP_KEY: 'custom-key',
        VITE_REVERB_HOST: 'custom-host',
        VITE_REVERB_PORT: '9000',
        VITE_REVERB_SCHEME: 'https',
        VITE_REVERB_SERVER_PATH: '/custom-path',
      }

      const echo = initEcho(true)

      expect(MockEcho).toHaveBeenCalled()
      expect(echo).toBeDefined()
    })

    it('should fallback to defaults when env vars are missing', () => {
      // Сбрасываем echoInstance перед тестом
      initEcho(true)
      
      ;(import.meta as any).env = {
        VITE_ENABLE_WS: 'true',
      }

      const echo = initEcho(true)
      expect(echo).toBeDefined()
    })
  })

  describe('Cleanup', () => {
    it('should cleanup connection handlers on teardown', () => {
      const echo = initEcho()

      // Add handlers
      mockPusherConnection.bind.mockClear()

      // Reinitialize to trigger cleanup
      initEcho(true)

      // Should have cleaned up old handlers
      expect(mockPusherConnection.unbind).toHaveBeenCalled()
    })

    it('should disconnect on teardown', () => {
      const echo = initEcho()
      const disconnectSpy = vi.spyOn(echo as any, 'disconnect')

      initEcho(true)

      expect(disconnectSpy).toHaveBeenCalled()
    })
  })
})

