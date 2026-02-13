import { logger } from '@/utils/logger'
import { registerSubscription, unregisterSubscription } from '@/ws/invariants'
import type {
  ActiveSubscription,
  ChannelControl,
  GlobalEventHandler,
  GlobalChannelRegistry,
} from './subscriptionTypes'

interface SubscriptionLifecycleDeps {
  activeSubscriptions: Map<string, ActiveSubscription>
  channelSubscribers: Map<string, Set<string>>
  channelControls: Map<string, ChannelControl>
  componentChannelCounts: Map<number, Map<string, number>>
  instanceSubscriptionSets: Map<number, Set<string>>
  globalChannelRegistry: Map<string, GlobalChannelRegistry>
  isGlobalChannel: (channelName: string) => boolean
  detachChannel: (control: ChannelControl, removeControl?: boolean) => void
}

function resolveEventName(kind: ActiveSubscription['kind']): string {
  return kind === 'zoneCommands'
    ? '.App\\Events\\CommandStatusUpdated'
    : '.App\\Events\\EventCreated'
}

export function createSubscriptionLifecycle(deps: SubscriptionLifecycleDeps) {
  const incrementComponentChannel = (instanceId: number, channelName: string): void => {
    let channelMap = deps.componentChannelCounts.get(instanceId)
    if (!channelMap) {
      channelMap = new Map()
      deps.componentChannelCounts.set(instanceId, channelMap)
    }
    channelMap.set(channelName, (channelMap.get(channelName) ?? 0) + 1)
    const instanceSet = deps.instanceSubscriptionSets.get(instanceId)
    instanceSet?.add(channelName)
  }

  const decrementComponentChannel = (instanceId: number, channelName: string): void => {
    const channelMap = deps.componentChannelCounts.get(instanceId)
    if (!channelMap) {
      return
    }

    const next = (channelMap.get(channelName) ?? 0) - 1
    if (next <= 0) {
      channelMap.delete(channelName)
      if (channelMap.size === 0) {
        deps.componentChannelCounts.delete(instanceId)
      }

      const instanceSet = deps.instanceSubscriptionSets.get(instanceId)
      if (instanceSet) {
        instanceSet.delete(channelName)
        if (instanceSet.size === 0) {
          deps.instanceSubscriptionSets.delete(instanceId)
        }
      }
      return
    }

    channelMap.set(channelName, next)
  }

  const addSubscription = (_control: ChannelControl, subscription: ActiveSubscription): void => {
    deps.activeSubscriptions.set(subscription.id, subscription)

    let channelSet = deps.channelSubscribers.get(subscription.channelName)
    if (!channelSet) {
      channelSet = new Set()
      deps.channelSubscribers.set(subscription.channelName, channelSet)
    }
    channelSet.add(subscription.id)

    incrementComponentChannel(subscription.instanceId, subscription.channelName)

    registerSubscription(
      subscription.channelName,
      subscription.id,
      resolveEventName(subscription.kind),
      subscription.componentTag
    )

    logger.debug('[useWebSocket] Added subscription', {
      channel: subscription.channelName,
      subscriptionId: subscription.id,
      componentTag: subscription.componentTag,
    })
  }

  const removeSubscription = (subscriptionId: string): void => {
    const subscription = deps.activeSubscriptions.get(subscriptionId)
    if (!subscription) {
      return
    }

    unregisterSubscription(
      subscription.channelName,
      subscriptionId,
      resolveEventName(subscription.kind)
    )

    if (deps.isGlobalChannel(subscription.channelName)) {
      const registry = deps.globalChannelRegistry.get(subscription.channelName)
      if (registry) {
        if (subscription.kind === 'globalEvents') {
          registry.handlers.delete(subscription.handler as GlobalEventHandler)
        }
        registry.subscriptionRefCount = Math.max(0, registry.subscriptionRefCount - 1)
      }
    }

    deps.activeSubscriptions.delete(subscriptionId)

    const channelSet = deps.channelSubscribers.get(subscription.channelName)
    if (channelSet) {
      channelSet.delete(subscriptionId)
      if (channelSet.size === 0) {
        deps.channelSubscribers.delete(subscription.channelName)
        const control = deps.channelControls.get(subscription.channelName)
        if (control) {
          if (!deps.isGlobalChannel(subscription.channelName)) {
            deps.detachChannel(control, false)
          } else {
            const registry = deps.globalChannelRegistry.get(subscription.channelName)
            if (registry && registry.subscriptionRefCount === 0) {
              registry.handlers.clear()
              deps.detachChannel(control, false)
              registry.isAuthorized = false
              logger.debug('[useWebSocket] Global channel kept in registry for reuse (ref-count=0)', {
                channel: subscription.channelName,
                hasActiveChannel: !!registry.channelControl?.echoChannel,
              })
            }
          }
        }
      }
    }

    decrementComponentChannel(subscription.instanceId, subscription.channelName)
    logger.debug('[useWebSocket] Removed subscription', {
      channel: subscription.channelName,
      subscriptionId,
      componentTag: subscription.componentTag,
      refCount: deps.isGlobalChannel(subscription.channelName)
        ? deps.globalChannelRegistry.get(subscription.channelName)?.subscriptionRefCount
        : undefined,
    })
  }

  const removeSubscriptionsByInstance = (instanceId: number): void => {
    const idsToRemove: string[] = []
    deps.activeSubscriptions.forEach((subscription, id) => {
      if (subscription.instanceId === instanceId) {
        idsToRemove.push(id)
      }
    })
    idsToRemove.forEach(id => removeSubscription(id))
  }

  return {
    addSubscription,
    removeSubscription,
    removeSubscriptionsByInstance,
  }
}
