import { logger } from './logger'
import type { WsEventPayload } from '@/ws/subscriptionTypes'

export interface ConnectionHandler {
  event: string
  handler: (payload?: unknown) => void
}

export interface ActiveTimer {
  timeoutId: ReturnType<typeof setTimeout>
  abortController?: AbortController
  onClear?: () => void
}

interface BindConnectionEventsDeps {
  activeTimers: Set<ActiveTimer>
  clearActiveTimers: () => void
  emitState: (state: 'connecting' | 'connected' | 'disconnected' | 'unavailable' | 'failed') => void
  scheduleReconnect: (reason: string) => void
  setReconnectAttempts: (value: number) => void
  setReconnectLockUntil: (value: number) => void
  setIsReconnecting: (value: boolean) => void
  setLastError: (value: { message: string; code?: number; timestamp: number } | null) => void
  getConnectingStartTime: () => number
  setConnectingStartTime: (value: number) => void
  performReconciliation: () => void
}

interface PusherConnectionLike {
  state?: string
  socket_id?: string | null
  bind: (event: string, handler: (payload?: unknown) => void) => void
  unbind: (event: string, handler: (payload?: unknown) => void) => void
  connect?: () => void
}

interface ErrorPayload {
  message?: string
  code?: string | number
  type?: string
  data?: Record<string, unknown>
  stack?: string
}

interface ConnectionErrorEvent extends WsEventPayload {
  message?: string
  code?: string | number
  type?: string
  data?: Record<string, unknown>
  error?: Error | ErrorPayload
}

function getErrorDataMessage(data: Record<string, unknown> | undefined): string | undefined {
  const message = data?.message
  return typeof message === 'string' ? message : undefined
}

function normalizeConnectionErrorPayload(payload: unknown): ConnectionErrorEvent {
  if (!payload || typeof payload !== 'object') {
    return {}
  }

  return payload as ConnectionErrorEvent
}

