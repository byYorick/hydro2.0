import Echo from 'laravel-echo'
import Pusher from 'pusher-js'
import { logger } from './logger'
import { readBooleanEnv } from './env'
import { buildEchoConfig, resolveHost, resolvePort, resolveScheme } from './echoConfig'
import {
  type ActiveTimer,
  type ConnectionHandler,
  bindEchoConnectionEvents,
  clearEchoActiveTimers,
} from './echoConnectionEvents'
import { attemptEchoConnect } from './echoConnectStrategy'
import { createEchoReconciliation } from './echoReconciliation'

// Ленивая загрузка store для избежания ошибок до инициализации Pinia
function getWebSocketStore() {
  try {
    // Проверяем доступность Pinia перед использованием store
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { getActivePinia } = require('pinia')
    const pinia = getActivePinia()
    if (!pinia) {
      return null
    }
    // Динамический импорт для избежания циклических зависимостей
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { useWebSocketStore } = require('@/stores/websocket')
    return useWebSocketStore()
  } catch (err) {
    // Pinia еще не инициализирована или store недоступен - это нормально при начальной загрузке
    return null
  }
}

type WsState = 'connecting' | 'connected' | 'disconnected' | 'unavailable' | 'failed'
type StateListener = (state: WsState) => void

interface ConnectionError {
  message: string
  code?: number
  timestamp: number
}

const BASE_RECONNECT_DELAY = 3000
const RECONNECT_MULTIPLIER = 1.5
const MAX_RECONNECT_DELAY = 60000

const listeners = new Set<StateListener>()

let currentState: WsState = 'disconnected'
let echoInstance: Echo<any> | null = null
let initializing = false
let reconnectAttempts = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectLockUntil = 0
let lastError: ConnectionError | null = null
let isReconnecting = false
let connectionHandlers: ConnectionHandler[] = []
let connectingStartTime = 0 // Отслеживание времени начала подключения (объявлено на уровне модуля)

const activeTimers = new Set<ActiveTimer>()

const reconciliationManager = createEchoReconciliation({
  getApiUrl: () => import.meta.env.VITE_API_URL || '/api',
  dispatchReconciliation: payload => {
    if (typeof window !== 'undefined' && window.dispatchEvent) {
      window.dispatchEvent(new CustomEvent('ws:reconciliation', {
        detail: payload,
      }))
    }
  },
})

function clearActiveTimers(): void {
  clearEchoActiveTimers(activeTimers)
}

function isBrowser(): boolean {
  return typeof window !== 'undefined'
}

function emitState(state: WsState): void {
  currentState = state
  
  // Обновляем store (только если Pinia инициализирована)
  try {
    const wsStore = getWebSocketStore()
    if (wsStore) {
      const connectionState = getConnectionState()
      wsStore.setState(state)
      wsStore.setReconnectAttempts(connectionState.reconnectAttempts)
      wsStore.setLastError(connectionState.lastError)
      wsStore.setSocketId(connectionState.socketId || null)
      wsStore.setConnectionInfo({
        protocol: connectionState.protocol,
        port: connectionState.port,
        host: connectionState.host,
      })
    }
  } catch (err) {
    // Игнорируем ошибки, если Pinia еще не инициализирована
    // Это нормально при начальной загрузке страницы
  }
  
  listeners.forEach(listener => {
    try {
      listener(state)
    } catch (err) {
      logger.warn('[echoClient] State listener error', {
        error: err instanceof Error ? err.message : String(err),
      })
    }
  })
}

emitState('disconnected')

function cleanupConnectionHandlers(): void {
  if (!echoInstance) {
    return
  }
  const connection = echoInstance.connector?.pusher?.connection
  if (!connectionHandlers.length || !connection) {
    connectionHandlers = []
    return
  }
  connectionHandlers.forEach(({ event, handler }) => {
    try {
      connection.unbind(event, handler)
    } catch {
      // no-op
    }
  })
  connectionHandlers = []
}

