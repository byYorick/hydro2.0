import Echo from 'laravel-echo'
import Pusher from 'pusher-js'
import { logger, type LogContext } from './logger'
import { readBooleanEnv } from './env'

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
let echoInstance: Echo | null = null
let initializing = false
let reconnectAttempts = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectLockUntil = 0
let lastError: ConnectionError | null = null
let isReconnecting = false
let connectionHandlers: ConnectionHandler[] = []
let connectingStartTime = 0 // Отслеживание времени начала подключения (объявлено на уровне модуля)

function isBrowser(): boolean {
  return typeof window !== 'undefined'
}

function emitState(state: WsState): void {
  currentState = state
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
}

function resolveScheme(): 'http' | 'https' {
  // Правильно определяем dev/prod режим
  // import.meta.env.DEV может быть undefined в некоторых случаях, поэтому проверяем также PROD
  const isDev = (import.meta as any).env?.DEV === true || (import.meta as any).env?.MODE === 'development'
  const isProd = (import.meta as any).env?.PROD === true || (import.meta as any).env?.MODE === 'production'
  const envScheme = (import.meta as any).env?.VITE_REVERB_SCHEME
  
  // Если схема явно указана в переменных окружения, используем её
  // В prod режиме ВСЕГДА уважаем указанную схему, даже если isDev не определен
  if (typeof envScheme === 'string' && envScheme.trim().length > 0) {
    const scheme = envScheme.toLowerCase().trim()
    if (scheme === 'https' || scheme === 'http') {
      // В dev режиме с nginx прокси может быть https страница, но ws:// соединение
      // В prod режиме ВСЕГДА уважаем указанную схему
      if (isDev && scheme === 'https') {
        logger.debug('[echoClient] HTTPS scheme detected in dev mode, but using HTTP for WebSocket', {
          envScheme: scheme,
          isDev,
        })
        return 'http'
      }
      // В prod режиме возвращаем указанную схему
      logger.debug('[echoClient] Using scheme from VITE_REVERB_SCHEME', {
        scheme,
        isDev,
        isProd,
      })
      return scheme as 'http' | 'https'
    }
  }
  
  // Если схема не указана, определяем по текущей странице (только в браузере)
  // В prod режиме на https странице используем https, в dev - http (nginx прокси)
  if (isBrowser()) {
    const protocol = window.location.protocol
    if (protocol === 'https:') {
      // В prod режиме используем https, в dev - http (nginx прокси)
      // Если isDev не определен, но isProd определен, используем https
      if (isProd || (!isDev && isProd !== false)) {
        logger.debug('[echoClient] HTTPS page detected, using HTTPS for WebSocket', {
          protocol,
          isDev,
          isProd,
        })
        return 'https'
      }
      // В dev режиме используем http даже для https страницы (nginx прокси)
      logger.debug('[echoClient] HTTPS page in dev mode, using HTTP for WebSocket', {
        protocol,
        isDev,
      })
      return 'http'
    }
  }
  
  // По умолчанию http
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
  const isDev = (import.meta as any).env?.DEV === true
  const envPort = (import.meta as any).env?.VITE_REVERB_PORT
  
  // Если порт явно указан в переменных окружения
  if (typeof envPort === 'string' && envPort.trim().length > 0) {
    const parsed = Number(envPort)
    if (!Number.isNaN(parsed)) {
      // Override только при явном dev флаге И наличии window.location.port
      // В проде БЕЗ ПРОКСИ всегда уважаем VITE_REVERB_PORT=6001, даже если есть window.location.port
      if (isDev && parsed === 6001 && isBrowser() && window.location.port) {
        const nginxPort = Number(window.location.port)
        if (!Number.isNaN(nginxPort) && nginxPort !== 6001) {
          logger.debug('[echoClient] Dev mode: overriding VITE_REVERB_PORT=6001 with nginx port', {
            nginxPort,
            reverbPort: parsed,
            isDev,
            hasWindowPort: !!window.location.port,
          })
          return nginxPort
        }
      }
      // В prod режиме ВСЕГДА используем указанный порт, даже если есть window.location.port
      // Это критично для prod без nginx прокси
      logger.debug('[echoClient] Using VITE_REVERB_PORT from env', {
        port: parsed,
        isDev,
        hasWindowPort: isBrowser() ? !!window.location.port : false,
      })
      return parsed
    }
  }
  
  // Если порт не указан в переменных окружения
  // В prod режиме используем стандартные порты для схемы (443 для https, 80 для http)
  // В dev режиме используем порт страницы (nginx прокси)
  if (isBrowser()) {
    if (isDev && window.location.port) {
      // В dev режиме используем порт nginx для проксирования
      const parsed = Number(window.location.port)
      if (!Number.isNaN(parsed)) {
        return parsed
      }
    }
    // В prod режиме или если порт не указан, используем стандартные порты для схемы
    return scheme === 'https' ? 443 : 80
  }
  
  return undefined
}

