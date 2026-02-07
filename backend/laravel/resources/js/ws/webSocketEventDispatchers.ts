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
  zoneId?: number | string
  zone_id?: number | string
  server_ts?: number | string | null
}

interface RawGlobalPayload extends WsEventPayload {
  id?: number | string
  eventId?: number | string
  event_id?: number | string
  kind?: string
  type?: string
  message?: string
  zoneId?: number | string
  zone_id?: number | string
  occurredAt?: string
  occurred_at?: string
  server_ts?: number | string | null
}

function asRecord(payload: unknown): WsEventPayload {
  if (payload && typeof payload === 'object') {
    return payload as WsEventPayload
  }

  return {}
}

function toOptionalNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : undefined
  }

  return undefined
}

function toServerTs(value: unknown): number | null | undefined {
  if (value === null) {
    return null
  }

  return toOptionalNumber(value)
}

function toRawCommandPayload(payload: WsEventPayload): RawCommandPayload {
  return asRecord(payload) as RawCommandPayload
}

function toRawGlobalPayload(payload: WsEventPayload): RawGlobalPayload {
  return asRecord(payload) as RawGlobalPayload
}

function resolveZoneId(channelName: string, payload: RawCommandPayload): number | undefined {
  const zoneIdMatch = channelName.match(/^commands\.(\d+)$/)
  if (zoneIdMatch) {
    return parseInt(zoneIdMatch[1], 10)
  }

  const payloadZoneId = payload?.zoneId ?? payload?.zone_id
  return toOptionalNumber(payloadZoneId)
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
  const kindValue = payload.kind ?? payload.type
  const messageValue = payload.message
  const occurredAt = payload.occurredAt ?? payload.occurred_at

  return {
    id: payload?.id ?? payload?.eventId ?? payload?.event_id,
    kind: typeof kindValue === 'string' ? kindValue : 'INFO',
    message: typeof messageValue === 'string' ? messageValue : '',
    zoneId,
    occurredAt: typeof occurredAt === 'string' ? occurredAt : new Date().toISOString(),
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

    const rawPayload = toRawCommandPayload(payload)
    const zoneId = resolveZoneId(channelName, rawPayload)
    const eventServerTs = toServerTs(rawPayload.server_ts)
    if (isStaleSnapshotEvent(zoneId, eventServerTs)) {
      const snapshotServerTs = typeof zoneId === 'number' ? getSnapshotServerTs(zoneId) : undefined
      logger.debug('[useWebSocket] Ignoring stale command event (reconciliation)', {
        channel: channelName,
        event_server_ts: eventServerTs,
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

    const rawPayload = toRawGlobalPayload(payload)
    const payloadZoneId = rawPayload.zoneId ?? rawPayload.zone_id
    const zoneId = toOptionalNumber(payloadZoneId)
    const eventServerTs = toServerTs(rawPayload.server_ts)

    if (isStaleSnapshotEvent(zoneId, eventServerTs)) {
      const snapshotServerTs = typeof zoneId === 'number' ? getSnapshotServerTs(zoneId) : undefined
      logger.debug('[useWebSocket] Ignoring stale global event (reconciliation)', {
        channel: channelName,
        event_server_ts: eventServerTs,
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
