/**
 * Composable для управления статусами системы (Core, DB, WebSocket, MQTT)
 */
import { ref, computed, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { useApi, type ToastHandler } from './useApi'
import { logger } from '@/utils/logger'

const POLL_INTERVAL = 30000 // 30 секунд
const RATE_LIMIT_BACKOFF = 60000 // 60 секунд при ошибке 429
const WS_CHECK_INTERVAL = 5000 // 5 секунд для проверки WebSocket

type CoreStatus = 'ok' | 'fail' | 'unknown'
type DbStatus = 'ok' | 'fail' | 'unknown'
type WsStatus = 'connected' | 'disconnected' | 'unknown'
type MqttStatus = 'online' | 'offline' | 'degraded' | 'unknown'
type ServiceStatus = 'ok' | 'fail' | 'unknown'

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
  const historyLoggerStatus: Ref<ServiceStatus> = ref('unknown')
  const automationEngineStatus: Ref<ServiceStatus> = ref('unknown')
  
  const lastUpdate: Ref<Date | null> = ref(null)
  let healthPollInterval: ReturnType<typeof setInterval> | null = null
  let wsConnectionCheckInterval: ReturnType<typeof setInterval> | null = null
  
  // Флаг для отслеживания rate limiting
  let isRateLimited = false
  let rateLimitTimeout: ReturnType<typeof setTimeout> | null = null
  
  // Флаг для предотвращения одновременных запросов
  let isCheckingHealth = false

  /**
   * Проверка статуса Core, Database, MQTT и сервисов через /api/system/health
   * Объединенная функция для избежания дублирующих запросов
   */
  async function checkHealth(): Promise<void> {
    // Пропускаем запрос, если активен rate limiting
    if (isRateLimited) {
      logger.warn('[useSystemStatus] Пропуск запроса из-за rate limiting')
      return
    }
    
    // Пропускаем запрос, если уже выполняется проверка
    if (isCheckingHealth) {
      logger.warn('[useSystemStatus] Пропуск запроса - проверка уже выполняется')
      return
    }
    
    isCheckingHealth = true

    try {
      const response = await api.get<{ 
        data?: { 
          app?: string
          db?: string
          mqtt?: string
          history_logger?: string
          automation_engine?: string
        }
      } | { 
        app?: string
        db?: string
        mqtt?: string
        history_logger?: string
        automation_engine?: string
      }>('/api/system/health')
      
      const data = ((response.data as { data?: { app?: string; db?: string; mqtt?: string; history_logger?: string; automation_engine?: string } })?.data || 
                   (response.data as { app?: string; db?: string; mqtt?: string; history_logger?: string; automation_engine?: string })) || {}
      
      // Обновляем статусы Core и DB
      coreStatus.value = data.app === 'ok' ? 'ok' : 'fail'
      dbStatus.value = data.db === 'ok' ? 'ok' : 'fail'
      
      // Обновляем статус MQTT
      if (data.mqtt === 'ok' || data.mqtt === 'online' || data.mqtt === 'connected') {
        mqttStatus.value = 'online'
      } else if (data.mqtt === 'fail' || data.mqtt === 'offline' || data.mqtt === 'disconnected') {
        mqttStatus.value = 'offline'
      } else if (data.mqtt === 'degraded') {
        mqttStatus.value = 'degraded'
      } else {
        // Если статус MQTT не указан, используем fallback логику
        if (wsStatus.value === 'connected') {
          mqttStatus.value = 'online'
        } else {
          mqttStatus.value = 'unknown'
        }
      }
      
      // Проверка статусов сервисов
      if (data.history_logger) {
        historyLoggerStatus.value = data.history_logger === 'ok' ? 'ok' : 'fail'
      } else {
        historyLoggerStatus.value = 'unknown'
      }
      
      if (data.automation_engine) {
        automationEngineStatus.value = data.automation_engine === 'ok' ? 'ok' : 'fail'
      } else {
        automationEngineStatus.value = 'unknown'
      }
      
      lastUpdate.value = new Date()
      
      // Сбрасываем флаг rate limiting при успешном запросе
      if (isRateLimited) {
        isRateLimited = false
        if (rateLimitTimeout) {
          clearTimeout(rateLimitTimeout)
          rateLimitTimeout = null
        }
      }
    } catch (err: any) {
      // Обработка ошибки 429 (Too Many Requests)
      if (err?.response?.status === 429) {
        isRateLimited = true
        logger.warn('[useSystemStatus] Получена ошибка 429, приостанавливаем запросы на', RATE_LIMIT_BACKOFF / 1000, 'секунд')
        
        // Очищаем предыдущий timeout, если он был
        if (rateLimitTimeout) {
          clearTimeout(rateLimitTimeout)
        }
        
        // Устанавливаем таймер для сброса rate limiting
        rateLimitTimeout = setTimeout(() => {
          isRateLimited = false
          rateLimitTimeout = null
          logger.info('[useSystemStatus] Rate limiting сброшен, возобновляем запросы')
        }, RATE_LIMIT_BACKOFF)
        
        // Не показываем toast для 429, чтобы не спамить
        return
      }
      
      // Логируем ошибку для диагностики
      const errorMessage = err?.response?.data?.message || err?.message || 'Неизвестная ошибка'
      const errorStatus = err?.response?.status
      logger.error('[useSystemStatus] Ошибка проверки здоровья системы:', {
        message: errorMessage,
        status: errorStatus,
        url: '/api/system/health',
        error: err,
      })
      
      // Для других ошибок обновляем статусы как fail
      // Но не сбрасываем статусы, если они уже были установлены ранее (сохраняем последние известные значения)
      if (coreStatus.value === 'unknown') {
        coreStatus.value = 'fail'
      }
      if (dbStatus.value === 'unknown') {
        dbStatus.value = 'fail'
      }
      if (mqttStatus.value === 'unknown') {
        mqttStatus.value = 'offline'
      }
      if (historyLoggerStatus.value === 'unknown') {
        historyLoggerStatus.value = 'fail'
      }
      if (automationEngineStatus.value === 'unknown') {
        automationEngineStatus.value = 'fail'
      }
      
      lastUpdate.value = new Date()
      
      if (showToast && err?.response?.status !== 429) {
        showToast(`Ошибка проверки статуса системы: ${errorMessage}`, 'error', 5000)
      }
    } finally {
      // Всегда сбрасываем флаг проверки
      isCheckingHealth = false
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
      logger.warn('[useSystemStatus] Ошибка проверки WebSocket:', err)
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
      logger.warn('[useSystemStatus] Ошибка настройки WebSocket listeners:', err)
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
      logger.warn('[useSystemStatus] Ошибка привязки событий connection:', err)
    }
  }

  /**
   * Проверка статуса MQTT через API
   * Теперь MQTT статус получается из checkHealth(), эта функция оставлена для обратной совместимости
   * @deprecated Используйте checkHealth() вместо этой функции
   */
  async function checkMqttStatus(): Promise<void> {
    // Просто вызываем checkHealth, так как он уже получает статус MQTT
    await checkHealth()
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
    }, 500)

    // Периодическая проверка здоровья (Core + DB + MQTT + сервисы)
    // Все статусы получаются из одного запроса /api/system/health
    healthPollInterval = setInterval(() => {
      checkHealth()
    }, POLL_INTERVAL)

    // Периодическая проверка WebSocket (не требует API запросов)
    wsConnectionCheckInterval = setInterval(() => {
      checkWebSocketStatus()
    }, WS_CHECK_INTERVAL)
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
    if (rateLimitTimeout) {
      clearTimeout(rateLimitTimeout)
      rateLimitTimeout = null
    }
    isRateLimited = false
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
    historyLoggerStatus: computed(() => historyLoggerStatus.value) as ComputedRef<ServiceStatus>,
    automationEngineStatus: computed(() => automationEngineStatus.value) as ComputedRef<ServiceStatus>,
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

