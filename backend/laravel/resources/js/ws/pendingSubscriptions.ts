import { logger } from '@/utils/logger'
import type {
  ActiveSubscription,
  ChannelControl,
  ChannelKind,
  EchoLike,
  GlobalChannelRegistry,
  GlobalEventHandler,
  PendingSubscription,
  ZoneCommandHandler,
} from '@/ws/subscriptionTypes'
import type { ToastHandler } from '@/composables/useApi'

interface PendingSubscriptionsManagerDeps {
  pendingSubscriptions: Map<string, PendingSubscription>
  createSubscriptionId: () => string
  removeSubscription: (subscriptionId: string) => void
  isBrowser: () => boolean
  getEcho: () => EchoLike | null
  isGlobalChannel: (channelName: string) => boolean
  isChannelDead: (channelName: string) => boolean
  globalChannelRegistry: Map<string, GlobalChannelRegistry>
  ensureChannelControl: (
    channelName: string,
    kind: ChannelKind,
    channelType: 'private' | 'public'
  ) => ChannelControl | null
  createActiveSubscription: (
    channelName: string,
    kind: ChannelKind,
    handler: ZoneCommandHandler | GlobalEventHandler,
    componentTag: string,
    instanceId: number,
    showToast?: ToastHandler
  ) => ActiveSubscription
  addSubscription: (control: ChannelControl, subscription: ActiveSubscription) => void
}

export function createPendingSubscriptionsManager(deps: PendingSubscriptionsManagerDeps) {
  const processPendingSubscriptions = (): void => {
    if (!deps.isBrowser() || deps.pendingSubscriptions.size === 0) {
      return
    }

    const echo = deps.getEcho()
    if (!echo) {
      if (import.meta.env.MODE === 'test') {
        logger.debug('[useWebSocket] Test environment detected, skipping Echo wait')
        return
      }

      logger.debug('[useWebSocket] Echo still not available, keeping subscriptions pending', {
        pendingCount: deps.pendingSubscriptions.size,
      })
      return
    }

    logger.info('[useWebSocket] Processing pending subscriptions', {
      count: deps.pendingSubscriptions.size,
    })

    const toProcess = Array.from(deps.pendingSubscriptions.entries())

    toProcess.forEach(([subscriptionId, pending]) => {
      try {
        if (deps.isGlobalChannel(pending.channelName)) {
          const registry = deps.globalChannelRegistry.get(pending.channelName)
          if (
            registry &&
            registry.channelControl &&
            registry.channelControl.echoChannel &&
            !deps.isChannelDead(pending.channelName)
          ) {
            registry.handlers.add(pending.handler as GlobalEventHandler)
            registry.subscriptionRefCount += 1

            const subscription = deps.createActiveSubscription(
              pending.channelName,
              pending.kind,
              pending.handler,
              pending.componentTag,
              pending.instanceId,
              pending.showToast
            )
            subscription.id = pending.id

            deps.addSubscription(registry.channelControl, subscription)
            deps.pendingSubscriptions.delete(subscriptionId)

            logger.debug('[useWebSocket] Processed pending subscription (reused global channel)', {
              channel: pending.channelName,
              subscriptionId: pending.id,
              componentTag: pending.componentTag,
              refCount: registry.subscriptionRefCount,
            })
            return
          }
        }

        const control = deps.ensureChannelControl(
          pending.channelName,
          pending.kind,
          pending.channelType
        )
        if (!control || !control.echoChannel) {
          logger.warn('[useWebSocket] Failed to create channel for pending subscription, will retry', {
            channel: pending.channelName,
            subscriptionId: pending.id,
            reason: !control ? 'ensureChannelControl returned null' : 'echoChannel is null',
          })
          return
        }

        if (deps.isGlobalChannel(pending.channelName)) {
          const registry = deps.globalChannelRegistry.get(pending.channelName)
          if (registry) {
            registry.handlers.add(pending.handler as GlobalEventHandler)
            registry.subscriptionRefCount += 1
          }
        }

        const subscription = deps.createActiveSubscription(
          pending.channelName,
          pending.kind,
          pending.handler,
          pending.componentTag,
          pending.instanceId,
          pending.showToast
        )
        subscription.id = pending.id

        deps.addSubscription(control, subscription)
        deps.pendingSubscriptions.delete(subscriptionId)

        logger.debug('[useWebSocket] Processed pending subscription', {
          channel: pending.channelName,
          subscriptionId: pending.id,
          componentTag: pending.componentTag,
        })
      } catch (error) {
        logger.error('[useWebSocket] Error processing pending subscription, will retry', {
          channel: pending.channelName,
          subscriptionId: pending.id,
          error: error instanceof Error ? error.message : String(error),
        })
      }
    })
  }

  const createPendingSubscription = (
    channelName: string,
    kind: ChannelKind,
    channelType: 'private' | 'public',
    handler: ZoneCommandHandler | GlobalEventHandler,
    componentTag: string,
    instanceId: number,
    showToast?: ToastHandler
  ): (() => void) => {
    const subscriptionId = deps.createSubscriptionId()
    const pending: PendingSubscription = {
      id: subscriptionId,
      channelName,
      kind,
      channelType,
      handler,
      componentTag,
      instanceId,
      showToast,
    }

    deps.pendingSubscriptions.set(subscriptionId, pending)
    logger.debug('[useWebSocket] Echo not available, subscription queued', {
      channel: channelName,
      subscriptionId,
      componentTag,
    })

    setTimeout(() => {
      processPendingSubscriptions()
    }, 100)

    return () => {
      deps.pendingSubscriptions.delete(subscriptionId)
      deps.removeSubscription(subscriptionId)
    }
  }

  return {
    createPendingSubscription,
    processPendingSubscriptions,
  }
}