function teardownEcho(): void {
  if (!isBrowser()) {
    return
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  cleanupConnectionHandlers()
  clearActiveTimers()
  reconciliationManager.reset()
  try {
    echoInstance?.disconnect?.()
  } catch {
    // ignore disconnect errors
  }
  try {
    echoInstance?.connector?.pusher?.disconnect?.()
  } catch {
    // ignore disconnect errors
  }
  echoInstance = null
  if (typeof window !== 'undefined') {
    window.Echo = undefined
  }
  // Сбрасываем флаги состояния
  initializing = false
  reconnectAttempts = 0
  reconnectLockUntil = 0
  isReconnecting = false
  connectingStartTime = 0
  lastError = null
  
  // Устанавливаем состояние disconnected
  emitState('disconnected')
  
  // Очищаем каналы useWebSocket при teardown
  if (typeof window !== 'undefined') {
    // Динамически импортируем cleanupWebSocketChannels, чтобы избежать циклических зависимостей
    import('../composables/useWebSocket').then(({ cleanupWebSocketChannels }) => {
      try {
        cleanupWebSocketChannels()
      } catch (error) {
        logger.warn('[echoClient] Error cleaning up WebSocket channels', {
          error: error instanceof Error ? error.message : String(error),
        })
      }
    }).catch(() => {
      // Игнорируем ошибки импорта (может быть недоступен в некоторых контекстах)
    })
  }
  
  // Уведомляем bootstrap.js о сбросе состояния через событие
  if (typeof window !== 'undefined' && window.dispatchEvent) {
    window.dispatchEvent(new CustomEvent('echo:teardown'))
  }
}

function scheduleReconnect(reason: string): void {
  if (!isBrowser()) {
    return
  }

  const now = Date.now()
  if (now < reconnectLockUntil) {
    logger.debug('[echoClient] Reconnect locked, skipping', {
      reason,
      lockUntil: reconnectLockUntil,
      remaining: reconnectLockUntil - now,
    })
    return
  }

  // Проверяем текущее состояние перед переподключением
  if (echoInstance) {
    const connection = echoInstance.connector?.pusher?.connection
    if (connection) {
      // Если соединение уже подключено или в процессе подключения, не переподключаемся
      if (connection.state === 'connected' || connection.state === 'connecting') {
        logger.debug('[echoClient] Already connected or connecting, skipping reconnect', {
          reason,
          state: connection.state,
          socketId: connection.socket_id,
        })
        reconnectAttempts = 0
        reconnectLockUntil = 0
        isReconnecting = false
        return
      }
      
      if (connection.state === 'connecting') {
        logger.debug('[echoClient] Already connecting, waiting before reconnect', {
          reason,
          state: connection.state,
        })
        // Ждем немного, если соединение в процессе подключения
        reconnectLockUntil = now + 3000 // Блокируем на 3 секунды
        setTimeout(() => {
          if (connection.state !== 'connected' && connection.state !== 'connecting') {
            scheduleReconnect(reason)
          }
        }, 3000)
        return
      }
    }
  }

  reconnectAttempts += 1
  isReconnecting = true

  const delay = Math.min(
    BASE_RECONNECT_DELAY * Math.pow(RECONNECT_MULTIPLIER, reconnectAttempts - 1),
    MAX_RECONNECT_DELAY
  )

  reconnectLockUntil = now + delay
  emitState('connecting')

  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
  }

  logger.info('[echoClient] Scheduling reconnect', {
    attempts: reconnectAttempts,
    reason,
    delay,
  })

  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    try {
      // Проверяем, не идет ли уже инициализация из bootstrap.js
      if (initializing) {
        logger.debug('[echoClient] Echo initialization in progress, skipping reconnect', {
          attempts: reconnectAttempts,
          reason,
        })
        // Переносим переподключение на следующий раз
        reconnectLockUntil = Date.now() + 2000 // Блокируем на 2 секунды
        scheduleReconnect(reason)
        return
      }

      if (!echoInstance) {
        logger.warn('[echoClient] Echo instance missing during reconnect, re-initializing', {
          attempts: reconnectAttempts,
          reason,
        })
        initEcho(true)
        return
      }

      const connection = echoInstance.connector?.pusher?.connection
      
      // Проверяем состояние еще раз перед переподключением
      if (connection) {
        if (connection.state === 'connected') {
          logger.info('[echoClient] Connection established during reconnect delay, skipping', {
            attempts: reconnectAttempts,
            reason,
            socketId: connection.socket_id,
          })
          reconnectAttempts = 0
          reconnectLockUntil = 0
          isReconnecting = false
          emitState('connected')
          return
        }
        
        if (connection.state === 'connecting') {
          logger.debug('[echoClient] Connection still connecting, waiting', {
            attempts: reconnectAttempts,
            reason,
          })
          // Ждем еще немного
          reconnectLockUntil = Date.now() + 2000
          setTimeout(() => {
            if (connection.state !== 'connected' && connection.state !== 'connecting') {
              scheduleReconnect(reason)
            }
          }, 2000)
          return
        }
      }
      
      if (connection && connection.state !== 'connected' && connection.state !== 'connecting') {
        logger.info('[echoClient] Triggering pusher reconnect', {
          attempts: reconnectAttempts,
          reason,
          currentState: connection.state,
        })
        // Используем явный вызов connect() вместо connection.connect()
        // Это более надежно для переподключения
        const pusher = echoInstance.connector?.pusher
        if (pusher && typeof pusher.connect === 'function') {
          pusher.connect()
        } else if (connection && typeof connection.connect === 'function') {
          connection.connect()
        } else {
          // Если методы недоступны, переинициализируем
          logger.warn('[echoClient] Connect methods not available, reinitializing', {
            hasPusher: !!pusher,
            hasConnection: !!connection,
          })
          initEcho(true)
        }
      }
    } catch (error) {
      logger.error('[echoClient] Reconnect attempt failed, forcing reinit', {
        attempts: reconnectAttempts,
        reason,
      }, error)
      // Проверяем, не идет ли уже инициализация перед переинициализацией
      if (!initializing) {
        initEcho(true)
      } else {
        logger.debug('[echoClient] Initialization in progress, skipping re-initialization after error', {})
      }
    }
  }, delay)
}

