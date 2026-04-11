import { onWsStateChange } from '@/utils/echoClient'
import { logger } from '@/utils/logger'
import { registerSubscription, unregisterSubscription } from '@/ws/invariants'
import { getSnapshotServerTs, isStaleSnapshotEvent } from '@/ws/snapshotRegistry'
import {
  ensureOwnedSharedEchoChannel,
  getSharedEchoChannel,
  releaseOwnedSharedEchoChannel,
} from '@/ws/sharedEchoChannels'
import type { WsEventPayload } from '@/ws/subscriptionTypes'

function toRecord(payload: unknown): WsEventPayload {
  if (payload && typeof payload === 'object') {
    return payload as WsEventPayload
  }

  return {}
}

interface ManagedChannelEventsOptions {
  channelName: string
  eventHandlers: Record<string, (payload: WsEventPayload) => void>
  channelType?: 'private' | 'public'
  componentTag?: string
  leaveOnCleanup?: boolean
}

interface ManagedChannelSubscription {
  subscriptionId: string
  ownerId: string
  channelName: string
  channelType: 'private' | 'public'
  componentTag: string
  eventHandlers: Record<string, (payload: WsEventPayload) => void>
  listenerRefs: Record<string, (payload: WsEventPayload) => void>
  lastAcceptedServerTsByEvent: Map<string, number>
  leaveOnCleanup: boolean
}

const managedSubscriptions = new Map<string, ManagedChannelSubscription>()
let unsubscribeWsState: (() => void) | null = null

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

function toServerTs(payload: WsEventPayload): number | null | undefined {
  const value = payload.server_ts
  if (value === null) {
    return null
  }

  return toOptionalNumber(value)
}

function asNestedRecord(value: unknown): WsEventPayload | null {
  if (value && typeof value === 'object') {
    return value as WsEventPayload
  }

  return null
}

function resolveZoneId(channelName: string, payload: WsEventPayload): number | undefined {
  const zoneChannelMatch = channelName.match(/^hydro\.(?:zones|commands)\.(\d+)$/)
  if (zoneChannelMatch) {
    return Number.parseInt(zoneChannelMatch[1], 10)
  }

  const directZoneId = toOptionalNumber(payload.zoneId ?? payload.zone_id)
  if (typeof directZoneId === 'number') {
    return directZoneId
  }

  const zoneRecord = asNestedRecord(payload.zone)
  const zoneObjectId = toOptionalNumber(zoneRecord?.id)
  if (typeof zoneObjectId === 'number') {
    return zoneObjectId
  }

  const deviceRecord = asNestedRecord(payload.device)
  const deviceZoneId = toOptionalNumber(deviceRecord?.zone_id ?? deviceRecord?.zoneId)
  if (typeof deviceZoneId === 'number') {
    return deviceZoneId
  }

  const cycleRecord = asNestedRecord(payload.cycle)
  return toOptionalNumber(cycleRecord?.zone_id ?? cycleRecord?.zoneId)
}

function clearListenerRefs(subscription: ManagedChannelSubscription): void {
  subscription.listenerRefs = {}
}

