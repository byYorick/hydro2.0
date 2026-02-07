interface PendingSubscriptionMonitorDeps {
  getPendingSubscriptionsSize: () => number
  getEcho: () => unknown | null
  processPendingSubscriptions: () => void
  intervalMs?: number
}

interface PendingSubscriptionMonitor {
  start: () => void
  stop: () => void
}

export function createPendingSubscriptionMonitor({
  getPendingSubscriptionsSize,
  getEcho,
  processPendingSubscriptions,
  intervalMs = 1000,
}: PendingSubscriptionMonitorDeps): PendingSubscriptionMonitor {
  let intervalRef: ReturnType<typeof setInterval> | null = null

  const stop = (): void => {
    if (!intervalRef) {
      return
    }

    clearInterval(intervalRef)
    intervalRef = null
  }

  const start = (): void => {
    if (intervalRef) {
      return
    }

    intervalRef = setInterval(() => {
      if (getPendingSubscriptionsSize() === 0) {
        stop()
        return
      }

      if (getEcho()) {
        processPendingSubscriptions()
        if (getPendingSubscriptionsSize() === 0) {
          stop()
        }
      }
    }, intervalMs)
  }

  return {
    start,
    stop,
  }
}
