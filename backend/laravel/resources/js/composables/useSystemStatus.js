/**
 * Composable для управления статусами системы (Core, DB, WebSocket, MQTT)
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useApi } from './useApi'

const POLL_INTERVAL = 30000 // 30 секунд
const MQTT_STATUS_TIMEOUT = 30000 // 30 секунд для определения MQTT статуса

export function useSystemStatus(showToast = null) {
  const { api } = useApi(showToast)
  
  // Статусы компонентов системы
  const coreStatus = ref('unknown') // 'ok' | 'fail' | 'unknown'
  const dbStatus = ref('unknown') // 'ok' | 'fail' | 'unknown'
  const wsStatus = ref('unknown') // 'connected' | 'disconnected' | 'unknown'
  const mqttStatus = ref('unknown') // 'online' | 'offline' | 'degraded' | 'unknown'
  
  const lastUpdate = ref(null)
  let healthPollInterval = null
  let wsConnectionCheckInterval = null
  let mqttStatusCheckInterval = null

  /**
   * Проверка статуса Core и Database через /api/system/health
   */
  async function checkHealth() {
    try {
      const response = await api.get('/api/system/health')
      const data = response.data?.data || response.data || {}
      
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
  function checkWebSocketStatus() {
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
  function setupWebSocketListeners() {
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
        pusher.connection = pusher.connection || {}
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
  function bindConnectionEvents(connection) {
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

      connection.bind('state_change', (states) => {
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
   * Проверка статуса MQTT через WebSocket канал nodes.status
   * MQTT статус определяется на основе статусов узлов
   */
  function checkMqttStatus() {
    if (!window.Echo) {
      mqttStatus.value = 'unknown'
      return
    }

    // Подписываемся на глобальный канал статусов узлов
    // В реальной реализации backend должен транслировать NodeStatusUpdated события
    // Здесь мы используем упрощенную логику: если WebSocket подключен, считаем MQTT доступным
    // В production нужно подписаться на канал nodes.status или zones_status_summary
    
    // Временная логика: если WebSocket подключен, считаем MQTT онлайн
    // В реальности нужно слушать события NodeStatusUpdated
    if (wsStatus.value === 'connected') {
      // В production здесь должна быть подписка на канал с агрегированным статусом MQTT
      // Например: window.Echo.channel('nodes.status').listen('.App\\Events\\NodeStatusUpdated', ...)
      mqttStatus.value = 'online'
    } else {
      mqttStatus.value = 'offline'
    }
  }

  /**
   * Инициализация мониторинга статусов
   */
  function startMonitoring() {
    // Первоначальная проверка
    checkHealth()
    
    // Даем время на инициализацию Echo перед первой проверкой WebSocket
    setTimeout(() => {
      checkWebSocketStatus()
      setupWebSocketListeners()
    }, 500)
    
    checkMqttStatus()

    // Периодическая проверка здоровья (Core + DB)
    healthPollInterval = setInterval(() => {
      checkHealth()
    }, POLL_INTERVAL)

    // Периодическая проверка WebSocket
    wsConnectionCheckInterval = setInterval(() => {
      checkWebSocketStatus()
    }, 5000) // Каждые 5 секунд

    // Периодическая проверка MQTT
    mqttStatusCheckInterval = setInterval(() => {
      checkMqttStatus()
    }, 10000) // Каждые 10 секунд
  }

  /**
   * Остановка мониторинга
   */
  function stopMonitoring() {
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
    coreStatus: computed(() => coreStatus.value),
    dbStatus: computed(() => dbStatus.value),
    wsStatus: computed(() => wsStatus.value),
    mqttStatus: computed(() => mqttStatus.value),
    lastUpdate: computed(() => lastUpdate.value),
    
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

