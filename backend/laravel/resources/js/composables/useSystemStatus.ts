/**
 * Composable для управления статусами системы
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useApi, type ToastHandler } from './useApi'
import { logger } from '@/utils/logger'
import { extractData } from '@/utils/apiHelpers'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { getReconnectAttempts, getLastError, getConnectionState, onWsStateChange } from '@/utils/echoClient'

const HEALTH_CHECK_INTERVAL = 30000
const WS_CHECK_INTERVAL = 10000

type CoreStatus = 'ok' | 'fail' | 'unknown'
type DbStatus = 'ok' | 'fail' | 'unknown'
type WsStatus = 'connected' | 'disconnected' | 'connecting' | 'unknown'
type MqttStatus = 'online' | 'offline' | 'degraded' | 'unknown'
type ServiceStatus = 'ok' | 'fail' | 'unknown'

// Singleton для предотвращения множественных интервалов
let sharedState: {
  coreStatus: ReturnType<typeof ref<CoreStatus>>
  dbStatus: ReturnType<typeof ref<DbStatus>>
  wsStatus: ReturnType<typeof ref<WsStatus>>
  mqttStatus: ReturnType<typeof ref<MqttStatus>>
  historyLoggerStatus: ReturnType<typeof ref<ServiceStatus>>
  automationEngineStatus: ReturnType<typeof ref<ServiceStatus>>
  lastUpdate: ReturnType<typeof ref<Date | null>>
  healthInterval: ReturnType<typeof setInterval> | null
  wsInterval: ReturnType<typeof setInterval> | null
  isRateLimited: boolean
  rateLimitBackoffMs: number
  rateLimitTimeout: ReturnType<typeof setTimeout> | null
  subscribers: number
  connectedHandler: (() => void) | null
  disconnectedHandler: (() => void) | null
} | null = null

function resetWebSocketBindings() {
  if (!sharedState) return
  const pusher = window?.Echo?.connector?.pusher
  if (pusher?.connection?.unbind) {
    if (sharedState.connectedHandler) {
      pusher.connection.unbind('connected', sharedState.connectedHandler)
      sharedState.connectedHandler = null
    }
    if (sharedState.disconnectedHandler) {
      pusher.connection.unbind('disconnected', sharedState.disconnectedHandler)
      sharedState.disconnectedHandler = null
    }
  }
}

if (import.meta.hot) {
  import.meta.hot.on('vite:beforeUpdate', () => {
    if (sharedState) {
      if (sharedState.healthInterval) {
        clearInterval(sharedState.healthInterval)
        sharedState.healthInterval = null
      }
      if (sharedState.wsInterval) {
        clearInterval(sharedState.wsInterval)
        sharedState.wsInterval = null
      }
      if (sharedState.rateLimitTimeout) {
        clearTimeout(sharedState.rateLimitTimeout)
        sharedState.rateLimitTimeout = null
      }
      resetWebSocketBindings()
    }
  })
  
  import.meta.hot.dispose(() => {
    if (sharedState) {
      if (sharedState.healthInterval) {
        clearInterval(sharedState.healthInterval)
        sharedState.healthInterval = null
      }
      if (sharedState.wsInterval) {
        clearInterval(sharedState.wsInterval)
        sharedState.wsInterval = null
      }
      if (sharedState.rateLimitTimeout) {
        clearTimeout(sharedState.rateLimitTimeout)
        sharedState.rateLimitTimeout = null
      }
      resetWebSocketBindings()
    }
  })
}

declare global {
  interface Window {
    Echo?: {
      connector?: {
        pusher?: {
          connection?: {
            state?: string
            bind?: (event: string, handler: () => void) => void
            unbind?: (event: string, handler: () => void) => void
          }
        }
      }
    }
  }
}

interface StatusResponse {
  app?: string
  db?: string
  mqtt?: string
  history_logger?: string
  automation_engine?: string
}

export function useSystemStatus(showToast?: ToastHandler) {
  const { api } = useApi(showToast || null)

  // Используем singleton для предотвращения множественных интервалов
  if (!sharedState) {
    sharedState = {
      coreStatus: ref<CoreStatus>('unknown'),
      dbStatus: ref<DbStatus>('unknown'),
      wsStatus: ref<WsStatus>('unknown'),
      mqttStatus: ref<MqttStatus>('unknown'),
      historyLoggerStatus: ref<ServiceStatus>('unknown'),
      automationEngineStatus: ref<ServiceStatus>('unknown'),
      lastUpdate: ref<Date | null>(null),
      healthInterval: null,
      wsInterval: null,
      isRateLimited: false,
      rateLimitBackoffMs: 30000, // Начальный backoff: 30 секунд
      rateLimitTimeout: null,
      subscribers: 0,
      connectedHandler: null,
      disconnectedHandler: null,
    }
  }

  // Увеличиваем счетчик подписчиков
  sharedState.subscribers++

  const coreStatus = sharedState.coreStatus
  const dbStatus = sharedState.dbStatus
  const wsStatus = sharedState.wsStatus
  const mqttStatus = sharedState.mqttStatus
  const historyLoggerStatus = sharedState.historyLoggerStatus
  const automationEngineStatus = sharedState.automationEngineStatus
  const lastUpdate = sharedState.lastUpdate

  const isCoreOk = computed(() => coreStatus.value === 'ok')
  const isDbOk = computed(() => dbStatus.value === 'ok')

  async function checkHealth(): Promise<void> {
    if (!sharedState) return
    // Если уже была ошибка 429, пропускаем запрос
    if (sharedState.isRateLimited) {
      return
    }
    
    try {
      const response = await api.get<{ data?: StatusResponse; app?: string }>(
        '/api/system/health'
      )

      const payload = extractData(response.data) || {}

      coreStatus.value = payload.app === 'ok' ? 'ok' : payload.app === 'fail' ? 'fail' : 'unknown'
      dbStatus.value = payload.db === 'ok' ? 'ok' : payload.db === 'fail' ? 'fail' : 'unknown'
      
      // Обновляем статусы сервисов только если они присутствуют в ответе
      // Если поля отсутствуют (например, при неаутентифицированном запросе),
      // оставляем текущее значение (не перезаписываем 'unknown')
      if ('history_logger' in payload) {
        historyLoggerStatus.value = payload.history_logger === 'ok' ? 'ok' : payload.history_logger === 'fail' ? 'fail' : 'unknown'
      } else {
        // Если поле отсутствует, логируем для диагностики
        logger.debug('[useSystemStatus] history_logger status not in health response', {
          availableFields: Object.keys(payload),
          isAuthenticated: true, // Если мы здесь, значит запрос прошел, но поля нет
        })
        // Оставляем текущее значение, не устанавливаем в 'unknown'
      }
      
      if ('automation_engine' in payload) {
        automationEngineStatus.value = payload.automation_engine === 'ok' ? 'ok' : payload.automation_engine === 'fail' ? 'fail' : 'unknown'
      } else {
        // Если поле отсутствует, логируем для диагностики
        logger.debug('[useSystemStatus] automation_engine status not in health response', {
          availableFields: Object.keys(payload),
          isAuthenticated: true,
        })
        // Оставляем текущее значение, не устанавливаем в 'unknown'
      }

      lastUpdate.value = new Date()
      // Сбрасываем флаг и backoff при успешном запросе
      if (sharedState && sharedState.isRateLimited) {
        sharedState.isRateLimited = false
        sharedState.rateLimitBackoffMs = 30000 // Сбрасываем backoff до начального значения
        if (sharedState.rateLimitTimeout) {
          clearTimeout(sharedState.rateLimitTimeout)
          sharedState.rateLimitTimeout = null
        }
        logger.debug('[useSystemStatus] Rate limit cleared after successful health check', {})
      }
    } catch (error: any) {
      // Игнорируем отмененные запросы (Inertia.js при навигации)
      if (error?.code === 'ERR_CANCELED' || 
          error?.name === 'CanceledError' || 
          error?.message === 'canceled' ||
          error?.message === 'Request aborted') {
        // Не логируем отмененные запросы - это нормальное поведение
        return
      }
      
      // Обработка ошибки 429 (Too Many Requests)
      if (error?.response?.status === 429) {
        if (!sharedState) {
          logger.debug('[useSystemStatus] Rate limited but sharedState is null, skipping', {})
          return
        }
        
        sharedState.isRateLimited = true
        
        // Останавливаем текущий интервал при rate limiting
        if (sharedState.healthInterval) {
          clearInterval(sharedState.healthInterval)
          sharedState.healthInterval = null
        }
        
        // Очищаем предыдущий timeout, если он был
        if (sharedState.rateLimitTimeout) {
          clearTimeout(sharedState.rateLimitTimeout)
          sharedState.rateLimitTimeout = null
        }
        
        // Планируем возобновление с экспоненциальным backoff
        const backoffMs = sharedState.rateLimitBackoffMs
        logger.debug('[useSystemStatus] Rate limited, scheduling resume with backoff', {
          backoffMs,
          nextCheckIn: `${Math.round(backoffMs / 1000)}s`,
        })
        
        sharedState.rateLimitTimeout = setTimeout(() => {
          if (!sharedState) {
            logger.debug('[useSystemStatus] Rate limit timeout fired but sharedState is null, skipping', {})
            return
          }
          
          // Увеличиваем backoff экспоненциально (максимум 5 минут)
          sharedState.rateLimitBackoffMs = Math.min(sharedState.rateLimitBackoffMs * 2, 300000)
          sharedState.isRateLimited = false
          sharedState.rateLimitTimeout = null
          
          // Возобновляем проверку здоровья
          if (!sharedState.healthInterval) {
            checkHealth()
            sharedState.healthInterval = setInterval(checkHealth, HEALTH_CHECK_INTERVAL)
            logger.debug('[useSystemStatus] Health checks resumed after rate limit backoff', {
              backoffMs: sharedState.rateLimitBackoffMs,
            })
          }
        }, backoffMs)
        
        // Не показываем Toast для 429, это нормальное поведение rate limiting
        return
      }
      
      // Обработка ошибки 401/403 (неаутентифицирован)
      if (error?.response?.status === 401 || error?.response?.status === 403) {
        logger.debug('[useSystemStatus] Health check failed: unauthenticated', {
          status: error?.response?.status,
        })
        // При ошибке аутентификации не обновляем статусы - они остаются как есть
        // Это нормально, если пользователь не залогинен или сессия истекла
        // historyLoggerStatus и automationEngineStatus останутся 'unknown', что корректно
        return
      }
      
      // Проверяем, что sharedState все еще существует перед логированием и обновлением статусов
      if (!sharedState) {
        logger.debug('[useSystemStatus] Health check failed but sharedState is null, skipping', {})
        return
      }
      
      logger.error('[useSystemStatus] Failed to check health', { 
        error,
        status: error?.response?.status,
        message: error?.message,
      })
      
      // При других ошибках устанавливаем только критичные статусы в 'fail'
      // historyLoggerStatus и automationEngineStatus остаются как есть (не сбрасываем в fail)
      // чтобы не показывать ложные предупреждения, если они были 'unknown'
      coreStatus.value = 'fail'
      dbStatus.value = 'fail'
      // Не обновляем historyLoggerStatus и automationEngineStatus при ошибке,
      // чтобы они остались в текущем состоянии (unknown или последнее известное значение)
      lastUpdate.value = new Date()
      
      if (showToast && error?.response?.status !== 429 && error?.response?.status !== 401 && error?.response?.status !== 403) {
        showToast(`Ошибка проверки статуса системы: ${error.message || 'Ошибка'}`, 'error', TOAST_TIMEOUT.LONG)
      }
    }
  }

  function checkWebSocketStatus(): void {
    const echo = window?.Echo
    if (!echo || !echo.connector || !echo.connector.pusher || !echo.connector.pusher.connection) {
      // НЕ инициализируем Echo здесь, так как это может конфликтовать с bootstrap.js
      // bootstrap.js уже инициализирует Echo, и повторная инициализация может прервать соединение
      // Просто показываем состояние "connecting" и ждем, пока bootstrap.js завершит инициализацию
      const wsEnabled = String((import.meta as any).env.VITE_ENABLE_WS ?? 'true') === 'true'
      if (wsEnabled && !echo) {
        logger.debug('[useSystemStatus] Echo not initialized, waiting for bootstrap.js to initialize', {
          note: 'Echo initialization is handled by bootstrap.js to avoid conflicts',
        })
        // НЕ вызываем initEcho() здесь - это может прервать инициализацию из bootstrap.js
        wsStatus.value = 'connecting'
        return
      }
      // Если Echo не инициализирован и не удалось инициализировать, показываем "connecting" вместо "unknown"
      wsStatus.value = 'connecting'
      return
    }

    const state = echo.connector.pusher.connection.state
    logger.debug('[useSystemStatus] WebSocket state', { 
      state,
      socketId: echo?.connector?.pusher?.connection?.socket_id || null,
      hasConnection: !!echo.connector.pusher.connection,
    })
    if (state === 'connected') {
      wsStatus.value = 'connected'
    } else if (state === 'connecting') {
      wsStatus.value = 'connecting'
    } else if (state === 'unavailable') {
      // unavailable означает, что сервер недоступен, но мы пытаемся подключиться
      wsStatus.value = 'connecting'
      logger.debug('[useSystemStatus] WebSocket unavailable, showing as connecting', { state })
    } else if (state === 'disconnected' || state === 'failed') {
      wsStatus.value = 'disconnected'
    } else {
      // Для неизвестных состояний показываем "connecting" вместо "unknown"
      logger.warn('[useSystemStatus] Unknown WebSocket state', { state })
      wsStatus.value = 'connecting'
    }
  }

  function checkMqttStatus(): void {
    if (wsStatus.value === 'connected') {
      mqttStatus.value = 'online'
    } else if (wsStatus.value === 'disconnected') {
      mqttStatus.value = 'offline'
    } else if (wsStatus.value === 'connecting') {
      mqttStatus.value = 'degraded'
    } else {
      mqttStatus.value = 'unknown'
    }
  }

  function startMonitoring(): void {
    if (!sharedState) return
    // Запускаем интервалы только один раз для всех подписчиков
    if (!sharedState.healthInterval) {
      checkHealth()
      sharedState.healthInterval = setInterval(checkHealth, HEALTH_CHECK_INTERVAL)
    }

    if (!sharedState.wsInterval) {
      checkWebSocketStatus()
      checkMqttStatus()
      sharedState.wsInterval = setInterval(() => {
        checkWebSocketStatus()
        checkMqttStatus()
      }, WS_CHECK_INTERVAL)
    }

    const pusher = window?.Echo?.connector?.pusher
    if (pusher && pusher.connection && typeof pusher.connection.bind === 'function') {
      if (!sharedState.connectedHandler) {
        sharedState.connectedHandler = () => {
          if (!sharedState) return
          wsStatus.value = 'connected'
          checkMqttStatus()
        }
        pusher.connection.bind('connected', sharedState.connectedHandler)
      }
      if (!sharedState.disconnectedHandler) {
        sharedState.disconnectedHandler = () => {
          if (!sharedState) return
          wsStatus.value = 'disconnected'
          checkMqttStatus()
        }
        pusher.connection.bind('disconnected', sharedState.disconnectedHandler)
      }
    }
  }

  function stopMonitoring(): void {
    if (!sharedState) return
    // Останавливаем интервалы только когда все подписчики отписались
    sharedState.subscribers--
    if (sharedState.subscribers <= 0) {
      if (sharedState.healthInterval) {
        clearInterval(sharedState.healthInterval)
        sharedState.healthInterval = null
      }
      if (sharedState.wsInterval) {
        clearInterval(sharedState.wsInterval)
        sharedState.wsInterval = null
      }
      if (sharedState.rateLimitTimeout) {
        clearTimeout(sharedState.rateLimitTimeout)
        sharedState.rateLimitTimeout = null
      }
      resetWebSocketBindings()
      // Сбрасываем singleton только когда нет подписчиков
      sharedState = null
    }
  }

  // Подписка на изменения состояния WebSocket для мгновенного обновления статусов
  let unsubscribeWsState: (() => void) | null = null

  onMounted(() => {
    startMonitoring()
    
    // Подписываемся на изменения состояния WebSocket для мгновенного обновления
    unsubscribeWsState = onWsStateChange((state) => {
      if (!sharedState) return
      
      // Мгновенно обновляем статусы WebSocket и MQTT при изменении состояния
      if (state === 'connected') {
        sharedState.wsStatus.value = 'connected'
        checkMqttStatus()
        logger.debug('[useSystemStatus] WebSocket state changed to connected, statuses updated immediately')
      } else if (state === 'disconnected' || state === 'unavailable' || state === 'failed') {
        sharedState.wsStatus.value = 'disconnected'
        sharedState.mqttStatus.value = 'offline'
        logger.debug('[useSystemStatus] WebSocket state changed to disconnected, statuses updated immediately')
      } else if (state === 'connecting') {
        sharedState.wsStatus.value = 'connecting'
        logger.debug('[useSystemStatus] WebSocket state changed to connecting, statuses updated immediately')
      }
    })
  })

  onUnmounted(() => {
    // Отписываемся от изменений состояния WebSocket
    if (unsubscribeWsState) {
      unsubscribeWsState()
      unsubscribeWsState = null
    }
    stopMonitoring()
  })

  // WebSocket детали из echoClient
  const wsReconnectAttempts = computed(() => getReconnectAttempts())
  const wsLastError = computed(() => getLastError())
  const wsConnectionDetails = computed(() => getConnectionState())

  return {
    coreStatus,
    dbStatus,
    wsStatus,
    mqttStatus,
    historyLoggerStatus,
    automationEngineStatus,
    lastUpdate,
    isCoreOk,
    isDbOk,
    checkHealth,
    checkWebSocketStatus,
    checkMqttStatus,
    startMonitoring,
    stopMonitoring,
    wsReconnectAttempts,
    wsLastError,
    wsConnectionDetails,
  }
}