export function initEcho(forceReinit = false): Echo<any> | null {
  if (!isBrowser()) {
    return null
  }

  const wsEnabled = readBooleanEnv('VITE_ENABLE_WS', true)
  if (!wsEnabled) {
    logger.warn('[echoClient] WebSocket disabled via VITE_ENABLE_WS=false', {})
    emitState('disconnected')
    return null
  }

  // Улучшена защита от множественных инициализаций
  if (initializing) {
    logger.debug('[echoClient] Echo initialization already in progress', {})
    return echoInstance
  }
  

  if (typeof window !== 'undefined' && window.Echo && !echoInstance) {
    const windowEcho = window.Echo
    const pusher = windowEcho.connector?.pusher
    const connection = pusher?.connection
    const state = connection?.state
    
    if (state === 'connected' || state === 'connecting') {
      // Активное соединение - синхронизируем echoInstance с window.Echo
      logger.info('[echoClient] HMR detected: reusing existing active window.Echo', {
        state: state,
        socketId: connection?.socket_id,
      })
      echoInstance = windowEcho
      // Сбрасываем флаги, так как соединение уже активно
      initializing = false
      reconnectAttempts = 0
      reconnectLockUntil = 0
      isReconnecting = false
      connectingStartTime = 0
      lastError = null
      emitState('connected')
      return echoInstance
    } else if (!forceReinit) {
   
      logger.debug('[echoClient] HMR detected: window.Echo exists but inactive', {
        state: state,
      })
      echoInstance = windowEcho
    }
  }
  
  // Дополнительная проверка - если соединение активно и не требуется принудительная переинициализация
  if (echoInstance && !forceReinit) {
    const connection = echoInstance.connector?.pusher?.connection
    if (connection && (connection.state === 'connected' || connection.state === 'connecting')) {
      logger.debug('[echoClient] Echo already initialized and active, skipping', {
        state: connection.state,
        socketId: connection.socket_id,
      })
      return echoInstance
    }
  }

  if (forceReinit) {
    teardownEcho()
    // teardown выполнен синхронно, задержка не нужна
    // Продолжаем инициализацию сразу
  }

  try {
    initializing = true
    if (typeof window !== 'undefined') {
      window.Pusher = Pusher
    }

    const config = buildEchoConfig()
    
    logger.info('[echoClient] Creating Echo instance with config', {
      hasWsPath: 'wsPath' in config,
      wsPath: config.wsPath,
      key: config.key,
      wsHost: config.wsHost,
      wsPort: config.wsPort,
    })
    
    echoInstance = new Echo(config)
    window.Echo = echoInstance

    const pusher = echoInstance?.connector?.pusher
    const connection = pusher?.connection

    if (!pusher) {
      logger.warn('[echoClient] Pusher not found after Echo creation', {
        hasEcho: !!echoInstance,
        hasConnector: !!echoInstance?.connector,
      })
    }
    cleanupConnectionHandlers()
    connectionHandlers = bindEchoConnectionEvents(connection, {
      activeTimers,
      clearActiveTimers,
      emitState,
      scheduleReconnect,
      setReconnectAttempts: value => {
        reconnectAttempts = value
      },
      setReconnectLockUntil: value => {
        reconnectLockUntil = value
      },
      setIsReconnecting: value => {
        isReconnecting = value
      },
      setLastError: value => {
        lastError = value
      },
      getConnectingStartTime: () => connectingStartTime,
      setConnectingStartTime: value => {
        connectingStartTime = value
      },
      performReconciliation: () => {
        void reconciliationManager.performReconciliation()
      },
    })
    emitState('connecting')
    
    // Сбрасываем таймер подключения при новой инициализации
    connectingStartTime = 0

    attemptEchoConnect({
      getRuntime: () => {
        const runtimePusher = echoInstance?.connector?.pusher
        const runtimeConnection = runtimePusher?.connection
        if (!runtimePusher || !runtimeConnection) {
          return null
        }
        return {
          pusher: runtimePusher,
          connection: runtimeConnection,
        }
      },
    })

    return echoInstance
  } catch (error) {
    lastError = {
      message: error instanceof Error ? error.message : String(error),
      timestamp: Date.now(),
    }
    logger.error('[echoClient] Failed to initialize Echo', {}, error)
    
    // Сбрасываем флаги состояния при ошибке
    initializing = false
    reconnectAttempts = 0
    reconnectLockUntil = 0
    isReconnecting = false
    connectingStartTime = 0
    
    // Устанавливаем состояние failed и disconnected
    emitState('failed')
    emitState('disconnected')
    
    // Очищаем экземпляр
    window.Echo = undefined
    echoInstance = null
    
    // Уведомляем bootstrap.js о сбросе состояния
    if (typeof window !== 'undefined' && window.dispatchEvent) {
      window.dispatchEvent(new CustomEvent('echo:teardown'))
    }
    
    return null
  } finally {
    initializing = false
  }
}

