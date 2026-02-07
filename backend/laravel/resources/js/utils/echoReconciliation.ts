import { logger } from './logger'
import apiClient from './apiClient'

interface ReconciliationPayload {
  telemetry: unknown[]
  commands: unknown[]
  alerts: unknown[]
  timestamp?: string
}

interface EchoReconciliationDeps {
  getApiUrl: () => string
  dispatchReconciliation: (payload: ReconciliationPayload) => void
}

export function createEchoReconciliation(deps: EchoReconciliationDeps) {
  let lastSyncTimestamp: number | null = null
  let isSyncing = false

  const performReconciliation = async (): Promise<void> => {
    if (isSyncing) {
      logger.debug('[echoClient] Reconciliation already in progress, skipping')
      return
    }

    const now = Date.now()
    const MIN_SYNC_INTERVAL = 5000
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

      const response = await apiClient.get(`${deps.getApiUrl()}/sync/full`, {
        timeout: 10000,
      })

      if (response.data?.status === 'ok' && response.data?.data) {
        const { telemetry, commands, alerts } = response.data.data

        logger.info('[echoClient] Reconciliation completed', {
          telemetryCount: telemetry?.length || 0,
          commandsCount: commands?.length || 0,
          alertsCount: alerts?.length || 0,
          timestamp: response.data.timestamp,
        })

        deps.dispatchReconciliation({
          telemetry: telemetry || [],
          commands: commands || [],
          alerts: alerts || [],
          timestamp: response.data.timestamp,
        })
      } else {
        logger.warn('[echoClient] Reconciliation failed: invalid response format', {
          status: response.data?.status,
        })
      }
    } catch (error) {
      logger.error('[echoClient] Reconciliation failed', {
        error: error instanceof Error ? error.message : String(error),
      })
    } finally {
      isSyncing = false
    }
  }

  const reset = (): void => {
    lastSyncTimestamp = null
    isSyncing = false
  }

  return {
    performReconciliation,
    reset,
  }
}
