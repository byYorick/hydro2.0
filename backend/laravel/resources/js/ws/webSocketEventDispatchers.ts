import { logger } from '@/utils/logger'
import {
  getSnapshotServerTs,
  isStaleSnapshotEvent,
} from '@/ws/snapshotRegistry'
import type {
  ActiveSubscription,
  GlobalEventHandler,
  ZoneCommandHandler,
  WsEventPayload,
} from '@/ws/subscriptionTypes'

interface WebSocketEventDispatcherDeps {
  activeSubscriptions: Map<string, ActiveSubscription>
  channelSubscribers: Map<string, Set<string>>
}

interface RawCommandPayload extends WsEventPayload {
  commandId?: number | string
  command_id?: number | string
  status?: string
  message?: string
  error?: string
  zoneId?: number
  zone_id?: number
  server_ts?: number
}

interface RawGlobalPayload extends WsEventPayload {
  id?: number | string
  eventId?: number | string
  event_id?: number | string
  kind?: string
  type?: string
  message?: string
  zoneId?: number
  zone_id?: number
  occurredAt?: string
  occurred_at?: string
  server_ts?: number
}

function asRecord(payload: unknown): WsEventPayload {
  if (payload && typeof payload === 'object') {
    return payload as WsEventPayload
  }

  return {}
}

function resolveZoneId(channelName: string, payload: RawCommandPayload): number | undefined {
  const zoneIdMatch = channelName.match(/^commands\.(\d+)$/)
  if (zoneIdMatch) {
    return parseInt(zoneIdMatch[1], 10)
  }

  const payloadZoneId = payload?.zoneId ?? payload?.zone_id
  return typeof payloadZoneId === 'number' ? payloadZoneId : undefined
}

function normalizeCommandPayload(
  payload: RawCommandPayload,
  zoneId: number | undefined,
  isFailure: boolean
): {
  commandId: number | string | undefined
  status: string
  message: string | undefined
  error: string | undefined
  zoneId: number | undefined
} {
  return {
    commandId: payload?.commandId ?? payload?.command_id,
    status: isFailure ? (payload.status ?? 'ERROR') : (payload.status ?? 'UNKNOWN'),
    message: typeof payload.message === 'string' ? payload.message : undefined,
    error: typeof payload.error === 'string' ? payload.error : undefined,
    zoneId,
  }
}

function normalizeGlobalPayload(payload: RawGlobalPayload, zoneId: number | undefined): {
  id: number | string | undefined
  kind: string
  message: string
  zoneId: number | undefined
  occurredAt: string
} {
  return {
    id: payload?.id ?? payload?.eventId ?? payload?.event_id,
    kind: payload.kind ?? payload.type ?? 'INFO',
    message: payload.message ?? '',
    zoneId,
    occurredAt: payload.occurredAt ?? payload.occurred_at ?? new Date().toISOString(),
  }
}

export function createWebSocketEventDispatchers({
  activeSubscriptions,
  channelSubscribers,
}: WebSocketEventDispatcherDeps): {
  handleCommandEvent: (channelName: string, payload: WsEventPayload, isFailure: boolean) => void
  handleGlobalEvent: (channelName: string, payload: WsEventPayload) => void
} {
  const handleCommandEvent = (channelName: string, payload: WsEventPayload, isFailure: boolean): void => {
    const channelSet = channelSubscribers.get(channelName)
    if (!channelSet) {
      return
    }

    const rawPayload = payload as RawCommandPayload
    const zoneId = resolveZoneId(channelName, rawPayload)
    if (isStaleSnapshotEvent(zoneId, rawPayload.server_ts)) {
      const snapshotServerTs = typeof zoneId === 'number' ? getSnapshotServerTs(zoneId) : undefined
      logger.debug('[useWebSocket] Ignoring stale command event (reconciliation)', {
        channel: channelName,
        event_server_ts: rawPayload.server_ts,
        snapshot_server_ts: snapshotServerTs,
        commandId: rawPayload.commandId ?? rawPayload.command_id,
      })
      return
    }

    const normalized = normalizeCommandPayload(rawPayload, zoneId, isFailure)

    channelSet.forEach(subscriptionId => {
      const subscription = activeSubscriptions.get(subscriptionId)
      if (!subscription || subscription.kind !== 'zoneCommands') {
        return
      }

      try {
        (subscription.handler as ZoneCommandHandler)(normalized)
      } catch (error) {
        logger.error('[useWebSocket] Zone command handler error', {
          channel: channelName,
          componentTag: subscription.componentTag,
        }, error)
      }

      if (isFailure && subscription.showToast) {
        subscription.showToast(
          `Команда завершилась с ошибкой: ${normalized.message || 'Ошибка'}`,
          'error',
          5000
        )
      }
    })
  }

  const handleGlobalEvent = (channelName: string, payload: WsEventPayload): void => {
    const channelSet = channelSubscribers.get(channelName)
    if (!channelSet) {
      return
    }

    const rawPayload = asRecord(payload) as RawGlobalPayload
    const payloadZoneId = rawPayload.zoneId ?? rawPayload.zone_id
    const zoneId = typeof payloadZoneId === 'number' ? payloadZoneId : undefined

    if (isStaleSnapshotEvent(zoneId, rawPayload.server_ts)) {
      const snapshotServerTs = typeof zoneId === 'number' ? getSnapshotServerTs(zoneId) : undefined
      logger.debug('[useWebSocket] Ignoring stale global event (reconciliation)', {
        channel: channelName,
        event_server_ts: rawPayload.server_ts,
        snapshot_server_ts: snapshotServerTs,
        eventId: rawPayload.id ?? rawPayload.eventId ?? rawPayload.event_id,
      })
      return
    }

    const normalized = normalizeGlobalPayload(rawPayload, zoneId)
    channelSet.forEach(subscriptionId => {
      const subscription = activeSubscriptions.get(subscriptionId)
      if (!subscription || subscription.kind !== 'globalEvents') {
        return
      }

      try {
        (subscription.handler as GlobalEventHandler)(normalized)
      } catch (error) {
        logger.error('[useWebSocket] Global event handler error', {
          channel: channelName,
          componentTag: subscription.componentTag,
        }, error)
      }
    })
  }

  return {
    handleCommandEvent,
    handleGlobalEvent,
  }
}