function resolvePath(): string | undefined {
  const envPath =
    (import.meta as any).env?.VITE_REVERB_SERVER_PATH ??
    (import.meta as any).env?.VITE_REVERB_PATH ??
    ''

  if (typeof envPath === 'string' && envPath.trim().length > 0) {
    return envPath.startsWith('/') ? envPath : `/${envPath}`
  }

  // Для Laravel Reverb, если REVERB_SERVER_PATH пустой,
  // Pusher автоматически создаст путь /app/{app_key}
  // НЕ указываем '/app' здесь, чтобы избежать дублирования пути
  // nginx проксирует /app/* на Reverb на порту 6001
  // Если указать пустую строку, Pusher создаст правильный путь: /app/local
  return ''
}

function buildEchoConfig(): Record<string, unknown> {
  const isDev = (import.meta as any).env?.DEV === true
  const scheme = resolveScheme()
  const host = resolveHost()
  const port = resolvePort(scheme)
  const path = resolvePath()
  
  // Определяем, нужно ли использовать TLS
  // В prod режиме на https странице используем wss, в dev - ws (nginx прокси)
  // Также проверяем window.location.protocol для надежности
  let shouldUseTls = false
  if (!isDev) {
    // В prod режиме: если схема https или страница https, используем wss
    if (scheme === 'https') {
      shouldUseTls = true
    } else if (isBrowser() && window.location.protocol === 'https:') {
      // Дополнительная проверка: если страница https, но схема http (не должно быть, но на всякий случай)
      shouldUseTls = true
      logger.warn('[echoClient] Page is HTTPS but scheme is HTTP, forcing TLS', {
        scheme,
        protocol: window.location.protocol,
      })
    }
  }
  
  // readBooleanEnv принимает ключ (строку), а не значение
  // Передаем строку 'VITE_WS_TLS' вместо значения из env
  const forceTls = readBooleanEnv(
    'VITE_WS_TLS',
    shouldUseTls // По умолчанию: true для https в prod, false в dev
  )

  const key =
    (import.meta as any).env?.VITE_REVERB_APP_KEY ||
    (import.meta as any).env?.VITE_PUSHER_APP_KEY ||
    'local'

  const csrfToken = isBrowser()
    ? document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
    : undefined

  logger.debug('[echoClient] Building Echo config', {
    scheme,
    host,
    port,
    path,
    forceTls,
    isDev,
    enabledTransports: forceTls ? ['wss'] : ['ws'],
  })

  return {
    broadcaster: 'reverb',
    key,
    wsHost: host,
    wsPort: port,
    wssPort: port,
    wsPath: path,
    forceTLS: forceTls,
    enabledTransports: forceTls ? ['wss'] : ['ws'],
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

  cleanupConnectionHandlers()

  // Отслеживание времени последнего события "unavailable"
  let lastUnavailableTime = 0
  const UNAVAILABLE_COOLDOWN = 10000 // Увеличено до 10 секунд для предотвращения преждевременных переподключений
  // connectingStartTime объявлена на уровне модуля для доступа из всех замыканий
  connectingStartTime = 0 // Сбрасываем при привязке новых обработчиков
  const CONNECTING_TIMEOUT = 15000 // 15 секунд таймаут для установления соединения

  const handlers: ConnectionHandler[] = [
    {
      event: 'connecting',
      handler: () => {
        // Отслеживаем время начала подключения
        if (connectingStartTime === 0) {
          connectingStartTime = Date.now()
        }
        
        logger.debug('[echoClient] Connection state: connecting', {
          socketId: connection?.socket_id || 'not yet assigned',
          connectionState: connection?.state,
          timeSinceStart: Date.now() - connectingStartTime,
        })
        emitState('connecting')
        // НЕ переподключаемся при переходе в "connecting" - это нормальное состояние
        
        // Проверяем socketId через некоторое время после начала подключения
        // Иногда socketId присваивается с небольшой задержкой (может быть до 3-5 секунд)
        // Проверяем несколько раз с увеличивающимися интервалами
        const checkSocketId = (checkAttempt = 0) => {
          const maxChecks = 5
          const delays = [1000, 2000, 3000, 5000, 7000] // Проверяем через 1, 2, 3, 5, 7 секунд
          const delay = delays[Math.min(checkAttempt, delays.length - 1)]
          
          setTimeout(() => {
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
                logger.warn('[echoClient] Connecting timeout exceeded without socketId', {
                  elapsed,
                  timeout: CONNECTING_TIMEOUT,
                  state,
                  checkAttempt: checkAttempt + 1,
                })
              }
            }
          }, delay)
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
        lastUnavailableTime = 0 // Сбрасываем таймер при успешном подключении
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
      },
    },
    {
      event: 'disconnected',
      handler: () => {
        logger.info('[echoClient] Connection state: disconnected', {
          socketId: connection.socket_id,
        })
        emitState('disconnected')
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
        
        // Улучшенная логика обработки "unavailable"
        // Если соединение в процессе подключения, даем больше времени
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
          setTimeout(() => {
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
              setTimeout(() => {
                if (connection.state !== 'connected' && connection.state !== 'connecting') {
                  logger.info('[echoClient] Connection still unavailable after extended wait, reconnecting', {
                    state: connection.state,
                  })
                  scheduleReconnect('unavailable')
                }
              }, 5000) // Еще 5 секунд ожидания
            } else {
              logger.info('[echoClient] Connection not connecting anymore, reconnecting', {
                state: currentState,
              })
              scheduleReconnect('unavailable')
            }
          }, waitTime)
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
          setTimeout(() => {
            if (connection.state !== 'connected' && connection.state !== 'connecting') {
              scheduleReconnect('unavailable')
            } else {
              logger.debug('[echoClient] Connection state changed during cooldown, skipping reconnect', {
                state: connection.state,
              })
            }
          }, remaining)
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

export function initEcho(forceReinit = false): Echo | null {
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
    // @ts-expect-error - constructor typing from laravel-echo
    echoInstance = new Echo(config)
    window.Echo = echoInstance

    const connection = echoInstance.connector?.pusher?.connection
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
    emitState('failed')
    window.Echo = undefined
    echoInstance = null
    return null
  } finally {
    initializing = false
  }
}

export function getEchoInstance(): Echo | null {
  return echoInstance
}

export function getEcho(): Echo | null {
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
} {
  // Более надежное получение socketId
  let socketId: string | null = null
  
  try {
    if (echoInstance?.connector?.pusher?.connection) {
      socketId = echoInstance.connector.pusher.connection.socket_id || null
      
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
  }
}

export function onWsStateChange(listener: StateListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export { emitState as __emitWsState }

declare global {
  interface Window {
    Echo?: Echo
    Pusher?: typeof Pusher
  }
}

