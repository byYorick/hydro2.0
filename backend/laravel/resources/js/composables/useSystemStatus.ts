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
        } else if (states.current === 'disconnected' || states.current === 'failed') {
          wsStatus.value = 'disconnected'
        }
      })

      // Также проверяем текущее состояние сразу после привязки
      if (connection.state === 'connected') {
        wsStatus.value = 'connected'
      }
    } catch (err) {
      console.warn('[useSystemStatus] Ошибка привязки событий connection:', err)
    }
  }

  /**
   * Проверка статуса MQTT через API
   * Фронтенд не может напрямую взаимодействовать с MQTT, только через API
   */
  async function checkMqttStatus(): Promise<void> {
    try {
      // Проверяем статус MQTT через API health endpoint
      // Backend должен возвращать статус MQTT в ответе health
      const response = await api.get<{ data?: { mqtt?: string } } | { mqtt?: string }>(
        '/api/system/health'
      )
      const data = ((response.data as { data?: { mqtt?: string } })?.data || 
                   (response.data as { mqtt?: string })) || {}
      
      // Обрабатываем статус MQTT из ответа API
      if (data.mqtt === 'ok' || data.mqtt === 'online' || data.mqtt === 'connected') {
        mqttStatus.value = 'online'
      } else if (data.mqtt === 'fail' || data.mqtt === 'offline' || data.mqtt === 'disconnected') {
        mqttStatus.value = 'offline'
      } else if (data.mqtt === 'degraded') {
        mqttStatus.value = 'degraded'
      } else {
        // Если статус MQTT не указан в ответе, используем fallback логику
        // Считаем MQTT доступным, если WebSocket подключен (так как WebSocket используется для получения данных от backend)
        if (wsStatus.value === 'connected') {
          mqttStatus.value = 'online'
        } else {
          mqttStatus.value = 'unknown'
        }
      }
      
      lastUpdate.value = new Date()
    } catch (err) {
      // При ошибке API считаем MQTT недоступным
      mqttStatus.value = 'offline'
      lastUpdate.value = new Date()
      
      if (showToast) {
        showToast('Ошибка проверки статуса MQTT', 'error', 3000)
      }
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
      
      // Проверяем статус MQTT через API
      checkMqttStatus()
    }, 500)

    // Периодическая проверка здоровья (Core + DB + MQTT)
    healthPollInterval = setInterval(() => {
      checkHealth()
      // Также проверяем MQTT статус через API
      checkMqttStatus()
    }, POLL_INTERVAL)

    // Периодическая проверка WebSocket
    wsConnectionCheckInterval = setInterval(() => {
      checkWebSocketStatus()
    }, 5000) // Каждые 5 секунд

    // Периодическая проверка MQTT через API
    mqttStatusCheckInterval = setInterval(() => {
      checkMqttStatus()
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

