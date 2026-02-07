import { logger } from './logger'
import type { EchoLike } from '@/ws/subscriptionTypes'

interface EchoConnectionRuntime {
  pusher: NonNullable<EchoLike['connector']>['pusher']
  connection: NonNullable<NonNullable<EchoLike['connector']>['pusher']>['connection']
}

interface AttemptEchoConnectDeps {
  getRuntime: () => EchoConnectionRuntime | null
}

export function attemptEchoConnect(deps: AttemptEchoConnectDeps): void {
  const maxAttempts = 5
  const delays = [100, 300, 500, 1000, 2000]

  const runAttempt = (attempt = 0): void => {
    setTimeout(() => {
      try {
        const runtime = deps.getRuntime()
        const pusher = runtime?.pusher
        const connection = runtime?.connection

        if (!connection) {
          if (attempt < maxAttempts - 1) {
            logger.debug('[echoClient] Connection not ready, retrying', { attempt: attempt + 1 })
            runAttempt(attempt + 1)
          } else {
            logger.warn('[echoClient] Connection not available after all attempts', { attempts: maxAttempts })
          }
          return
        }

        if (connection.state !== 'connected' && connection.state !== 'connecting') {
          logger.info('[echoClient] Explicitly calling pusher.connect()', {
            currentState: connection.state,
            attempt: attempt + 1,
          })

          if (pusher && typeof pusher.connect === 'function') {
            pusher.connect()
          } else if (typeof connection.connect === 'function') {
            connection.connect()
          } else if (attempt < maxAttempts - 1) {
            logger.debug('[echoClient] Connect method not available, retrying', { attempt: attempt + 1 })
            runAttempt(attempt + 1)
          }
          return
        }

        const socketId = connection.socket_id
        logger.debug('[echoClient] Connection already active', {
          state: connection.state,
          socketId: socketId || 'not yet assigned',
        })

        if (connection.state === 'connected' && !socketId && attempt < maxAttempts - 1) {
          logger.debug('[echoClient] Connected but socketId missing, waiting', {
            attempt: attempt + 1,
          })
          runAttempt(attempt + 1)
        }
      } catch (err) {
        logger.warn('[echoClient] Error calling pusher.connect()', {
          error: err instanceof Error ? err.message : String(err),
          attempt: attempt + 1,
        })
        if (attempt < maxAttempts - 1) {
          runAttempt(attempt + 1)
        }
      }
    }, delays[Math.min(attempt, delays.length - 1)])
  }

  runAttempt(0)
}
