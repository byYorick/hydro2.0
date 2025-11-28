import Echo from 'laravel-echo'
import Pusher from 'pusher-js'
import { logger, type LogContext } from './logger'

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

function isBrowser(): boolean {
  return typeof window !== 'undefined'
}

function readBooleanEnv(value: unknown, defaultValue: boolean): boolean {
  if (typeof value === 'string') {
    const normalized = value.toLowerCase().trim()
    if (['true', '1', 'yes', 'on'].includes(normalized)) {
      return true
    }
    if (['false', '0', 'no', 'off'].includes(normalized)) {
      return false
    }
  }
  if (typeof value === 'boolean') {
    return value
  }
  return defaultValue
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
  const envScheme = (import.meta as any).env?.VITE_REVERB_SCHEME
  if (typeof envScheme === 'string' && envScheme.trim().length > 0) {
    return envScheme.toLowerCase() === 'https' ? 'https' : 'http'
  }
  if (isBrowser() && typeof window.location?.protocol === 'string') {
    return window.location.protocol === 'https:' ? 'https' : 'http'
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
  const envPort = (import.meta as any).env?.VITE_REVERB_PORT
  if (typeof envPort === 'string' && envPort.trim().length > 0) {
    const parsed = Number(envPort)
    if (!Number.isNaN(parsed)) {
      return parsed
    }
  }
  if (isBrowser()) {
    if (window.location.port) {
      const parsed = Number(window.location.port)
      if (!Number.isNaN(parsed)) {
        return parsed
      }
    }
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

  // ИСПРАВЛЕНО: Возвращаем пустую строку вместо '/app', чтобы избежать дублирования пути
  // Если путь не указан, Pusher будет использовать корневой путь
  return ''
}

function buildEchoConfig(): Record<string, unknown> {
  const scheme = resolveScheme()
  const host = resolveHost()
  const port = resolvePort(scheme)
  const path = resolvePath()
  const forceTls = readBooleanEnv(
    (import.meta as any).env?.VITE_WS_TLS,
    scheme === 'https'
  )

  const key =
    (import.meta as any).env?.VITE_REVERB_APP_KEY ||
    (import.meta as any).env?.VITE_PUSHER_APP_KEY ||
    'local'

  const csrfToken = isBrowser()
    ? document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
    : undefined

  return {
    broadcaster: 'reverb',
    key,
    wsHost: host,
    wsPort: port,
    wssPort: port,
    wsPath: path,
    forceTLS: forceTls,
    enabledTransports: forceTls ? ['wss'] : ['ws', 'wss'],
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
    return
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

  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    try {
      if (!echoInstance) {
        logger.warn('[echoClient] Echo instance missing during reconnect, re-initializing', {
          attempts: reconnectAttempts,
          reason,
        })
        initEcho(true)
        return
      }

      const connection = echoInstance.connector?.pusher?.connection
      if (connection && connection.state !== 'connected' && connection.state !== 'connecting') {
        logger.info('[echoClient] Triggering pusher reconnect', {
          attempts: reconnectAttempts,
          reason,
        })
        connection.connect()
      }
    } catch (error) {
      logger.error('[echoClient] Reconnect attempt failed, forcing reinit', {
        attempts: reconnectAttempts,
        reason,
      }, error)
      initEcho(true)
    }
  }, delay)
}

function bindConnectionEvents(connection: any): void {
  if (!connection) {
    logger.warn('[echoClient] Unable to bind connection handlers: missing connection', {})
    return
  }

  cleanupConnectionHandlers()

  const handlers: ConnectionHandler[] = [
    {
      event: 'connecting',
      handler: () => {
        emitState('connecting')
      },
    },
    {
      event: 'connected',
      handler: () => {
        reconnectAttempts = 0
        reconnectLockUntil = 0
        isReconnecting = false
        lastError = null
        emitState('connected')
      },
    },
    {
      event: 'disconnected',
      handler: () => {
        emitState('disconnected')
        scheduleReconnect('disconnected')
      },
    },
    {
      event: 'unavailable',
      handler: () => {
        emitState('unavailable')
        scheduleReconnect('unavailable')
      },
    },
    {
      event: 'failed',
      handler: () => {
        emitState('failed')
        scheduleReconnect('failed')
      },
    },
    {
      event: 'error',
      handler: (payload: any) => {
        const message =
          payload?.error?.data?.message ||
          payload?.error?.message ||
          payload?.message ||
          'Unknown error'
        const code = payload?.error?.code ?? payload?.code
        lastError = {
          message,
          code,
          timestamp: Date.now(),
        }
        logger.error('[echoClient] WebSocket connection error', {
          message,
          code,
          state: connection.state,
        })
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

  const wsEnabled = readBooleanEnv((import.meta as any).env?.VITE_ENABLE_WS, true)
  if (!wsEnabled) {
    logger.warn('[echoClient] WebSocket disabled via VITE_ENABLE_WS=false', {})
    emitState('disconnected')
    return null
  }

  if (initializing) {
    logger.debug('[echoClient] Echo initialization already in progress', {})
    return echoInstance
  }

  if (echoInstance && !forceReinit) {
    return echoInstance
  }

  if (forceReinit) {
    teardownEcho()
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
  const socketId =
    echoInstance?.connector?.pusher?.connection?.socket_id ?? null

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