export function getEchoInstance(): Echo<any> | null {
  return echoInstance
}

export function getEcho(): Echo<any> | null {
  return echoInstance
}

export function isEchoInitializing(): boolean {
  return initializing
}

export function getReconnectAttempts(): number {
  return reconnectAttempts
}

export function getLastError(): ConnectionError | null {
  return lastError
}

export function getConnectionState(): {
  state: WsState
  reconnectAttempts: number
  lastError: ConnectionError | null
  isReconnecting: boolean
  socketId?: string | null
  protocol?: string
  port?: number
  host?: string
} {
  // Более надежное получение socketId
  let socketId: string | null = null
  let protocol: string | undefined
  let port: number | undefined
  let host: string | undefined
  
  try {
    if (echoInstance?.connector?.pusher?.connection) {
      socketId = echoInstance.connector.pusher.connection.socket_id || null
      
      // Получаем телеметрию подключения
      const scheme = resolveScheme()
      protocol = scheme === 'https' ? 'wss' : 'ws'
      port = resolvePort(scheme)
      host = resolveHost()
      
      // Если socketId undefined, но соединение в состоянии connected, ждем немного
      if (!socketId && echoInstance.connector.pusher.connection.state === 'connected') {
        // socketId может присваиваться с небольшой задержкой
        // В этом случае возвращаем null, но логируем для диагностики
        logger.debug('[echoClient] socketId is null but connection is connected', {
          state: echoInstance.connector.pusher.connection.state,
        })
      }
    }
  } catch (error) {
    logger.warn('[echoClient] Error getting socketId', {
      error: error instanceof Error ? error.message : String(error),
    })
  }

  return {
    state: currentState,
    reconnectAttempts,
    lastError,
    isReconnecting,
    socketId,
    protocol,
    port,
    host,
  }
}

export function onWsStateChange(listener: StateListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export { emitState as __emitWsState }

declare global {
  interface Window {
    Echo?: Echo<any>
    Pusher?: typeof Pusher
  }
}
