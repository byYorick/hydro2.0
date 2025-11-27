import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useWebSocket } from '../useWebSocket'

describe('useWebSocket', () => {
  let mockEcho: any
  let mockShowToast: vi.Mock
  let mockZoneChannel: any
  let mockGlobalChannel: any

  beforeEach(() => {
    mockShowToast = vi.fn()
    
    // Mock window.Echo
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
      channel: vi.fn()
    }
    
    // @ts-ignore
    global.window = {
      Echo: mockEcho
    }
  })

  afterEach(() => {
    vi.clearAllMocks()
    // @ts-ignore
    delete global.window.Echo
  })

  it('should return unsubscribe function when Echo is available', () => {
    const { subscribeToZoneCommands } = useWebSocket(mockShowToast)
    const unsubscribe = subscribeToZoneCommands(1, vi.fn())

    expect(typeof unsubscribe).toBe('function')
    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    expect(mockZoneChannel.listen).toHaveBeenCalled()
  })

  it('should handle missing Echo gracefully', () => {
    // @ts-ignore
    delete global.window.Echo

    const { subscribeToZoneCommands } = useWebSocket(mockShowToast)
    const unsubscribe = subscribeToZoneCommands(1, vi.fn())

    expect(typeof unsubscribe).toBe('function')
    expect(mockShowToast).toHaveBeenCalledWith('WebSocket не доступен', 'warning', 3000)
  })

  it('should subscribe to zone commands channel', () => {
    const onCommandUpdate = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    subscribeToZoneCommands(1, onCommandUpdate)

    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    expect(mockZoneChannel.listen).toHaveBeenCalledWith('.App\\Events\\CommandStatusUpdated', expect.any(Function))
    expect(mockZoneChannel.listen).toHaveBeenCalledWith('.App\\Events\\CommandFailed', expect.any(Function))
  })

  it('should call onCommandUpdate when command status is updated', () => {
    const onCommandUpdate = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    subscribeToZoneCommands(1, onCommandUpdate)

    // Get the listener function
    const statusListener = mockZoneChannel.listen.mock.calls.find(
      call => call[0] === '.App\\Events\\CommandStatusUpdated'
    )?.[1]

    expect(statusListener).toBeDefined()

    // Simulate event (события приходят уже с camelCase полями)
    const event = {
      commandId: 123,
      status: 'completed',
      message: 'Command completed',
      zoneId: 1
    }
    statusListener(event)

    expect(onCommandUpdate).toHaveBeenCalledWith({
      commandId: 123,
      status: 'completed',
      message: 'Command completed',
      error: undefined,
      zoneId: 1
    })
  })

  it('should show toast on command failure', () => {
    const onCommandUpdate = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket(mockShowToast)
    
    subscribeToZoneCommands(1, onCommandUpdate)

    // Get the failure listener
    const failureListener = mockZoneChannel.listen.mock.calls.find(
      call => call[0] === '.App\\Events\\CommandFailed'
    )?.[1]

    expect(failureListener).toBeDefined()

    // Simulate failure event (события приходят уже с camelCase полями)
    const event = {
      commandId: 123,
      message: 'Command failed',
      error: 'Some error',
      zoneId: 1
    }
    failureListener(event)

    expect(onCommandUpdate).toHaveBeenCalled()
    expect(mockShowToast).toHaveBeenCalledWith('Команда завершилась с ошибкой: Command failed', 'error', 5000)
  })

  it('should unsubscribe from zone commands', () => {
    const { subscribeToZoneCommands } = useWebSocket()
    const unsubscribe = subscribeToZoneCommands(1, vi.fn())

    unsubscribe()

    expect(mockZoneChannel.stopListening).toHaveBeenCalledWith('.App\\Events\\CommandStatusUpdated')
    expect(mockZoneChannel.stopListening).toHaveBeenCalledWith('.App\\Events\\CommandFailed')
    expect(mockZoneChannel.leave).toHaveBeenCalled()
  })

  it('should subscribe to global events channel', () => {
    const onEvent = vi.fn()
    const { subscribeToGlobalEvents } = useWebSocket()
    
    subscribeToGlobalEvents(onEvent)

    expect(mockEcho.private).toHaveBeenCalledWith('events.global')
    expect(mockGlobalChannel.listen).toHaveBeenCalledWith('.App\\Events\\EventCreated', expect.any(Function))
  })

  it('should call onEvent when global event occurs', () => {
    const onEvent = vi.fn()
    const { subscribeToGlobalEvents } = useWebSocket()
    
    subscribeToGlobalEvents(onEvent)

    // Get the listener function
    const eventListener = mockGlobalChannel.listen.mock.calls[0]?.[1]

    expect(eventListener).toBeDefined()

    // Simulate event (события приходят уже с camelCase полями)
    const event = {
      id: 456,
      kind: 'ALERT',
      message: 'Alert occurred',
      zoneId: 1,
      occurredAt: '2024-01-01T00:00:00Z'
    }
    eventListener(event)

    expect(onEvent).toHaveBeenCalledWith({
      id: 456,
      kind: 'ALERT',
      message: 'Alert occurred',
      zoneId: 1,
      occurredAt: '2024-01-01T00:00:00Z'
    })
  })

  it('should unsubscribe from global events', () => {
    const { subscribeToGlobalEvents } = useWebSocket()
    const unsubscribe = subscribeToGlobalEvents(vi.fn())

    unsubscribe()

    expect(mockGlobalChannel.stopListening).toHaveBeenCalledWith('.App\\Events\\EventCreated')
    expect(mockGlobalChannel.leave).toHaveBeenCalled()
  })

  it('should handle unsubscribeAll', () => {
    const { subscribeToZoneCommands, subscribeToGlobalEvents, unsubscribeAll } = useWebSocket()
    
    subscribeToZoneCommands(1, vi.fn())
    subscribeToGlobalEvents(vi.fn())
    
    unsubscribeAll()

    expect(mockZoneChannel.leave).toHaveBeenCalled()
    expect(mockGlobalChannel.leave).toHaveBeenCalled()
  })
})

