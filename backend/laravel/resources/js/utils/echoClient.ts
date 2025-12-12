import Echo from 'laravel-echo'
import Pusher from 'pusher-js'
import { logger } from './logger'
import { readBooleanEnv } from './env'
import apiClient from './apiClient'
import { useWebSocketStore } from '@/stores/websocket'

type WsState = 'connecting' | 'connected' | 'disconnected' | 'unavailable' | 'failed'
type StateListener = (state: WsState) => void

interface ConnectionError {
  message: string
  code?: number
  timestamp: number
}

interface ConnectionHandler {
  event: string
  handler: (payload?: unknown) => void
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
let lastSyncTimestamp: number | null = null // Время последней синхронизации
let isSyncing = false // Флаг для предотвращения параллельных синхронизаций

// Хранилище активных таймеров для отмены при новом подключении/teardown
interface ActiveTimer {
  timeoutId: ReturnType<typeof setTimeout>
  abortController?: AbortController
  onClear?: () => void
}
const activeTimers = new Set<ActiveTimer>()

function clearActiveTimers(): void {
  activeTimers.forEach(timer => {
    if (timer.abortController) {
      timer.abortController.abort()
    }
    if (timer.timeoutId) {
      clearTimeout(timer.timeoutId)
    }
    if (timer.onClear) {
      timer.onClear()
    }
  })
  activeTimers.clear()
}

function isBrowser(): boolean {
  return typeof window !== 'undefined'
}

function emitState(state: WsState): void {
  currentState = state
  
  // Обновляем store
  try {
    const wsStore = useWebSocketStore()
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
  } catch (err) {
    logger.warn('[echoClient] Error updating WebSocket store', {
      error: err instanceof Error ? err.message : String(err),
    })
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
  // Отменяем все активные таймеры
  if (activeTimers) {
    activeTimers.forEach(timer => {
      if (timer.abortController) {
        timer.abortController.abort()
      }
      if (timer.timeoutId) {
        clearTimeout(timer.timeoutId)
      }
    })
    activeTimers.clear()
  }
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

function resolveScheme(): 'http' | 'https' {
  const envScheme = (import.meta as any).env?.VITE_REVERB_SCHEME
  
  if (typeof envScheme === 'string' && envScheme.trim().length > 0) {
    const scheme = envScheme.toLowerCase().trim()
    if (scheme === 'https' || scheme === 'http') {
      return scheme as 'http' | 'https'
    }
  }
  
  if (isBrowser()) {
    const protocol = window.location.protocol
    if (protocol === 'https:') {
      return 'https'
    }
  }
  
  return 'http'
}

function resolveHost(): string | undefined {
  const envHost = (import.meta as any).env?.VITE_REVERB_HOST
  if (typeof envHost === 'string' && envHost.trim().length > 0) {
    return envHost.trim()
  }
  if (isBrowser()) {
    return window.location.hostname
  }
  return undefined
}

function resolvePort(scheme: 'http' | 'https'): number | undefined {
  // Определяем dev режим несколькими способами для надежности
  const isDev = (import.meta as any).env?.DEV === true || 
                (import.meta as any).env?.MODE === 'development' ||
                (typeof (import.meta as any).env?.DEV !== 'undefined' && (import.meta as any).env?.DEV)
  const envPort = (import.meta as any).env?.VITE_REVERB_PORT
  

  if (isBrowser() && window.location.port) {
    const pagePort = Number(window.location.port)
    if (!Number.isNaN(pagePort) && pagePort !== 6001) {
      // В dev режиме или если явно включен флаг прокси - используем порт страницы
      const useProxyPort = readBooleanEnv('VITE_REVERB_USE_PROXY_PORT', isDev)
      
      if (useProxyPort) {
        logger.info('[echoClient] Using page port for nginx proxy', {
          pagePort,
          isDev,
          envPort: typeof envPort === 'string' ? envPort : 'not set',
          scheme,
          reason: isDev ? 'dev mode (auto)' : 'VITE_REVERB_USE_PROXY_PORT enabled',
          windowPort: window.location.port,
          windowHost: window.location.hostname,
        })
        return pagePort
      }
    }
  }
  
  // Если порт явно задан через переменную окружения, используем его
  if (typeof envPort === 'string' && envPort.trim().length > 0) {
    const parsed = Number(envPort)
    if (!Number.isNaN(parsed)) {
      logger.debug('[echoClient] Using port from VITE_REVERB_PORT env', {
        port: parsed,
        scheme,
      })
      return parsed
    }
  }
  
  // Дефолт: 6001 (порт Reverb)
  logger.debug('[echoClient] Using default port 6001', {
    scheme,
    isDev,
  })
  return 6001
}

function resolvePath(): string | undefined {
  const envPath =
    (import.meta as any).env?.VITE_REVERB_SERVER_PATH ??
    (import.meta as any).env?.VITE_REVERB_PATH

  if (typeof envPath === 'string' && envPath.trim().length > 0) {
    const trimmed = envPath.trim()
    return trimmed.startsWith('/') ? trimmed : `/${trimmed}`
  }

  // Для Reverb по умолчанию не указываем путь
  // pusher-js использует '/app' автоматически (что соответствует Reverb)
  return undefined
}

function buildEchoConfig(): Record<string, unknown> {
  const isDev = (import.meta as any).env?.DEV === true
  const scheme = resolveScheme()
  const host = resolveHost()
  const port = resolvePort(scheme)
  const path = resolvePath()
  

  let shouldUseTls = false
  if (scheme === 'https') {
    shouldUseTls = true
  } else if (isBrowser() && window.location.protocol === 'https:') {
    // Если страница HTTPS, но схема http (например, через прокси), принудительно используем TLS
    shouldUseTls = true
    logger.warn('[echoClient] Page is HTTPS but scheme is HTTP, forcing TLS', {
      scheme,
      protocol: window.location.protocol,
    })
  }
  

  if (isDev && isBrowser() && window.location.protocol === 'https:') {
    shouldUseTls = true
    logger.debug('[echoClient] Dev mode with HTTPS page, forcing TLS to avoid mixed content', {
      scheme,
      protocol: window.location.protocol,
    })
  }
  

  const forceTls = readBooleanEnv('VITE_WS_TLS', shouldUseTls)

  const key =
    (import.meta as any).env?.VITE_REVERB_APP_KEY ||
    (import.meta as any).env?.VITE_PUSHER_APP_KEY ||
    'local'

  const csrfToken = isBrowser()
    ? document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
    : undefined


  const enabledTransports = isDev && forceTls 
    ? ['ws', 'wss'] // В dev на HTTPS разрешаем оба транспорта
    : forceTls 
      ? ['wss'] 
      : ['ws']

  logger.debug('[echoClient] Building Echo config', {
    scheme,
    host,
    port,
    path,
    pathType: typeof path,
    pathIsUndefined: path === undefined,
    forceTls,
    isDev,
    pageProtocol: isBrowser() ? window.location.protocol : 'unknown',
    enabledTransports,
  })

  // Конфигурация Echo
  // Для Reverb: если path не указан, не устанавливаем wsPath - pusher-js использует '/app' по умолчанию
  const echoConfig: Record<string, unknown> = {
    broadcaster: 'reverb',
    key,
    wsHost: host,
    wsPort: port,
    wssPort: port,
    forceTLS: forceTls,
    enabledTransports,
    disableStats: true,
    withCredentials: true,
    authEndpoint: '/broadcasting/auth',
    auth: {
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        ...(csrfToken ? { 'X-CSRF-TOKEN': csrfToken } : {}),
      },
      withCredentials: true,
    },
    encrypted: forceTls,
  }

  // Указываем wsPath только если путь явно задан через переменную окружения
  // Если не указан, pusher-js использует '/app' по умолчанию (что соответствует Reverb)
  if (path) {
    // Валидация: предупреждение, если путь содержит двойной /app/app
    if (path.includes('/app/app') || path.startsWith('/app/app/')) {
      logger.warn('[echoClient] wsPath contains double /app/app pattern', {
        wsPath: path,
        suggestion: 'Remove duplicate /app from path. Reverb listens on /app/{app_key}',
      })
    }
    echoConfig.wsPath = path
    logger.debug('[echoClient] wsPath set in config from environment', { wsPath: path })
  } else {
    logger.debug('[echoClient] wsPath not set, pusher-js will use default /app', {
      note: 'Reverb listens on /app/{app_key}, pusher-js defaults to /app',
    })
  }
  
  logger.debug('[echoClient] Final Echo config', {
    hasWsPath: 'wsPath' in echoConfig,
    wsPath: echoConfig.wsPath,
    key,
    wsHost: host,
    wsPort: port,
  })
  
  return echoConfig
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

function bindConnectionEvents(connection: any): void {
  if (!connection) {
    logger.warn('[echoClient] Unable to bind connection handlers: missing connection', {})
    return
  }

  // Отменяем все предыдущие таймеры перед привязкой новых обработчиков
  clearActiveTimers()

  cleanupConnectionHandlers()

 
  const UNAVAILABLE_COOLDOWN = 10000 // Увеличено до 10 секунд для предотвращения преждевременных переподключений
  let lastUnavailableTime = Date.now() - UNAVAILABLE_COOLDOWN

  connectingStartTime = 0 // Сбрасываем при привязке новых обработчиков
  const CONNECTING_TIMEOUT = 15000 // 15 секунд таймаут для установления соединения
  
  // Создаем AbortController для отмены таймеров этого подключения
  const abortController = new AbortController()

  const handlers: ConnectionHandler[] = [
    {
      event: 'connecting',
      handler: () => {
    
        connectingStartTime = Date.now()
        
        logger.debug('[echoClient] Connection state: connecting', {
          socketId: connection?.socket_id || 'not yet assigned',
          connectionState: connection?.state,
          timeSinceStart: Date.now() - connectingStartTime,
        })
        emitState('connecting')

        const checkSocketId = (checkAttempt = 0) => {
          if (abortController.signal.aborted) {
            return // Таймер отменен
          }
          
          const maxChecks = 5
          const delays = [1000, 2000, 3000, 5000, 7000] // Проверяем через 1, 2, 3, 5, 7 секунд
          const delay = delays[Math.min(checkAttempt, delays.length - 1)]
          
          const timeoutId = setTimeout(() => {
            if (abortController.signal.aborted) {
              return // Таймер отменен
            }
            
            const socketId = connection?.socket_id
            const elapsed = Date.now() - connectingStartTime
            const state = connection?.state
            
            if (socketId) {
              logger.info('[echoClient] socketId assigned during connecting', {
                socketId,
                state,
                elapsed,
                checkAttempt: checkAttempt + 1,
              })
              connectingStartTime = 0 // Сбрасываем таймер при успешном получении socketId
            } else if (state === 'connecting' || state === 'connected') {
              logger.debug('[echoClient] Still connecting/connected, socketId not yet assigned', {
                state,
                elapsed,
                checkAttempt: checkAttempt + 1,
                timeout: CONNECTING_TIMEOUT,
              })
              
              // Продолжаем проверку, если еще не превышен таймаут
              if (elapsed < CONNECTING_TIMEOUT && checkAttempt < maxChecks - 1) {
                checkSocketId(checkAttempt + 1)
              } else if (elapsed > CONNECTING_TIMEOUT) {
                logger.warn('[echoClient] Connecting timeout exceeded without socketId, initiating reconnect', {
                  elapsed,
                  timeout: CONNECTING_TIMEOUT,
                  state,
                  checkAttempt: checkAttempt + 1,
                })
                connectingStartTime = 0
                scheduleReconnect('no_socket_id')
              }
            }
            // Таймер отработал — убираем из набора
            activeTimers.delete(timerRef)
          }, delay)
          
          // Сохраняем таймер для возможной отмены
          const timerRef: ActiveTimer = { timeoutId, abortController }
          activeTimers.add(timerRef)
        }
        
        checkSocketId(0) // Начинаем первую проверку
      },
    },
    {
      event: 'connected',
      handler: () => {
        reconnectAttempts = 0
        reconnectLockUntil = 0
        isReconnecting = false
        lastError = null
      
        lastUnavailableTime = Date.now() - UNAVAILABLE_COOLDOWN
        connectingStartTime = 0 // Сбрасываем таймер подключения
        
        // Проверяем, что socketId действительно получен
        const socketId = connection?.socket_id
        if (!socketId) {
          logger.warn('[echoClient] Connected but socketId is undefined, waiting for socket_id', {
            connectionState: connection?.state,
          })
          // Ждем немного, возможно socketId появится
          setTimeout(() => {
            const delayedSocketId = connection?.socket_id
            if (delayedSocketId) {
              logger.info('[echoClient] socketId received after delay', {
                socketId: delayedSocketId,
              })
            } else {
              logger.error('[echoClient] socketId still undefined after delay, connection may be invalid', {
                connectionState: connection?.state,
              })
            }
          }, 500)
        }
        
        logger.info('[echoClient] Connection state: connected', {
          socketId: socketId || 'pending',
          connectionState: connection?.state,
        })
        emitState('connected')
        clearActiveTimers()
        
        // Запускаем синхронизацию данных при переподключении
        // Используем небольшую задержку, чтобы дать время подписаться на каналы
        setTimeout(() => {
          performReconciliation()
        }, 500)
      },
    },
    {
      event: 'disconnected',
      handler: () => {
        logger.info('[echoClient] Connection state: disconnected', {
          socketId: connection.socket_id,
        })
        
    
        connectingStartTime = 0
        
        emitState('disconnected')
        clearActiveTimers()
        // Переподключаемся только если не в процессе подключения
        if (connection.state !== 'connecting') {
          scheduleReconnect('disconnected')
        }
      },
    },
    {
      event: 'unavailable',
      handler: () => {
        const now = Date.now()
        const timeSinceLastUnavailable = now - lastUnavailableTime
        const timeSinceConnectingStart = connectingStartTime > 0 ? now - connectingStartTime : 0
        
        logger.warn('[echoClient] Connection state: unavailable', {
          socketId: connection.socket_id,
          timeSinceLastUnavailable,
          timeSinceConnectingStart,
          cooldown: UNAVAILABLE_COOLDOWN,
          state: connection.state,
        })
        
        emitState('unavailable')
        lastUnavailableTime = now
        
        clearActiveTimers()
        if (connection.state === 'connecting' || timeSinceConnectingStart > 0) {
          const waitTime = timeSinceConnectingStart < CONNECTING_TIMEOUT 
            ? CONNECTING_TIMEOUT - timeSinceConnectingStart 
            : 5000 // Минимум 5 секунд ожидания
          
          logger.debug('[echoClient] Connection is connecting, waiting before reconnecting', {
            state: connection.state,
            timeSinceConnectingStart,
            waitTime,
            timeout: CONNECTING_TIMEOUT,
          })
          
          // Ждем дольше, если соединение только начало устанавливаться
          const timeoutId1 = setTimeout(() => {
            if (abortController.signal.aborted) {
              return // Таймер отменен
            }
            
            const currentState = connection?.state
            const currentSocketId = connection?.socket_id
            
            if (currentState === 'connected') {
              logger.info('[echoClient] Connection established during wait, skipping reconnect', {
                state: currentState,
                socketId: currentSocketId,
              })
              connectingStartTime = 0
            } else if (currentState === 'connecting') {
              logger.debug('[echoClient] Still connecting after wait, will check again', {
                state: currentState,
                socketId: currentSocketId,
                elapsed: Date.now() - connectingStartTime,
              })
              // Если все еще connecting, ждем еще немного
              const timeoutId2 = setTimeout(() => {
                if (abortController.signal.aborted) {
                  return // Таймер отменен
                }
                if (connection.state !== 'connected' && connection.state !== 'connecting') {
                  logger.info('[echoClient] Connection still unavailable after extended wait, reconnecting', {
                    state: connection.state,
                  })
                  scheduleReconnect('unavailable')
                }
              }, 5000) // Еще 5 секунд ожидания
              const ref2: ActiveTimer = { timeoutId: timeoutId2, abortController }
              activeTimers.add(ref2)
            } else {
              logger.info('[echoClient] Connection not connecting anymore, reconnecting', {
                state: currentState,
              })
              scheduleReconnect('unavailable')
            }
            activeTimers.delete(ref1)
          }, waitTime)
          const ref1: ActiveTimer = { timeoutId: timeoutId1, abortController }
          activeTimers.add(ref1)
        } else if (timeSinceLastUnavailable > UNAVAILABLE_COOLDOWN) {
          // Если прошло достаточно времени с последнего "unavailable", переподключаемся
          logger.info('[echoClient] Unavailable cooldown passed, reconnecting', {
            timeSinceLastUnavailable,
            cooldown: UNAVAILABLE_COOLDOWN,
          })
          scheduleReconnect('unavailable')
        } else {
          // Если не прошло достаточно времени, ждем
          const remaining = UNAVAILABLE_COOLDOWN - timeSinceLastUnavailable
          logger.debug('[echoClient] Unavailable cooldown active, waiting before reconnect', {
            remaining,
            cooldown: UNAVAILABLE_COOLDOWN,
          })
          const timeoutId = setTimeout(() => {
            if (abortController.signal.aborted) {
              return // Таймер отменен
            }
            if (connection.state !== 'connected' && connection.state !== 'connecting') {
              scheduleReconnect('unavailable')
            } else {
              logger.debug('[echoClient] Connection state changed during cooldown, skipping reconnect', {
                state: connection.state,
              })
            }
          }, remaining)
          activeTimers.add({ timeoutId, abortController })
        }
      },
    },
    {
      event: 'failed',
      handler: () => {
        logger.error('[echoClient] Connection state: failed', {
          socketId: connection.socket_id,
        })
        emitState('failed')
        scheduleReconnect('failed')
      },
    },
    {
      event: 'error',
      handler: (payload: any) => {
        // Детальная обработка ошибок для диагностики
        const message =
          payload?.error?.data?.message ||
          payload?.error?.message ||
          payload?.message ||
          payload?.error?.toString() ||
          (payload?.error ? JSON.stringify(payload.error) : null) ||
          'Unknown error'
        const code = payload?.error?.code ?? payload?.code ?? payload?.error?.type
        const errorType = payload?.error?.type || payload?.type || 'unknown'
        const errorData = payload?.error?.data || payload?.data
        
        lastError = {
          message,
          code,
          timestamp: Date.now(),
        }
        
        // Детальное логирование всех данных об ошибке
        logger.error('[echoClient] WebSocket connection error', {
          message,
          code,
          errorType,
          errorData,
          state: connection?.state,
          socketId: connection?.socket_id,
          fullPayload: payload,
          errorStack: payload?.error?.stack,
        }, payload?.error instanceof Error ? payload.error : undefined)
        
        // Если ошибка критична, переподключаемся
        // Некоторые ошибки могут быть временными и не требуют переподключения
        if (errorType === 'PusherError' || code === 'PUSHER_ERROR' || message.includes('authorization')) {
          logger.warn('[echoClient] Critical error detected, will reconnect', {
            errorType,
            code,
            message,
          })
          // Переподключение произойдет через события disconnected/unavailable
        }
      },
    },
  ]

  handlers.forEach(({ event, handler }) => {
    connection.bind(event, handler)
  })
  connectionHandlers = handlers
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
    bindConnectionEvents(connection)
    emitState('connecting')
    
    // Сбрасываем таймер подключения при новой инициализации
    connectingStartTime = 0

    // Явный вызов connect() для гарантии подключения
    // Это решает проблему, когда Pusher.js не подключается автоматически
    // Используем несколько попыток для надежности
    const attemptConnect = (attempt = 0) => {
      const maxAttempts = 5 // Увеличено до 5 попыток
      const delays = [100, 300, 500, 1000, 2000] // Увеличены задержки
      
      setTimeout(() => {
        try {
          const pusher = echoInstance?.connector?.pusher
          const conn = pusher?.connection
          
          if (!conn) {
            if (attempt < maxAttempts - 1) {
              logger.debug('[echoClient] Connection not ready, retrying', { attempt: attempt + 1 })
              attemptConnect(attempt + 1)
            } else {
              logger.warn('[echoClient] Connection not available after all attempts', { attempts: maxAttempts })
            }
            return
          }
          
          if (conn.state !== 'connected' && conn.state !== 'connecting') {
            logger.info('[echoClient] Explicitly calling pusher.connect()', {
              currentState: conn.state,
              attempt: attempt + 1,
            })
            
            if (pusher && typeof pusher.connect === 'function') {
              pusher.connect()
            } else if (conn && typeof conn.connect === 'function') {
              conn.connect()
            } else if (attempt < maxAttempts - 1) {
              logger.debug('[echoClient] Connect method not available, retrying', { attempt: attempt + 1 })
              attemptConnect(attempt + 1)
            }
          } else {
            const socketId = conn.socket_id
            logger.debug('[echoClient] Connection already active', {
              state: conn.state,
              socketId: socketId || 'not yet assigned',
            })
            
            // Если соединение в состоянии "connected" но socketId отсутствует, ждем
            if (conn.state === 'connected' && !socketId && attempt < maxAttempts - 1) {
              logger.debug('[echoClient] Connected but socketId missing, waiting', {
                attempt: attempt + 1,
              })
              attemptConnect(attempt + 1)
            }
          }
        } catch (err) {
          logger.warn('[echoClient] Error calling pusher.connect()', {
            error: err instanceof Error ? err.message : String(err),
            attempt: attempt + 1,
          })
          if (attempt < maxAttempts - 1) {
            attemptConnect(attempt + 1)
          }
        }
      }, delays[Math.min(attempt, delays.length - 1)])
    }
    
    attemptConnect(0)

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

/**
 * Выполняет синхронизацию данных при переподключении WebSocket.
 * 
 * Получает snapshots телеметрии, команд и алертов через API
 * и уведомляет composables о необходимости обновления данных.
 */
async function performReconciliation(): Promise<void> {
  // Предотвращаем параллельные синхронизации
  if (isSyncing) {
    logger.debug('[echoClient] Reconciliation already in progress, skipping')
    return
  }

  // Проверяем, что прошло достаточно времени с последней синхронизации
  const now = Date.now()
  const MIN_SYNC_INTERVAL = 5000 // Минимум 5 секунд между синхронизациями
  if (lastSyncTimestamp && now - lastSyncTimestamp < MIN_SYNC_INTERVAL) {
    logger.debug('[echoClient] Reconciliation skipped: too soon after last sync', {
      timeSinceLastSync: now - lastSyncTimestamp,
      minInterval: MIN_SYNC_INTERVAL,
    })
    return
  }

  isSyncing = true
  lastSyncTimestamp = now

  try {
    logger.info('[echoClient] Starting data reconciliation after reconnect')

    // Получаем полный snapshot данных
    // Используем единый apiClient вместо прямого axios
    const apiUrl = import.meta.env.VITE_API_URL || '/api'
    const response = await apiClient.get(`${apiUrl}/sync/full`, {
      timeout: 10000, // 10 секунд таймаут
    })

    if (response.data?.status === 'ok' && response.data?.data) {
      const { telemetry, commands, alerts } = response.data.data

      logger.info('[echoClient] Reconciliation completed', {
        telemetryCount: telemetry?.length || 0,
        commandsCount: commands?.length || 0,
        alertsCount: alerts?.length || 0,
        timestamp: response.data.timestamp,
      })

      // Уведомляем composables о необходимости обновления данных
      // Используем CustomEvent для передачи данных
      if (typeof window !== 'undefined' && window.dispatchEvent) {
        window.dispatchEvent(new CustomEvent('ws:reconciliation', {
          detail: {
            telemetry: telemetry || [],
            commands: commands || [],
            alerts: alerts || [],
            timestamp: response.data.timestamp,
          },
        }))
      }
    } else {
      logger.warn('[echoClient] Reconciliation failed: invalid response format', {
        status: response.data?.status,
      })
    }
  } catch (error) {
    logger.error('[echoClient] Reconciliation failed', {
      error: error instanceof Error ? error.message : String(error),
    })
    // Не блокируем работу приложения при ошибке синхронизации
  } finally {
    isSyncing = false
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
