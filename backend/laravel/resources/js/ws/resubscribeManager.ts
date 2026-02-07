import { logger } from '@/utils/logger'

interface ResubscribeManagerDeps {
  isBrowser: () => boolean
  resubscribeAllChannels: () => void
}

export function createResubscribeManager(deps: ResubscribeManagerDeps) {
  let resubscribeTimer: ReturnType<typeof setTimeout> | null = null
  let isResubscribing = false

  const scheduleResubscribe = (delay = 500): void => {
    if (!deps.isBrowser()) {
      return
    }

    if (isResubscribing) {
      logger.debug('[useWebSocket] Resubscribe already in progress, skipping', {})
      return
    }

    if (resubscribeTimer) {
      clearTimeout(resubscribeTimer)
    }

    resubscribeTimer = window.setTimeout(() => {
      resubscribeTimer = null
      if (!isResubscribing) {
        isResubscribing = true
        try {
          deps.resubscribeAllChannels()
        } finally {
          isResubscribing = false
        }
      }
    }, delay)
  }

  const reset = (): void => {
    if (resubscribeTimer) {
      clearTimeout(resubscribeTimer)
      resubscribeTimer = null
    }
    isResubscribing = false
  }

  return {
    scheduleResubscribe,
    reset,
  }
}
