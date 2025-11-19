/**
 * Composable для управления статусами системы (Core, DB, WebSocket, MQTT)
 */
import { ref, computed, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { useApi, type ToastHandler } from './useApi'

const POLL_INTERVAL = 30000 // 30 секунд

type CoreStatus = 'ok' | 'fail' | 'unknown'
type DbStatus = 'ok' | 'fail' | 'unknown'
type WsStatus = 'connected' | 'disconnected' | 'unknown'
type MqttStatus = 'online' | 'offline' | 'degraded' | 'unknown'

// Расширяем Window для Echo
declare global {
  interface Window {
    Echo?: {
      connector?: {
        pusher?: {
          connection?: {
            state?: string
            socket_id?: string
            bind: (event: string, handler: () => void) => void
          }
          channels?: {
            channels?: Record<string, unknown>
          }
        }
      }
    }
  }
}

export function useSystemStatus(showToast?: ToastHandler) {
  const { api } = useApi(showToast || null)
  
  // Статусы компонентов системы
  const coreStatus: Ref<CoreStatus> = ref('unknown')
  const dbStatus: Ref<DbStatus> = ref('unknown')
  const wsStatus: Ref<WsStatus> = ref('unknown')
  const mqttStatus: Ref<MqttStatus> = ref('unknown')
  
  const lastUpdate: Ref<Date | null> = ref(null)
  let healthPollInterval: ReturnType<typeof setInterval> | null = null
  let wsConnectionCheckInterval: ReturnType<typeof setInterval> | null = null
  let mqttStatusCheckInterval: ReturnType<typeof setInterval> | null = null

  /**
   * Проверка статуса Core и Database через /api/system/health
   */
  async function checkHealth(): Promise<void> {
    try {
      const response = await api.get<{ data?: { app?: string; db?: string } } | { app?: string; db?: string }>(
        '/api/system/health'
      )
      const data = ((response.data as { data?: { app?: string; db?: string } })?.data || 
                   (response.data as { app?: string; db?: string })) || {}
      
      coreStatus.value = data.app === 'ok' ? 'ok' : 'fail'
      dbStatus.value = data.db === 'ok' ? 'ok' : 'fail'
      lastUpdate.value = new Date()
    } catch (err) {
      coreStatus.value = 'fail'
      dbStatus.value = 'fail'
      lastUpdate.value = new Date()
      
      if (showToast) {
        showToast('Ошибка проверки статуса системы', 'error', 3000)
      }
    }
  }

  /**
   * Проверка статуса WebSocket соединения
   */
  function checkWebSocketStatus(): void {
    // Проверяем, включен ли WebSocket вообще
    const wsEnabled = String(import.meta.env.VITE_ENABLE_WS || 'false') === 'true'
    const appKey = import.meta.env.VITE_PUSHER_APP_KEY

    // Если WebSocket не включен или нет ключа, показываем как отключенный
    if (!wsEnabled || !appKey) {
      wsStatus.value = 'disconnected'
      return
    }

    // Если Echo еще не инициализирован, ждем немного и проверяем снова
    if (!window.Echo) {
      // Если это первая проверка, оставляем unknown, иначе показываем disconnected
      if (wsStatus.value === 'unknown') {
        // Даем время на инициализацию Echo
        setTimeout(() => {
          if (window.Echo) {
            checkWebSocketStatus()
          } else {
            wsStatus.value = 'disconnected'
          }
        }, 1000)
      } else {
        wsStatus.value = 'disconnected'
      }
      return
    }

    // Laravel Echo использует Pusher под капотом
    // Проверяем состояние соединения через Pusher
    try {
      const pusher = window.Echo?.connector?.pusher
      if (!pusher) {
        wsStatus.value = 'disconnected'
        return
      }

      // Проверяем наличие connection объекта
      if (!pusher.connection) {
        wsStatus.value = 'disconnected'
        return
      }

      const state = pusher.connection?.state
      
      // Проверяем все возможные состояния соединения
      if (state === 'connected') {
        wsStatus.value = 'connected'
      } else if (state === 'connecting' || state === 'unavailable') {
        // В процессе подключения - сохраняем текущий статус, если он был connected
        // Иначе показываем как disconnected
        if (wsStatus.value !== 'connected') {
          wsStatus.value = 'disconnected'
        }
      } else if (state === 'disconnected' || state === 'failed' || state === 'error') {
        wsStatus.value = 'disconnected'
      } else {
        // Для неизвестных состояний проверяем, есть ли активное соединение
        const socketId = pusher.connection?.socket_id
        if (socketId) {
          wsStatus.value = 'connected'
        } else {
          // Если состояние неизвестно и нет socket_id, проверяем через другие методы
          // Проверяем, есть ли активные каналы
          const hasActiveChannels = pusher.channels && Object.keys(pusher.channels.channels || {}).length > 0
          if (hasActiveChannels) {
            wsStatus.value = 'connected'
          } else {
            wsStatus.value = 'disconnected'
          }
        }
      }
    } catch (err) {
      // Если произошла ошибка при проверке, считаем disconnected
      console.warn('[useSystemStatus] Ошибка проверки WebSocket:', err)
      wsStatus.value = 'disconnected'
    }
  }

  /**
   * Подписка на события WebSocket для отслеживания соединения
   */
  function setupWebSocketListeners(): void {
    // Проверяем, включен ли WebSocket
    const wsEnabled = String(import.meta.env.VITE_ENABLE_WS || 'false') === 'true'
    const appKey = import.meta.env.VITE_PUSHER_APP_KEY

    if (!wsEnabled || !appKey) {
      return
    }

    if (!window.Echo) {
      // Если Echo еще не готов, попробуем позже
      setTimeout(() => {
        if (window.Echo) {
          setupWebSocketListeners()
        }
      }, 1000)
      return
    }

    try {
      const pusher = window.Echo?.connector?.pusher
      if (!pusher) {
        return
      }

      // Ждем, пока connection будет готов
      if (!pusher.connection) {
        // Подписываемся на событие инициализации connection
        pusher.connection = pusher.connection || {} as typeof pusher.connection
        setTimeout(() => {
          if (pusher.connection) {
            bindConnectionEvents(pusher.connection)
          }
        }, 500)
        return
      }

      bindConnectionEvents(pusher.connection)
    } catch (err) {
      // Если не удалось настроить слушатели, просто используем периодическую проверку
      console.warn('[useSystemStatus] Ошибка настройки WebSocket listeners:', err)
    }
  }

  /**
   * Привязка событий к connection объекту
   */
  function bindConnectionEvents(connection: NonNullable<typeof window.Echo>['connector']['pusher']['connection']): void {
    if (!connection) return

    try {
      // Слушаем события подключения/отключения
      connection.bind('connected', () => {
        wsStatus.value = 'connected'
        // При переподключении WebSocket переподписываемся на MQTT канал
        if (!mqttStatusChannel) {
          setupMqttStatusSubscription()
        }
      })

      connection.bind('disconnected', () => {
        wsStatus.value = 'disconnected'
      })

      connection.bind('error', () => {
        wsStatus.value = 'disconnected'
      })

      connection.bind('state_change', (states: { previous?: string; current?: string }) => {
        // states: { previous: 'disconnected', current: 'connected' }
        if (states.current === 'connected') {
          wsStatus.value = 'connected'
          // При переподключении WebSocket переподписываемся на MQTT канал
          if (!mqttStatusChannel) {
            setupMqttStatusSubscription()
          }
        } else if (states.current === 'disconnected' || states.current === 'failed') {
          wsStatus.value = 'disconnected'
        }
      })

      // Также проверяем текущее состояние сразу после привязки
      if (connection.state === 'connected') {
        wsStatus.value = 'connected'
        // Если уже подключены, подписываемся на MQTT канал
        if (!mqttStatusChannel) {
          setupMqttStatusSubscription()
        }
      }
    } catch (err) {
      console.warn('[useSystemStatus] Ошибка привязки событий connection:', err)
    }
  }

  /**
   * Подписка на dedicated канал для MQTT статуса
   */
  let mqttStatusChannel: ReturnType<typeof window.Echo>['channel'] | null = null
  let mqttStatusUnsubscribe: (() => void) | null = null

  /**
   * Настройка подписки на канал MQTT статуса
   */
  function setupMqttStatusSubscription(): void {
    if (!window.Echo) {
      mqttStatus.value = 'unknown'
      return
    }

    // Отписываемся от предыдущей подписки, если есть
    if (mqttStatusUnsubscribe) {
      mqttStatusUnsubscribe()
      mqttStatusUnsubscribe = null
      mqttStatusChannel = null
    }

    try {
      // Подписываемся на dedicated канал для MQTT статуса
      const channelName = 'mqtt.status'
      mqttStatusChannel = window.Echo.channel(channelName)
      
      // Слушаем события изменения статуса MQTT брокера
      mqttStatusChannel.listen('.App\\Events\\MqttStatusUpdated', (event: unknown) => {
        const e = event as { status?: string; message?: string; degraded?: boolean }
        
        if (e.status === 'online' || e.status === 'connected') {
          mqttStatus.value = 'online'
        } else if (e.status === 'offline' || e.status === 'disconnected') {
          mqttStatus.value = 'offline'
        } else if (e.degraded || e.status === 'degraded') {
          mqttStatus.value = 'degraded'
        } else {
          mqttStatus.value = 'unknown'
        }
        
        lastUpdate.value = new Date()
      })

      // Также слушаем события ошибок MQTT
      mqttStatusChannel.listen('.App\\Events\\MqttError', (event: unknown) => {
        const e = event as { message?: string }
        mqttStatus.value = 'offline'
        lastUpdate.value = new Date()
        
        if (showToast && e.message) {
          showToast(`MQTT ошибка: ${e.message}`, 'error', 5000)
        }
      })

      // Функция для отписки
      mqttStatusUnsubscribe = () => {
        if (mqttStatusChannel) {
          try {
            mqttStatusChannel.stopListening('.App\\Events\\MqttStatusUpdated')
            mqttStatusChannel.stopListening('.App\\Events\\MqttError')
            mqttStatusChannel.leave()
          } catch (err) {
            console.warn('[useSystemStatus] Ошибка отписки от MQTT канала:', err)
          }
          mqttStatusChannel = null
        }
      }
    } catch (err) {
      console.warn('[useSystemStatus] Ошибка подписки на MQTT канал:', err)
      // Fallback: используем упрощенную логику
      checkMqttStatusFallback()
    }
  }

  /**
   * Fallback проверка статуса MQTT (если канал недоступен)
   */
  function checkMqttStatusFallback(): void {
    if (!window.Echo) {
      mqttStatus.value = 'unknown'
      return
    }

    // Упрощенная логика: если WebSocket подключен, считаем MQTT доступным
    // Это временная мера, пока backend не настроит dedicated канал
    if (wsStatus.value === 'connected') {
      mqttStatus.value = 'online'
    } else {
      mqttStatus.value = 'offline'
    }
  }

  /**
   * Проверка статуса MQTT (legacy метод для обратной совместимости)
   */
  function checkMqttStatus(): void {
    // Если есть активная подписка, статус обновляется автоматически
    // Этот метод используется только для fallback проверки
    if (!mqttStatusChannel) {
      checkMqttStatusFallback()
    }
  }

  /**
   * Инициализация мониторинга статусов
   */
  function startMonitoring(): void {
    // Первоначальная проверка
    checkHealth()
    
    // Даем время на инициализацию Echo перед первой проверкой WebSocket
    setTimeout(() => {
      checkWebSocketStatus()
      setupWebSocketListeners()
      
      // Настраиваем подписку на MQTT статус после инициализации WebSocket
      setupMqttStatusSubscription()
    }, 500)
    
    // Fallback проверка MQTT (на случай, если канал еще не готов)
    checkMqttStatus()

    // Периодическая проверка здоровья (Core + DB)
    healthPollInterval = setInterval(() => {
      checkHealth()
    }, POLL_INTERVAL)

    // Периодическая проверка WebSocket
    wsConnectionCheckInterval = setInterval(() => {
      checkWebSocketStatus()
      
      // Если WebSocket переподключился, переподписываемся на MQTT канал
      if (wsStatus.value === 'connected' && !mqttStatusChannel) {
        setupMqttStatusSubscription()
      }
    }, 5000) // Каждые 5 секунд

    // Периодическая fallback проверка MQTT (если канал недоступен)
    mqttStatusCheckInterval = setInterval(() => {
      // Проверяем только если нет активной подписки
      if (!mqttStatusChannel) {
        checkMqttStatus()
      }
    }, 10000) // Каждые 10 секунд
  }

  /**
   * Остановка мониторинга
   */
  function stopMonitoring(): void {
    if (healthPollInterval) {
      clearInterval(healthPollInterval)
      healthPollInterval = null
    }
    if (wsConnectionCheckInterval) {
      clearInterval(wsConnectionCheckInterval)
      wsConnectionCheckInterval = null
    }
    if (mqttStatusCheckInterval) {
      clearInterval(mqttStatusCheckInterval)
      mqttStatusCheckInterval = null
    }
    
    // Отписываемся от MQTT канала
    if (mqttStatusUnsubscribe) {
      mqttStatusUnsubscribe()
      mqttStatusUnsubscribe = null
      mqttStatusChannel = null
    }
  }

  onMounted(() => {
    startMonitoring()
  })

  onUnmounted(() => {
    stopMonitoring()
  })

  // Computed свойства для удобного доступа
  const isCoreOk = computed(() => coreStatus.value === 'ok')
  const isDbOk = computed(() => dbStatus.value === 'ok')
  const isWsConnected = computed(() => wsStatus.value === 'connected')
  const isMqttOnline = computed(() => mqttStatus.value === 'online')

  return {
    // Статусы
    coreStatus: computed(() => coreStatus.value) as ComputedRef<CoreStatus>,
    dbStatus: computed(() => dbStatus.value) as ComputedRef<DbStatus>,
    wsStatus: computed(() => wsStatus.value) as ComputedRef<WsStatus>,
    mqttStatus: computed(() => mqttStatus.value) as ComputedRef<MqttStatus>,
    lastUpdate: computed(() => lastUpdate.value) as ComputedRef<Date | null>,
    
    // Computed флаги
    isCoreOk,
    isDbOk,
    isWsConnected,
    isMqttOnline,
    
    // Методы
    checkHealth,
    checkWebSocketStatus,
    checkMqttStatus,
    startMonitoring,
    stopMonitoring,
  }
}

