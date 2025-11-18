import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useWebSocket } from '../useWebSocket'

describe('useWebSocket', () => {
  let mockEcho: any
  let mockShowToast: vi.Mock

  beforeEach(() => {
    mockShowToast = vi.fn()
    
    // Mock window.Echo
    mockEcho = {
      private: vi.fn(),
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
    const mockChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }
    mockEcho.private.mockReturnValue(mockChannel)

    const { subscribeToZoneCommands } = useWebSocket(mockShowToast)
    const unsubscribe = subscribeToZoneCommands(1, vi.fn())

    expect(typeof unsubscribe).toBe('function')
    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    expect(mockChannel.listen).toHaveBeenCalled()
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
    const mockChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }
    mockEcho.private.mockReturnValue(mockChannel)

    const onCommandUpdate = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    subscribeToZoneCommands(1, onCommandUpdate)

    expect(mockEcho.private).toHaveBeenCalledWith('commands.1')
    expect(mockChannel.listen).toHaveBeenCalledWith('.App\\Events\\CommandStatusUpdated', expect.any(Function))
    expect(mockChannel.listen).toHaveBeenCalledWith('.App\\Events\\CommandFailed', expect.any(Function))
  })

  it('should call onCommandUpdate when command status is updated', () => {
    const mockChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }
    mockEcho.private.mockReturnValue(mockChannel)

    const onCommandUpdate = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket()
    
    subscribeToZoneCommands(1, onCommandUpdate)

    // Get the listener function
    const statusListener = mockChannel.listen.mock.calls.find(
      call => call[0] === '.App\\Events\\CommandStatusUpdated'
    )?.[1]

    expect(statusListener).toBeDefined()

    // Simulate event
    const event = {
      command_id: 123,
      status: 'completed',
      message: 'Command completed',
      zone_id: 1
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
    const mockChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }
    mockEcho.private.mockReturnValue(mockChannel)

    const onCommandUpdate = vi.fn()
    const { subscribeToZoneCommands } = useWebSocket(mockShowToast)
    
    subscribeToZoneCommands(1, onCommandUpdate)

    // Get the failure listener
    const failureListener = mockChannel.listen.mock.calls.find(
      call => call[0] === '.App\\Events\\CommandFailed'
    )?.[1]

    expect(failureListener).toBeDefined()

    // Simulate failure event
    const event = {
      command_id: 123,
      message: 'Command failed',
      error: 'Some error',
      zone_id: 1
    }
    failureListener(event)

    expect(onCommandUpdate).toHaveBeenCalled()
    expect(mockShowToast).toHaveBeenCalledWith('Команда завершилась с ошибкой: Command failed', 'error', 5000)
  })

  it('should unsubscribe from zone commands', () => {
    const mockChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }
    mockEcho.private.mockReturnValue(mockChannel)

    const { subscribeToZoneCommands } = useWebSocket()
    const unsubscribe = subscribeToZoneCommands(1, vi.fn())

    unsubscribe()

    expect(mockChannel.stopListening).toHaveBeenCalledWith('.App\\Events\\CommandStatusUpdated')
    expect(mockChannel.stopListening).toHaveBeenCalledWith('.App\\Events\\CommandFailed')
    expect(mockChannel.leave).toHaveBeenCalled()
  })

  it('should subscribe to global events channel', () => {
    const mockChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }
    mockEcho.channel.mockReturnValue(mockChannel)

    const onEvent = vi.fn()
    const { subscribeToGlobalEvents } = useWebSocket()
    
    subscribeToGlobalEvents(onEvent)

    expect(mockEcho.channel).toHaveBeenCalledWith('events.global')
    expect(mockChannel.listen).toHaveBeenCalledWith('.App\\Events\\EventCreated', expect.any(Function))
  })

  it('should call onEvent when global event occurs', () => {
    const mockChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }
    mockEcho.channel.mockReturnValue(mockChannel)

    const onEvent = vi.fn()
    const { subscribeToGlobalEvents } = useWebSocket()
    
    subscribeToGlobalEvents(onEvent)

    // Get the listener function
    const eventListener = mockChannel.listen.mock.calls[0]?.[1]

    expect(eventListener).toBeDefined()

    // Simulate event
    const event = {
      id: 456,
      kind: 'ALERT',
      message: 'Alert occurred',
      zone_id: 1,
      occurred_at: '2024-01-01T00:00:00Z'
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
    const mockChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }
    mockEcho.channel.mockReturnValue(mockChannel)

    const { subscribeToGlobalEvents } = useWebSocket()
    const unsubscribe = subscribeToGlobalEvents(vi.fn())

    unsubscribe()

    expect(mockChannel.stopListening).toHaveBeenCalledWith('.App\\Events\\EventCreated')
    expect(mockChannel.leave).toHaveBeenCalled()
  })

  it('should handle unsubscribeAll', () => {
    const mockChannel1 = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }
    const mockChannel2 = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }
    mockEcho.private.mockReturnValue(mockChannel1)
    mockEcho.channel.mockReturnValue(mockChannel2)

    const { subscribeToZoneCommands, subscribeToGlobalEvents, unsubscribeAll } = useWebSocket()
    
    subscribeToZoneCommands(1, vi.fn())
    subscribeToGlobalEvents(vi.fn())
    
    unsubscribeAll()

    expect(mockChannel1.leave).toHaveBeenCalled()
    expect(mockChannel2.leave).toHaveBeenCalled()
  })
})

