import { logger } from '@/utils/logger'
import {
  getSnapshotServerTs,
  isStaleSnapshotEvent,
} from '@/ws/snapshotRegistry'
import type {
  ActiveSubscription,
  AlertCreatedHandler,
  GlobalEventHandler,
  ZoneUpdateHandler,
  ZoneCommandHandler,
  WsEventPayload,
} from '@/ws/subscriptionTypes'
import type { CommandStatus } from '@/types'
import type { Zone } from '@/types/Zone'
import type { Alert } from '@/types/Alert'

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

interface RawZonePayload extends WsEventPayload {
  zone?: Zone | null
  id?: number | string
  name?: string
  status?: string
  server_ts?: number | string | null
}

interface RawAlertPayload extends WsEventPayload {
  alert?: Alert | null
  id?: number | string
  code?: string
  severity?: string
  status?: string
  zoneId?: number | string
  zone_id?: number | string
  message?: string
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

function toRawZonePayload(payload: WsEventPayload): RawZonePayload {
  return asRecord(payload) as RawZonePayload
}

function toRawAlertPayload(payload: WsEventPayload): RawAlertPayload {
  return asRecord(payload) as RawAlertPayload
}

function resolveZoneId(channelName: string, payload: RawCommandPayload): number | undefined {
  const zoneIdMatch = channelName.match(/^hydro\.commands\.(\d+)$/)
  if (zoneIdMatch) {
    return parseInt(zoneIdMatch[1], 10)
  }

  const payloadZoneId = payload?.zoneId ?? payload?.zone_id
  return toOptionalNumber(payloadZoneId)
}

function resolveZoneUpdateId(channelName: string, payload: RawZonePayload): number | undefined {
  const zoneIdMatch = channelName.match(/^hydro\.zones\.(\d+)$/)
  if (zoneIdMatch) {
    return parseInt(zoneIdMatch[1], 10)
  }

  const payloadZoneId = payload?.zone?.id ?? payload?.id
  return toOptionalNumber(payloadZoneId)
}

function resolveAlertZoneId(payload: RawAlertPayload): number | undefined {
  const payloadZoneId = payload?.alert?.zone_id ?? payload?.zoneId ?? payload?.zone_id
  return toOptionalNumber(payloadZoneId)
}

function normalizeCommandPayload(
  payload: RawCommandPayload,
  zoneId: number | undefined,
  isFailure: boolean
): {
  commandId: number | string | undefined
  status: CommandStatus
  message: string | undefined
  error: string | undefined
  zoneId: number | undefined
} {
  const rawStatus = isFailure ? (payload.status ?? 'ERROR') : (payload.status ?? 'UNKNOWN')
  return {
    commandId: payload?.commandId ?? payload?.command_id,
    status: normalizeCommandStatus(rawStatus),
    message: typeof payload.message === 'string' ? payload.message : undefined,
    error: typeof payload.error === 'string' ? payload.error : undefined,
    zoneId,
  }
}

function normalizeCommandStatus(status: unknown): CommandStatus {
  const normalized = String(status ?? 'UNKNOWN').toUpperCase()
  if ([
    'QUEUED',
    'SENT',
    'ACK',
    'DONE',
    'NO_EFFECT',
    'ERROR',
    'INVALID',
    'BUSY',
    'TIMEOUT',
    'SEND_FAILED',
  ].includes(normalized)) {
    return normalized as CommandStatus
  }

  return 'UNKNOWN'
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

function normalizeZonePayload(payload: RawZonePayload, zoneId: number | undefined): Zone | undefined {
  const zonePayload = payload.zone
  if (zonePayload && typeof zonePayload === 'object') {
    return zonePayload
  }

  const normalizedZoneId = zoneId ?? toOptionalNumber(payload.id)
  if (typeof normalizedZoneId !== 'number') {
    return undefined
  }

  return {
    id: normalizedZoneId,
    name: typeof payload.name === 'string' ? payload.name : undefined,
    status: typeof payload.status === 'string' ? payload.status : undefined,
  } as Zone
}

function normalizeAlertPayload(payload: RawAlertPayload): Alert | undefined {
  const alertPayload = payload.alert
  if (alertPayload && typeof alertPayload === 'object') {
    return alertPayload
  }

  const alertId = payload.id
  if (typeof alertId !== 'number' && typeof alertId !== 'string') {
    return undefined
  }

  return {
    id: alertId,
    code: typeof payload.code === 'string' ? payload.code : '',
    severity: typeof payload.severity === 'string' ? payload.severity : 'info',
    status: typeof payload.status === 'string' ? payload.status : 'active',
    zone_id: toOptionalNumber(payload.zoneId ?? payload.zone_id),
    message: typeof payload.message === 'string' ? payload.message : '',
  } as Alert
}

export function createWebSocketEventDispatchers({
  activeSubscriptions,
  channelSubscribers,
}: WebSocketEventDispatcherDeps): {
  handleCommandEvent: (channelName: string, payload: WsEventPayload, isFailure: boolean) => void
  handleGlobalEvent: (channelName: string, payload: WsEventPayload) => void
  handleZoneUpdateEvent: (channelName: string, payload: WsEventPayload) => void
  handleAlertEvent: (channelName: string, payload: WsEventPayload) => void
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
    if (typeof normalized.commandId !== 'number' && typeof normalized.commandId !== 'string') {
      logger.warn('[useWebSocket] Ignoring command event without commandId', {
        channel: channelName,
        zoneId,
        status: normalized.status,
      })
      return
    }

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

  const handleZoneUpdateEvent = (channelName: string, payload: WsEventPayload): void => {
    const channelSet = channelSubscribers.get(channelName)
    if (!channelSet) {
      return
    }

    const rawPayload = toRawZonePayload(payload)
    const zoneId = resolveZoneUpdateId(channelName, rawPayload)
    const eventServerTs = toServerTs(rawPayload.server_ts)

    if (isStaleSnapshotEvent(zoneId, eventServerTs)) {
      const snapshotServerTs = typeof zoneId === 'number' ? getSnapshotServerTs(zoneId) : undefined
      logger.debug('[useWebSocket] Ignoring stale zone update event (reconciliation)', {
        channel: channelName,
        event_server_ts: eventServerTs,
        snapshot_server_ts: snapshotServerTs,
      })
      return
    }

    const normalized = normalizeZonePayload(rawPayload, zoneId)
    if (!normalized) {
      logger.warn('[useWebSocket] Ignoring zone update event without zone payload', {
        channel: channelName,
      })
      return
    }

    channelSet.forEach(subscriptionId => {
      const subscription = activeSubscriptions.get(subscriptionId)
      if (!subscription || subscription.kind !== 'zoneUpdates') {
        return
      }

      try {
        (subscription.handler as ZoneUpdateHandler)(normalized)
      } catch (error) {
        logger.error('[useWebSocket] Zone update handler error', {
          channel: channelName,
          componentTag: subscription.componentTag,
        }, error)
      }
    })
  }

  const handleAlertEvent = (channelName: string, payload: WsEventPayload): void => {
    const channelSet = channelSubscribers.get(channelName)
    if (!channelSet) {
      return
    }

    const rawPayload = toRawAlertPayload(payload)
    const zoneId = resolveAlertZoneId(rawPayload)
    const eventServerTs = toServerTs(rawPayload.server_ts)

    if (isStaleSnapshotEvent(zoneId, eventServerTs)) {
      const snapshotServerTs = typeof zoneId === 'number' ? getSnapshotServerTs(zoneId) : undefined
      logger.debug('[useWebSocket] Ignoring stale alert event (reconciliation)', {
        channel: channelName,
        event_server_ts: eventServerTs,
        snapshot_server_ts: snapshotServerTs,
      })
      return
    }

    const normalized = normalizeAlertPayload(rawPayload)
    if (!normalized) {
      logger.warn('[useWebSocket] Ignoring alert event without alert payload', {
        channel: channelName,
      })
      return
    }

    channelSet.forEach(subscriptionId => {
      const subscription = activeSubscriptions.get(subscriptionId)
      if (!subscription || subscription.kind !== 'alerts') {
        return
      }

      try {
        (subscription.handler as AlertCreatedHandler)(normalized)
      } catch (error) {
        logger.error('[useWebSocket] Alert handler error', {
          channel: channelName,
          componentTag: subscription.componentTag,
        }, error)
      }
    })
  }

  return {
    handleCommandEvent,
    handleGlobalEvent,
    handleZoneUpdateEvent,
    handleAlertEvent,
  }
}
