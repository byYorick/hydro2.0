/**
 * Composable для управления статусами системы
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useApi, type ToastHandler } from './useApi'
import { logger } from '@/utils/logger'
import { getReconnectAttempts, getLastError, getConnectionState, initEcho } from '@/utils/echoClient'

const HEALTH_CHECK_INTERVAL = 30000
const WS_CHECK_INTERVAL = 10000

type CoreStatus = 'ok' | 'fail' | 'unknown'
type DbStatus = 'ok' | 'fail' | 'unknown'
type WsStatus = 'connected' | 'disconnected' | 'connecting' | 'unknown'
type MqttStatus = 'online' | 'offline' | 'degraded' | 'unknown'
type ServiceStatus = 'ok' | 'fail' | 'unknown'

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

  const coreStatus = ref<CoreStatus>('unknown')
  const dbStatus = ref<DbStatus>('unknown')
  const wsStatus = ref<WsStatus>('unknown')
  const mqttStatus = ref<MqttStatus>('unknown')
  const historyLoggerStatus = ref<ServiceStatus>('unknown')
  const automationEngineStatus = ref<ServiceStatus>('unknown')
  const lastUpdate = ref<Date | null>(null)

  const isCoreOk = computed(() => coreStatus.value === 'ok')
  const isDbOk = computed(() => dbStatus.value === 'ok')

  let healthInterval: ReturnType<typeof setInterval> | null = null
  let wsInterval: ReturnType<typeof setInterval> | null = null
  let connectedHandler: (() => void) | null = null
  let disconnectedHandler: (() => void) | null = null

  const resetWebSocketBindings = () => {
    const pusher = window?.Echo?.connector?.pusher
    if (pusher?.connection?.unbind) {
      if (connectedHandler) {
        pusher.connection.unbind('connected', connectedHandler)
        connectedHandler = null
      }
      if (disconnectedHandler) {
        pusher.connection.unbind('disconnected', disconnectedHandler)
        disconnectedHandler = null
      }
    }
  }

  async function checkHealth(): Promise<void> {
    try {
      const response = await api.get<{ data?: StatusResponse; app?: string }>(
        '/api/system/health'
      )

      const payload = response.data?.data || response.data || {}

      coreStatus.value = payload.app === 'ok' ? 'ok' : payload.app === 'fail' ? 'fail' : 'unknown'
      dbStatus.value = payload.db === 'ok' ? 'ok' : payload.db === 'fail' ? 'fail' : 'unknown'
      historyLoggerStatus.value = payload.history_logger === 'ok' ? 'ok' : payload.history_logger === 'fail' ? 'fail' : 'unknown'
      automationEngineStatus.value = payload.automation_engine === 'ok' ? 'ok' : payload.automation_engine === 'fail' ? 'fail' : 'unknown'

      lastUpdate.value = new Date()
    } catch (error: any) {
      logger.error('[useSystemStatus] Failed to check health', { error })
      coreStatus.value = coreStatus.value === 'unknown' ? 'fail' : coreStatus.value
      dbStatus.value = dbStatus.value === 'unknown' ? 'fail' : dbStatus.value
      lastUpdate.value = new Date()
      if (showToast) {
        showToast(`Ошибка проверки статуса системы: ${error.message || 'Ошибка'}`, 'error', 5000)
      }
    }
  }

  function checkWebSocketStatus(): void {
    const echo = window?.Echo
    if (!echo || !echo.connector || !echo.connector.pusher || !echo.connector.pusher.connection) {
      // ИСПРАВЛЕНО: НЕ инициализируем Echo здесь, так как это может конфликтовать с bootstrap.js
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
      // ИСПРАВЛЕНО: Если Echo не инициализирован и не удалось инициализировать, показываем "connecting" вместо "unknown"
      wsStatus.value = 'connecting'
      return
    }

    const state = echo.connector.pusher.connection.state
    logger.debug('[useSystemStatus] WebSocket state', { 
      state,
      socketId: echo.connector.pusher.connection.socket_id,
      hasConnection: !!echo.connector.pusher.connection,
    })
    if (state === 'connected') {
      wsStatus.value = 'connected'
    } else if (state === 'connecting') {
      wsStatus.value = 'connecting'
    } else if (state === 'unavailable') {
      // ИСПРАВЛЕНО: unavailable означает, что сервер недоступен, но мы пытаемся подключиться
      wsStatus.value = 'connecting'
      logger.debug('[useSystemStatus] WebSocket unavailable, showing as connecting', { state })
    } else if (state === 'disconnected' || state === 'failed') {
      wsStatus.value = 'disconnected'
    } else {
      // ИСПРАВЛЕНО: Для неизвестных состояний показываем "connecting" вместо "unknown"
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
    if (!healthInterval) {
      checkHealth()
      healthInterval = setInterval(checkHealth, HEALTH_CHECK_INTERVAL)
    }

    if (!wsInterval) {
      checkWebSocketStatus()
      checkMqttStatus()
      wsInterval = setInterval(() => {
        checkWebSocketStatus()
        checkMqttStatus()
      }, WS_CHECK_INTERVAL)
    }

    const pusher = window?.Echo?.connector?.pusher
    if (pusher && pusher.connection && typeof pusher.connection.bind === 'function') {
      if (!connectedHandler) {
        connectedHandler = () => {
          wsStatus.value = 'connected'
          checkMqttStatus()
        }
        pusher.connection.bind('connected', connectedHandler)
      }
      if (!disconnectedHandler) {
        disconnectedHandler = () => {
          wsStatus.value = 'disconnected'
          checkMqttStatus()
        }
        pusher.connection.bind('disconnected', disconnectedHandler)
      }
    }
  }

  function stopMonitoring(): void {
    if (healthInterval) {
      clearInterval(healthInterval)
      healthInterval = null
    }
    if (wsInterval) {
      clearInterval(wsInterval)
      wsInterval = null
    }
    resetWebSocketBindings()
  }

  onMounted(() => {
    startMonitoring()
  })

  onUnmounted(() => {
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