function detachSubscriptionListeners(subscription: ManagedChannelSubscription): void {
  const channel = getSharedEchoChannel(subscription.channelName, subscription.channelType)
  if (!channel) {
    clearListenerRefs(subscription)
    return
  }

  Object.entries(subscription.listenerRefs).forEach(([eventName, handler]) => {
    try {
      channel.stopListening(eventName, handler)
    } catch (error) {
      logger.warn('[managedChannelEvents] Failed to stop listening', {
        channel: subscription.channelName,
        event: eventName,
        componentTag: subscription.componentTag,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  })

  clearListenerRefs(subscription)
}

function createManagedListener(
  subscription: ManagedChannelSubscription,
  eventName: string,
  handler: (payload: WsEventPayload) => void
): (payload: WsEventPayload) => void {
  return (payload: WsEventPayload) => {
    if (!managedSubscriptions.has(subscription.subscriptionId)) {
      return
    }

    const normalizedPayload = toRecord(payload)
    const zoneId = resolveZoneId(subscription.channelName, normalizedPayload)
    const eventServerTs = toServerTs(normalizedPayload)

    if (isStaleSnapshotEvent(zoneId, eventServerTs)) {
      const snapshotServerTs = typeof zoneId === 'number' ? getSnapshotServerTs(zoneId) : undefined
      logger.debug('[managedChannelEvents] Ignoring stale raw event', {
        channel: subscription.channelName,
        event: eventName,
        componentTag: subscription.componentTag,
        event_server_ts: eventServerTs,
        snapshot_server_ts: snapshotServerTs,
        zoneId,
      })
      return
    }

    const lastAcceptedServerTs = subscription.lastAcceptedServerTsByEvent.get(eventName)
    if (
      typeof eventServerTs === 'number' &&
      typeof lastAcceptedServerTs === 'number' &&
      eventServerTs <= lastAcceptedServerTs
    ) {
      logger.debug('[managedChannelEvents] Ignoring non-monotonic raw event', {
        channel: subscription.channelName,
        event: eventName,
        componentTag: subscription.componentTag,
        event_server_ts: eventServerTs,
        last_accepted_server_ts: lastAcceptedServerTs,
      })
      return
    }

    try {
      handler(normalizedPayload)
      if (typeof eventServerTs === 'number') {
        subscription.lastAcceptedServerTsByEvent.set(eventName, eventServerTs)
      }
    } catch (error) {
      logger.error('[managedChannelEvents] Event handler failed', {
        channel: subscription.channelName,
        event: eventName,
        componentTag: subscription.componentTag,
      }, error)
    }
  }
}

function attachSubscriptionListeners(subscription: ManagedChannelSubscription): void {
  const channel = ensureOwnedSharedEchoChannel(
    subscription.channelName,
    subscription.channelType,
    subscription.ownerId
  )
  if (!channel) {
    logger.debug('[managedChannelEvents] Channel not available yet', {
      channel: subscription.channelName,
      componentTag: subscription.componentTag,
    })
    return
  }

  Object.entries(subscription.eventHandlers).forEach(([eventName, handler]) => {
    if (subscription.listenerRefs[eventName]) {
      return
    }

    const listener = createManagedListener(subscription, eventName, handler)
    subscription.listenerRefs[eventName] = listener
    channel.listen(eventName, listener)
  })
}

function ensureManagedWsListener(): void {
  if (unsubscribeWsState) {
    return
  }

  unsubscribeWsState = onWsStateChange((state) => {
    if (managedSubscriptions.size === 0) {
      return
    }

    if (state === 'connected') {
      managedSubscriptions.forEach((subscription) => {
        attachSubscriptionListeners(subscription)
      })
      return
    }

    if (state === 'disconnected' || state === 'unavailable' || state === 'failed') {
      managedSubscriptions.forEach((subscription) => {
        detachSubscriptionListeners(subscription)
      })
    }
  })
}

function cleanupManagedWsListenerIfIdle(): void {
  if (managedSubscriptions.size > 0 || !unsubscribeWsState) {
    return
  }

  unsubscribeWsState()
  unsubscribeWsState = null
}

export function __resetManagedChannelEventsForTests(): void {
  managedSubscriptions.forEach((subscription) => {
    releaseOwnedSharedEchoChannel(
      subscription.channelName,
      subscription.channelType,
      subscription.ownerId,
      false
    )
  })
  managedSubscriptions.clear()
  cleanupManagedWsListenerIfIdle()
}

export function subscribeManagedChannelEvents({
  channelName,
  eventHandlers,
  channelType = 'private',
  componentTag = 'managed-ws-channel',
  leaveOnCleanup = true,
}: ManagedChannelEventsOptions): () => void {
  const eventEntries = Object.entries(eventHandlers)
  if (eventEntries.length === 0) {
    logger.warn('[managedChannelEvents] Missing event handlers', {
      channel: channelName,
      componentTag,
    })
    return () => undefined
  }

  const subscriptionIds = new Map<string, string>()
  const subscriptionNonce = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  eventEntries.forEach(([eventName], index) => {
    const subscriptionId = `${componentTag}:${channelName}:${eventName}:${subscriptionNonce}:${index}`
    subscriptionIds.set(eventName, subscriptionId)
    registerSubscription(channelName, subscriptionId, eventName, componentTag)
  })

  const primarySubscriptionId = subscriptionIds.values().next().value as string
  const subscription: ManagedChannelSubscription = {
    subscriptionId: primarySubscriptionId,
    ownerId: `managed:${primarySubscriptionId}`,
    channelName,
    channelType,
    componentTag,
    eventHandlers,
    listenerRefs: {},
    lastAcceptedServerTsByEvent: new Map(),
    leaveOnCleanup,
  }

  ensureManagedWsListener()
  managedSubscriptions.set(primarySubscriptionId, subscription)
  attachSubscriptionListeners(subscription)

  return () => {
    const activeSubscription = managedSubscriptions.get(primarySubscriptionId)
    if (activeSubscription) {
      detachSubscriptionListeners(activeSubscription)
      releaseOwnedSharedEchoChannel(
        activeSubscription.channelName,
        activeSubscription.channelType,
        activeSubscription.ownerId,
        activeSubscription.leaveOnCleanup
      )
      managedSubscriptions.delete(primarySubscriptionId)
    }

    subscriptionIds.forEach((subscriptionId, eventName) => {
      unregisterSubscription(channelName, subscriptionId, eventName)
    })

    cleanupManagedWsListenerIfIdle()
  }
}