export function clearEchoActiveTimers(activeTimers: Set<ActiveTimer>): void {
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

export function bindEchoConnectionEvents(
  connection: PusherConnectionLike | null | undefined,
  deps: BindConnectionEventsDeps
): ConnectionHandler[] {
  if (!connection) {
    logger.warn('[echoClient] Unable to bind connection handlers: missing connection', {})
    return []
  }

  deps.clearActiveTimers()
  const UNAVAILABLE_COOLDOWN = 10000
  let lastUnavailableTime = Date.now() - UNAVAILABLE_COOLDOWN
  deps.setConnectingStartTime(0)
  const CONNECTING_TIMEOUT = 15000
  const abortController = new AbortController()

  const handlers: ConnectionHandler[] = [
    {
      event: 'connecting',
      handler: () => {
        deps.setConnectingStartTime(Date.now())

        logger.debug('[echoClient] Connection state: connecting', {
          socketId: connection?.socket_id || 'not yet assigned',
          connectionState: connection?.state,
          timeSinceStart: Date.now() - deps.getConnectingStartTime(),
        })
        deps.emitState('connecting')

        const checkSocketId = (checkAttempt = 0) => {
          if (abortController.signal.aborted) {
            return
          }

          const maxChecks = 5
          const delays = [1000, 2000, 3000, 5000, 7000]
          const delay = delays[Math.min(checkAttempt, delays.length - 1)]

          const timeoutId = setTimeout(() => {
            if (abortController.signal.aborted) {
              return
            }

            const socketId = connection?.socket_id
            const elapsed = Date.now() - deps.getConnectingStartTime()
            const state = connection?.state

            if (socketId) {
              logger.info('[echoClient] socketId assigned during connecting', {
                socketId,
                state,
                elapsed,
                checkAttempt: checkAttempt + 1,
              })
              deps.setConnectingStartTime(0)
            } else if (state === 'connecting' || state === 'connected') {
              logger.debug('[echoClient] Still connecting/connected, socketId not yet assigned', {
                state,
                elapsed,
                checkAttempt: checkAttempt + 1,
                timeout: CONNECTING_TIMEOUT,
              })

              if (elapsed < CONNECTING_TIMEOUT && checkAttempt < maxChecks - 1) {
                checkSocketId(checkAttempt + 1)
              } else if (elapsed > CONNECTING_TIMEOUT) {
                logger.warn('[echoClient] Connecting timeout exceeded without socketId, initiating reconnect', {
                  elapsed,
                  timeout: CONNECTING_TIMEOUT,
                  state,
                  checkAttempt: checkAttempt + 1,
                })
                deps.setConnectingStartTime(0)
                deps.scheduleReconnect('no_socket_id')
              }
            }

            deps.activeTimers.delete(timerRef)
          }, delay)

          const timerRef: ActiveTimer = { timeoutId, abortController }
          deps.activeTimers.add(timerRef)
        }

        checkSocketId(0)
      },
    },
    {
      event: 'connected',
      handler: () => {
        deps.setReconnectAttempts(0)
        deps.setReconnectLockUntil(0)
        deps.setIsReconnecting(false)
        deps.setLastError(null)

        lastUnavailableTime = Date.now() - UNAVAILABLE_COOLDOWN
        deps.setConnectingStartTime(0)

        const socketId = connection?.socket_id
        if (!socketId) {
          logger.warn('[echoClient] Connected but socketId is undefined, waiting for socket_id', {
            connectionState: connection?.state,
          })
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
        deps.emitState('connected')
        deps.clearActiveTimers()

        setTimeout(() => {
          deps.performReconciliation()
        }, 500)
      },
    },
    {
      event: 'disconnected',
      handler: () => {
        logger.info('[echoClient] Connection state: disconnected', {
          socketId: connection.socket_id,
        })

        deps.setConnectingStartTime(0)
        deps.emitState('disconnected')
        deps.clearActiveTimers()
        if (connection.state !== 'connecting') {
          deps.scheduleReconnect('disconnected')
        }
      },
    },
    {
      event: 'unavailable',
      handler: () => {
        const now = Date.now()
        const timeSinceLastUnavailable = now - lastUnavailableTime
        const connectingStartTime = deps.getConnectingStartTime()
        const timeSinceConnectingStart = connectingStartTime > 0 ? now - connectingStartTime : 0

        logger.warn('[echoClient] Connection state: unavailable', {
          socketId: connection.socket_id,
          timeSinceLastUnavailable,
          timeSinceConnectingStart,
          cooldown: UNAVAILABLE_COOLDOWN,
          state: connection.state,
        })

        deps.emitState('unavailable')
        lastUnavailableTime = now

        deps.clearActiveTimers()
        if (connection.state === 'connecting' || timeSinceConnectingStart > 0) {
          const waitTime = timeSinceConnectingStart < CONNECTING_TIMEOUT
            ? CONNECTING_TIMEOUT - timeSinceConnectingStart
            : 5000

          logger.debug('[echoClient] Connection is connecting, waiting before reconnecting', {
            state: connection.state,
            timeSinceConnectingStart,
            waitTime,
            timeout: CONNECTING_TIMEOUT,
          })

          const timeoutId1 = setTimeout(() => {
            if (abortController.signal.aborted) {
              return
            }

            const currentState = connection?.state
            const currentSocketId = connection?.socket_id

            if (currentState === 'connected') {
              logger.info('[echoClient] Connection established during wait, skipping reconnect', {
                state: currentState,
                socketId: currentSocketId,
              })
              deps.setConnectingStartTime(0)
            } else if (currentState === 'connecting') {
              logger.debug('[echoClient] Still connecting after wait, will check again', {
                state: currentState,
                socketId: currentSocketId,
                elapsed: Date.now() - deps.getConnectingStartTime(),
              })

              const timeoutId2 = setTimeout(() => {
                if (abortController.signal.aborted) {
                  return
                }
                if (connection.state !== 'connected' && connection.state !== 'connecting') {
                  logger.info('[echoClient] Connection still unavailable after extended wait, reconnecting', {
                    state: connection.state,
                  })
                  deps.scheduleReconnect('unavailable')
                }
              }, 5000)
              const ref2: ActiveTimer = { timeoutId: timeoutId2, abortController }
              deps.activeTimers.add(ref2)
            } else {
              logger.info('[echoClient] Connection not connecting anymore, reconnecting', {
                state: currentState,
              })
              deps.scheduleReconnect('unavailable')
            }
            deps.activeTimers.delete(ref1)
          }, waitTime)
          const ref1: ActiveTimer = { timeoutId: timeoutId1, abortController }
          deps.activeTimers.add(ref1)
        } else if (timeSinceLastUnavailable > UNAVAILABLE_COOLDOWN) {
          logger.info('[echoClient] Unavailable cooldown passed, reconnecting', {
            timeSinceLastUnavailable,
            cooldown: UNAVAILABLE_COOLDOWN,
          })
          deps.scheduleReconnect('unavailable')
        } else {
          const remaining = UNAVAILABLE_COOLDOWN - timeSinceLastUnavailable
          logger.debug('[echoClient] Unavailable cooldown active, waiting before reconnect', {
            remaining,
            cooldown: UNAVAILABLE_COOLDOWN,
          })
          const timeoutId = setTimeout(() => {
            if (abortController.signal.aborted) {
              return
            }
            if (connection.state !== 'connected' && connection.state !== 'connecting') {
              deps.scheduleReconnect('unavailable')
            } else {
              logger.debug('[echoClient] Connection state changed during cooldown, skipping reconnect', {
                state: connection.state,
              })
            }
          }, remaining)
          deps.activeTimers.add({ timeoutId, abortController })
        }
      },
    },
    {
      event: 'failed',
      handler: () => {
        logger.error('[echoClient] Connection state: failed', {
          socketId: connection.socket_id,
        })
        deps.emitState('failed')
        deps.scheduleReconnect('failed')
      },
    },
    {
      event: 'error',
      handler: (payload: unknown) => {
        const normalizedPayload = normalizeConnectionErrorPayload(payload)
        const nestedError = normalizedPayload.error
        const errorObject = nestedError && typeof nestedError === 'object'
          ? nestedError as ErrorPayload
          : null

        const message =
          getErrorDataMessage(errorObject?.data) ||
          errorObject?.message ||
          normalizedPayload.message ||
          (nestedError instanceof Error ? nestedError.toString() : null) ||
          (nestedError ? JSON.stringify(nestedError) : null) ||
          'Unknown error'
        const code = errorObject?.code ?? normalizedPayload.code ?? errorObject?.type
        const codeAsNumber =
          typeof code === 'number'
            ? code
            : typeof code === 'string' && code.trim() !== '' && Number.isFinite(Number(code))
              ? Number(code)
              : undefined
        const errorType = errorObject?.type || normalizedPayload.type || 'unknown'
        const errorData = errorObject?.data || normalizedPayload.data

        deps.setLastError({
          message,
          code: codeAsNumber,
          timestamp: Date.now(),
        })

        logger.error('[echoClient] WebSocket connection error', {
          message,
          code,
          errorType,
          errorData,
          state: connection?.state,
          socketId: connection?.socket_id,
          fullPayload: normalizedPayload,
          errorStack: errorObject?.stack,
        }, nestedError instanceof Error ? nestedError : undefined)

        if (errorType === 'PusherError' || code === 'PUSHER_ERROR' || message.includes('authorization')) {
          logger.warn('[echoClient] Critical error detected, will reconnect', {
            errorType,
            code,
            message,
          })
        }
      },
    },
  ]

  handlers.forEach(({ event, handler }) => {
    connection.bind(event, handler)
  })

  return handlers
}
