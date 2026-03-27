import { getEchoInstance, onWsStateChange } from '@/utils/echoClient'
import { logger } from '@/utils/logger'
import { registerSubscription, unregisterSubscription } from '@/ws/invariants'
import type { EchoChannelLike, EchoLike, WsEventPayload } from '@/ws/subscriptionTypes'

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

export function subscribeManagedChannelEvents({
  channelName,
  eventHandlers,
  channelType = 'private',
  componentTag = 'managed-ws-channel',
  leaveOnCleanup = false,
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

  let channel: EchoChannelLike | null = null
  let listenerRefs: Record<string, (payload: WsEventPayload) => void> = {}
  let unsubscribeWsState: (() => void) | null = null
  let stopped = false

  const cleanupChannel = (): void => {
    if (channel) {
      Object.entries(listenerRefs).forEach(([eventName, handler]) => {
        try {
          channel?.stopListening(eventName, handler)
        } catch (error) {
          logger.warn('[managedChannelEvents] Failed to stop listening', {
            channel: channelName,
            event: eventName,
            componentTag,
            error: error instanceof Error ? error.message : String(error),
          })
        }
      })
    }

    if (leaveOnCleanup) {
      try {
        getEchoInstance()?.leave?.(channelName)
      } catch (error) {
        logger.warn('[managedChannelEvents] Failed to leave channel', {
          channel: channelName,
          componentTag,
          error: error instanceof Error ? error.message : String(error),
        })
      }
    }

    channel = null
    listenerRefs = {}
  }

  const subscribeChannel = (): void => {
    if (stopped) {
      return
    }

    const echo = (getEchoInstance() || (typeof window !== 'undefined' ? window.Echo : null)) as EchoLike | null
    if (!echo) {
      logger.debug('[managedChannelEvents] Echo not available, waiting for connect', {
        channel: channelName,
        componentTag,
      })
      return
    }

    cleanupChannel()

    try {
      channel = channelType === 'private' ? echo.private(channelName) : echo.channel(channelName)
      listenerRefs = {}

      eventEntries.forEach(([eventName, handler]) => {
        const listener = (payload: WsEventPayload) => {
          if (stopped) {
            return
          }

          try {
            handler(toRecord(payload))
          } catch (error) {
            logger.error('[managedChannelEvents] Event handler failed', {
              channel: channelName,
              event: eventName,
              componentTag,
            }, error)
          }
        }

        listenerRefs[eventName] = listener
        channel?.listen(eventName, listener)
      })

      logger.debug('[managedChannelEvents] Subscribed channel events', {
        channel: channelName,
        componentTag,
        events: eventEntries.map(([eventName]) => eventName),
      })
    } catch (error) {
      logger.warn('[managedChannelEvents] Failed to subscribe channel events', {
        channel: channelName,
        componentTag,
        error: error instanceof Error ? error.message : String(error),
      })
      cleanupChannel()
    }
  }

  subscribeChannel()

  unsubscribeWsState = onWsStateChange((state) => {
    if (stopped) {
      return
    }

    if (state === 'connected') {
      subscribeChannel()
      return
    }

    if (state === 'disconnected' || state === 'unavailable' || state === 'failed') {
      cleanupChannel()
    }
  })

  return () => {
    stopped = true
    unsubscribeWsState?.()
    unsubscribeWsState = null
    cleanupChannel()

    subscriptionIds.forEach((subscriptionId, eventName) => {
      unregisterSubscription(channelName, subscriptionId, eventName)
    })
  }
}
