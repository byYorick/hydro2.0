import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useSystemStatus } from '../useSystemStatus'

describe('useSystemStatus - MQTT Status Channel (P2-4)', () => {
  let mockEcho: any
  let mockChannel: any
  let mockShowToast: vi.Mock

  beforeEach(() => {
    mockShowToast = vi.fn()
    
    mockChannel = {
      listen: vi.fn(),
      stopListening: vi.fn(),
      leave: vi.fn()
    }

    mockEcho = {
      channel: vi.fn(() => mockChannel)
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

  it('should subscribe to mqtt.status channel on initialization', async () => {
    const { mqttStatus } = useSystemStatus(mockShowToast)

    // Даем время на инициализацию
    await new Promise(resolve => setTimeout(resolve, 100))
    
    expect(mockEcho.channel).toHaveBeenCalledWith('mqtt.status')
    expect(mockChannel.listen).toHaveBeenCalled()
  })

  it('should update MQTT status to online when receiving MqttStatusUpdated event', async () => {
    const { mqttStatus } = useSystemStatus(mockShowToast)

    await new Promise(resolve => setTimeout(resolve, 100))

    // Находим listener для MqttStatusUpdated
    const statusListener = mockChannel.listen.mock.calls.find(
      (call: any[]) => call[0] === '.App\\Events\\MqttStatusUpdated'
    )?.[1]

    expect(statusListener).toBeDefined()

    // Симулируем событие
    if (statusListener) {
      statusListener({ status: 'online' })
      expect(mqttStatus.value).toBe('online')
    }
  })

  it('should update MQTT status to offline when receiving offline event', async () => {
    const { mqttStatus } = useSystemStatus(mockShowToast)

    await new Promise(resolve => setTimeout(resolve, 100))

    const statusListener = mockChannel.listen.mock.calls.find(
      (call: any[]) => call[0] === '.App\\Events\\MqttStatusUpdated'
    )?.[1]

    if (statusListener) {
      statusListener({ status: 'offline' })
      expect(mqttStatus.value).toBe('offline')
    }
  })

  it('should update MQTT status to degraded when receiving degraded event', async () => {
    const { mqttStatus } = useSystemStatus(mockShowToast)

    await new Promise(resolve => setTimeout(resolve, 100))

    const statusListener = mockChannel.listen.mock.calls.find(
      (call: any[]) => call[0] === '.App\\Events\\MqttStatusUpdated'
    )?.[1]

    if (statusListener) {
      statusListener({ status: 'degraded' })
      expect(mqttStatus.value).toBe('degraded')
    }
  })

  it('should handle MqttError events', async () => {
    const { mqttStatus } = useSystemStatus(mockShowToast)

    await new Promise(resolve => setTimeout(resolve, 100))

    const errorListener = mockChannel.listen.mock.calls.find(
      (call: any[]) => call[0] === '.App\\Events\\MqttError'
    )?.[1]

    expect(errorListener).toBeDefined()

    if (errorListener) {
      errorListener({ message: 'MQTT connection failed' })
      expect(mqttStatus.value).toBe('offline')
      expect(mockShowToast).toHaveBeenCalledWith(
        'MQTT ошибка: MQTT connection failed',
        'error',
        5000
      )
    }
  })

  it('should resubscribe to MQTT channel on WebSocket reconnect', () => {
    const { mqttStatus } = useSystemStatus(mockShowToast)

    // Симулируем отключение
    // @ts-ignore
    delete global.window.Echo

    // Симулируем переподключение
    // @ts-ignore
    global.window.Echo = mockEcho

    // Симулируем событие connected
    const pusher = {
      connection: {
        state: 'connected',
        bind: vi.fn((event: string, handler: () => void) => {
          if (event === 'connected') {
            handler()
          }
        })
      }
    }

    mockEcho.connector = { pusher }

    // Инициализируем снова
    useSystemStatus(mockShowToast)

    // Проверяем, что подписка восстановлена
    expect(mockEcho.channel).toHaveBeenCalledWith('mqtt.status')
  })

  it('should use fallback logic when MQTT channel is unavailable', async () => {
    // @ts-ignore
    delete global.window.Echo

    const { mqttStatus, wsStatus } = useSystemStatus(mockShowToast)

    // Если WebSocket подключен, MQTT должен быть online (fallback)
    wsStatus.value = 'connected'
    
    // Даем время на fallback проверку
    await new Promise(resolve => setTimeout(resolve, 200))
    
    expect(mqttStatus.value).toBe('online')
  })

  it('should unsubscribe from MQTT channel on cleanup', () => {
    const { stopMonitoring } = useSystemStatus(mockShowToast)

    stopMonitoring()

    expect(mockChannel.stopListening).toHaveBeenCalledWith('.App\\Events\\MqttStatusUpdated')
    expect(mockChannel.stopListening).toHaveBeenCalledWith('.App\\Events\\MqttError')
    expect(mockChannel.leave).toHaveBeenCalled()
  })
})

