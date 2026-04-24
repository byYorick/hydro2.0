import { logger } from '@/utils/logger'
import { getEcho } from '@/utils/echoClient'
import { chainUpdatedEventSchema } from '@/schemas/execution'
import type { ChainStep } from '@/composables/zoneScheduleWorkspaceTypes'

const EVENT_NAMES = [
  '.ExecutionChainUpdated',
  '.App\\Events\\ExecutionChainUpdated',
] as const

export interface ChainChannelHandlers {
  onStep: (executionId: string, step: ChainStep) => void
}

export interface SchedulerChainSubscription {
  unsubscribe: () => void
}

function channelName(zoneId: number | string): string {
  return `hydro.zone.executions.${zoneId}`
}

/**
 * Подписывается на приватный канал зоны и ретранслирует события
 * `ExecutionChainUpdated` в колбэк `onStep`.
 *
 * Если Echo ещё не инициализирован (например, в SSR / unit-тесте без
 * browser-plugin-а) — возвращает no-op subscription. Все ошибки парсинга
 * события проглатываются и логируются: WS-поток никогда не должен ронять UI.
 */
export function subscribeToExecutionChain(
  zoneId: number | string,
  handlers: ChainChannelHandlers,
): SchedulerChainSubscription {
  const echo = getEcho()
  if (!echo) {
    logger.warn('subscribeToExecutionChain: echo instance unavailable, skipping', {
      zoneId,
    })
    return { unsubscribe: () => {} }
  }

  const name = channelName(zoneId)
  let channel: ReturnType<typeof echo.private> | null = null
  try {
    channel = echo.private(name)
  } catch (error) {
    logger.error('subscribeToExecutionChain: failed to attach to channel', {
      channel: name,
      error,
    })
    return { unsubscribe: () => {} }
  }

  const listener = (payload: unknown): void => {
    const parsed = chainUpdatedEventSchema.safeParse(payload)
    if (!parsed.success) {
      logger.warn('ExecutionChainUpdated payload failed schema validation', {
        issues: parsed.error.issues,
      })
      return
    }
    handlers.onStep(parsed.data.execution_id, parsed.data.step)
  }

  for (const eventName of EVENT_NAMES) {
    try {
      channel.listen(eventName, listener)
    } catch (error) {
      logger.warn('subscribeToExecutionChain: listen() failed', {
        eventName,
        error,
      })
    }
  }

  return {
    unsubscribe: () => {
      if (!channel) return
      try {
        for (const eventName of EVENT_NAMES) {
          try {
            channel.stopListening(eventName)
          } catch {
            /* ignore */
          }
        }
        echo.leave(name)
      } catch (error) {
        logger.warn('subscribeToExecutionChain: unsubscribe failed', {
          channel: name,
          error,
        })
      }
    },
  }
}
