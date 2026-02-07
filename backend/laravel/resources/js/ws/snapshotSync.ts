import { logger } from '@/utils/logger'
import type { SnapshotHandler, ZoneSnapshot } from '@/types/reconciliation'
import type { ActiveSubscription } from '@/ws/subscriptionTypes'

interface ApiClient {
  get<T = unknown>(url: string, config?: Record<string, unknown>): Promise<{ data?: T }>
}

interface SnapshotSyncDeps {
  getApiClient: () => ApiClient
  activeSubscriptions: Map<string, ActiveSubscription>
  isValidSnapshot: (snapshot: unknown) => boolean
  setZoneSnapshot: (zoneId: number, snapshot: ZoneSnapshot) => void
  getSnapshotHandler: (zoneId: number) => SnapshotHandler | undefined
  registerSnapshotHandler: (zoneId: number, handler: SnapshotHandler) => void
  getZoneSnapshot: (zoneId: number) => ZoneSnapshot | undefined
  hasZoneSnapshot: (zoneId: number) => boolean
}

function extractZoneIdFromChannel(channelName: string): number | null {
  const match = channelName.match(/^commands\.(\d+)$/)
  if (!match) return null
  return Number.parseInt(match[1], 10)
}

export function createSnapshotSync(deps: SnapshotSyncDeps) {
  const fetchAndApplySnapshot = async (zoneId: number): Promise<void> => {
    try {
      const api = deps.getApiClient()
      const response = await api.get<{ status: string; data: ZoneSnapshot }>(`/zones/${zoneId}/snapshot`)

      if (response.data?.status === 'ok' && response.data?.data) {
        const snapshot = response.data.data

        if (!deps.isValidSnapshot(snapshot)) {
          logger.warn('[useWebSocket] Invalid snapshot received, skipping', {
            zoneId,
            snapshot,
          })
          return
        }

        deps.setZoneSnapshot(zoneId, snapshot)

        logger.info('[useWebSocket] Snapshot fetched and stored', {
          zoneId,
          snapshot_id: snapshot.snapshot_id,
          server_ts: snapshot.server_ts,
        })

        const handler = deps.getSnapshotHandler(zoneId)
        if (handler) {
          try {
            await handler(snapshot)
          } catch (error) {
            logger.error('[useWebSocket] Error applying snapshot', {
              zoneId,
              error: error instanceof Error ? error.message : String(error),
            })
          }
        }
      }
    } catch (error) {
      logger.error('[useWebSocket] Failed to fetch snapshot', {
        zoneId,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  }

  const syncActiveZoneSnapshots = (): void => {
    const activeZoneIds = Array.from(
      new Set(
        Array.from(deps.activeSubscriptions.values())
          .filter((subscription) => subscription.kind === 'zoneCommands')
          .map((subscription) => extractZoneIdFromChannel(subscription.channelName))
          .filter((id): id is number => id !== null)
      )
    )

    activeZoneIds.forEach((zoneId) => {
      fetchAndApplySnapshot(zoneId).catch((error) => {
        logger.warn('[useWebSocket] Failed to fetch snapshot on reconnect', {
          zoneId,
          error: error instanceof Error ? error.message : String(error),
        })
      })
    })
  }

  const initializeZoneSnapshotSubscription = (zoneId: number, onSnapshot?: SnapshotHandler): void => {
    if (onSnapshot && typeof onSnapshot === 'function') {
      deps.registerSnapshotHandler(zoneId, onSnapshot)
    }

    if (!deps.hasZoneSnapshot(zoneId)) {
      fetchAndApplySnapshot(zoneId).catch((error) => {
        logger.warn('[useWebSocket] Failed to fetch initial snapshot', {
          zoneId,
          error: error instanceof Error ? error.message : String(error),
        })
      })
      return
    }

    const snapshot = deps.getZoneSnapshot(zoneId)
    if (snapshot && onSnapshot) {
      try {
        onSnapshot(snapshot)
      } catch (error) {
        logger.error('[useWebSocket] Error applying existing snapshot', {
          zoneId,
          error: error instanceof Error ? error.message : String(error),
        })
      }
    }
  }

  return {
    fetchAndApplySnapshot,
    syncActiveZoneSnapshots,
    initializeZoneSnapshotSubscription,
  }
}
