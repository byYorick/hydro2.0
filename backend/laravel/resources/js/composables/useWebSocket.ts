import { ref } from 'vue'
import { logger } from '@/utils/logger'
import type { ToastHandler } from './useApi'
import { useApi } from './useApi'
import { onWsStateChange } from '@/utils/echoClient'
import type { SnapshotHandler } from '@/types/reconciliation'
import { isValidSnapshot } from '@/types/reconciliation'
import {
  createSubscriptionLifecycle,
} from '@/ws/subscriptionLifecycle'
import type {
  ActiveSubscription,
  ChannelControl,
  ChannelKind,
  GlobalChannelRegistry,
  GlobalEventHandler,
  PendingSubscription,
  ZoneCommandHandler,
} from '@/ws/subscriptionTypes'
import {
  clearSnapshotRegistry,
  getSnapshotHandler,
  getZoneSnapshot,
  hasZoneSnapshot,
  registerSnapshotHandler,
  removeSnapshotHandler,
  setZoneSnapshot,
} from '@/ws/snapshotRegistry'
import { createPendingSubscriptionsManager } from '@/ws/pendingSubscriptions'
import { createPendingSubscriptionMonitor } from '@/ws/pendingSubscriptionMonitor'
import { createResubscribeManager } from '@/ws/resubscribeManager'
import { createSnapshotSync } from '@/ws/snapshotSync'
import { createChannelControlManager } from '@/ws/channelControlManager'
import { createWebSocketEventDispatchers } from '@/ws/webSocketEventDispatchers'
import {
  ensureEchoAvailable,
  getAvailableEcho,
  GLOBAL_EVENTS_CHANNEL,
  isBrowser,
  isGlobalChannel,
  isWsEnabled,
} from '@/ws/webSocketRuntime'

const activeSubscriptions = new Map<string, ActiveSubscription>()
const channelSubscribers = new Map<string, Set<string>>()
const channelControls = new Map<string, ChannelControl>()
const componentChannelCounts = new Map<number, Map<string, number>>()
const instanceSubscriptionSets = new Map<number, Set<string>>()

const globalChannelRegistry = new Map<string, GlobalChannelRegistry>()

const pendingSubscriptions = new Map<string, PendingSubscription>()

let subscriptionCounter = 0
let componentCounter = 0

function createSubscriptionId(): string {
  subscriptionCounter += 1
  return `sub-${subscriptionCounter}`
}

// Вспомогательная функция для создания активной подписки
function createActiveSubscription(
  channelName: string,
  kind: ChannelKind,
  handler: ZoneCommandHandler | GlobalEventHandler,
  componentTag: string,
  instanceId: number,
  showToast?: ToastHandler
): ActiveSubscription {
  return {
    id: createSubscriptionId(),
    channelName,
    kind,
    handler,
    componentTag,
    showToast,
    instanceId,
  }
}

const {
  handleCommandEvent,
  handleGlobalEvent,
} = createWebSocketEventDispatchers({
  activeSubscriptions,
  channelSubscribers,
})

const channelControlManager = createChannelControlManager({
  isBrowser,
  getEcho: () => {
    if (!isBrowser()) {
      return null
    }
    return window.Echo
  },
  isGlobalChannel,
  channelControls,
  globalChannelRegistry,
  onCommandEvent: handleCommandEvent,
  onGlobalEvent: handleGlobalEvent,
})

const {
  addSubscription,
  removeSubscription,
  removeSubscriptionsByInstance,
} = createSubscriptionLifecycle({
  activeSubscriptions,
  channelSubscribers,
  channelControls,
  componentChannelCounts,
  instanceSubscriptionSets,
  globalChannelRegistry,
  isGlobalChannel,
  detachChannel: channelControlManager.detachChannel,
})

const pendingSubscriptionsManager = createPendingSubscriptionsManager({
  pendingSubscriptions,
  createSubscriptionId,
  removeSubscription,
  isBrowser,
  getEcho: getAvailableEcho,
  isGlobalChannel,
  isChannelDead: channelControlManager.isChannelDead,
  globalChannelRegistry,
  ensureChannelControl: channelControlManager.ensureChannelControl,
  createActiveSubscription,
  addSubscription,
})

const snapshotSync = createSnapshotSync({
  getApiClient: () => useApi().api,
  activeSubscriptions,
  isValidSnapshot,
  setZoneSnapshot,
  getSnapshotHandler,
  registerSnapshotHandler,
  getZoneSnapshot,
  hasZoneSnapshot,
})

const resubscribeManager = createResubscribeManager({
  isBrowser,
  resubscribeAllChannels: channelControlManager.resubscribeAllChannels,
})

const pendingSubscriptionMonitor = createPendingSubscriptionMonitor({
  getPendingSubscriptionsSize: () => pendingSubscriptions.size,
  getEcho: getAvailableEcho,
  processPendingSubscriptions: pendingSubscriptionsManager.processPendingSubscriptions,
})

if (isBrowser()) {
  try {
    onWsStateChange(state => {
      if (state === 'connected') {
        resubscribeManager.scheduleResubscribe()
        // Обрабатываем отложенные подписки при подключении
        pendingSubscriptionsManager.processPendingSubscriptions()
        snapshotSync.syncActiveZoneSnapshots()
      }
    })
  } catch {
    // ignore registration errors
  }

  pendingSubscriptionMonitor.start()

  // Очистка при HMR
  if (import.meta.hot) {
    import.meta.hot.dispose(() => {
      pendingSubscriptionMonitor.stop()
    })
  }
}

// Функция для очистки всех каналов и реестров при teardown Echo
export function cleanupWebSocketChannels(): void {
  logger.debug('[useWebSocket] Cleaning up all channels and registries', {})

  pendingSubscriptionMonitor.stop()

  // Очищаем все каналы
  channelControls.forEach(control => {
    try {
      channelControlManager.removeChannelListeners(control)
      if (isBrowser() && window.Echo) {
        try {
          window.Echo.leave?.(control.channelName)
        } catch {
          // ignore leave errors
        }
      }
    } catch (error) {
      logger.warn('[useWebSocket] Error cleaning up channel', {
        channel: control.channelName,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  })
  
  // Очищаем все структуры данных
  channelControls.clear()
  channelSubscribers.clear()
  activeSubscriptions.clear()
  componentChannelCounts.clear()
  // Сохраняем ссылки на sets, чтобы существующие инстансы могли продолжить обновлять свои subscriptions
  instanceSubscriptionSets.forEach(set => set.clear())
  globalChannelRegistry.clear()
  pendingSubscriptions.clear()
  
  // Очищаем состояние resubscribe
  resubscribeManager.reset()
  
  logger.debug('[useWebSocket] All channels and registries cleaned up', {})
}

export function resubscribeAllChannels(): void {
  channelControlManager.resubscribeAllChannels()
}

export function useWebSocket(showToast?: ToastHandler, componentTag?: string) {
  const subscriptions = ref<Set<string>>(new Set())
  componentCounter += 1
  const instanceId = componentCounter
  const resolvedComponentTag = componentTag || `component-${instanceId}`
  instanceSubscriptionSets.set(instanceId, subscriptions.value)

  const subscribeToZoneCommands = (
    zoneId: number,
    handler?: ZoneCommandHandler,
    onSnapshot?: SnapshotHandler
  ): (() => void) => {
    if (typeof handler !== 'function') {
      logger.warn('[useWebSocket] Missing zone command handler', { zoneId })
      return () => undefined
    }

    if (typeof zoneId !== 'number' || Number.isNaN(zoneId)) {
      logger.warn('[useWebSocket] Invalid zoneId provided for subscription', { zoneId })
      return () => undefined
    }

    snapshotSync.initializeZoneSnapshotSubscription(zoneId, onSnapshot)

    if (!isWsEnabled()) {
      // Явно не добавляем отложенные подписки при отключенном WS
      ensureEchoAvailable(showToast)
      return () => undefined
    }

    const channelName = `commands.${zoneId}`
    const echo = ensureEchoAvailable(showToast)
    
    // Если Echo не доступен, сохраняем подписку в очередь
    if (!echo) {
      return pendingSubscriptionsManager.createPendingSubscription(
        channelName,
        'zoneCommands',
        'private',
        handler,
        resolvedComponentTag,
        instanceId,
        showToast
      )
    }

    const control = channelControlManager.ensureChannelControl(channelName, 'zoneCommands', 'private')
    if (!control) {
      logger.warn('[useWebSocket] Unable to create zone command channel', { channel: channelName })
      return () => undefined
    }

    const subscription = createActiveSubscription(
      channelName,
      'zoneCommands',
      handler,
      resolvedComponentTag,
      instanceId,
      showToast
    )

    addSubscription(control, subscription)

    return () => {
      removeSubscription(subscription.id)
      // Очищаем handler при отписке, если больше нет подписок на эту зону
      const hasOtherSubscriptions = Array.from(activeSubscriptions.values())
        .some(sub => sub.kind === 'zoneCommands' && sub.channelName === channelName)
      if (!hasOtherSubscriptions) {
        removeSnapshotHandler(zoneId)
      }
    }
  }

  const subscribeToGlobalEvents = (
    handler?: GlobalEventHandler
  ): (() => void) => {
    if (typeof handler !== 'function') {
      logger.warn('[useWebSocket] Missing global event handler', {})
      return () => undefined
    }

    if (!isWsEnabled()) {
      // WS отключен явно: возвращаем no-op и не ставим в очередь
      ensureEchoAvailable(showToast)
      return () => undefined
    }

    // Используем глобальный реестр для предотвращения множественных auth запросов
    let registry = globalChannelRegistry.get(GLOBAL_EVENTS_CHANNEL)
    
    // Если канал уже существует и авторизован, просто добавляем handler без нового auth
    if (
      registry &&
      registry.channelControl &&
      registry.channelControl.echoChannel &&
      !channelControlManager.isChannelDead(GLOBAL_EVENTS_CHANNEL)
    ) {
      // Канал уже существует и авторизован - переиспользуем его
      registry.handlers.add(handler)
      registry.subscriptionRefCount += 1
      
      const subscription = createActiveSubscription(
        GLOBAL_EVENTS_CHANNEL,
        'globalEvents',
        handler,
        resolvedComponentTag,
        instanceId
      )

      addSubscription(registry.channelControl, subscription)
      
      logger.debug('[useWebSocket] Reusing global events channel (no auth, ref-count++)', {
        channel: GLOBAL_EVENTS_CHANNEL,
        subscriptionId: subscription.id,
        componentTag: resolvedComponentTag,
        refCount: registry.subscriptionRefCount,
        totalHandlers: registry.handlers.size,
        instanceId,
      })

      return () => {
        // removeSubscription автоматически обновит реестр
        removeSubscription(subscription.id)
      }
    }

    const echo = ensureEchoAvailable(showToast)
    
    // Если Echo не доступен, сохраняем подписку в очередь
    if (!echo) {
      return pendingSubscriptionsManager.createPendingSubscription(
        GLOBAL_EVENTS_CHANNEL,
        'globalEvents',
        'private',
        handler,
        resolvedComponentTag,
        instanceId,
        showToast
      )
    }

    // Первая подписка - создаем канал и делаем auth запрос
    const control = channelControlManager.ensureChannelControl(
      GLOBAL_EVENTS_CHANNEL,
      'globalEvents',
      'private'
    )
    if (!control) {
      logger.warn('[useWebSocket] Unable to create global events channel', {})
      return () => undefined
    }

    // Обновляем реестр (ensureChannelControl уже создал запись в реестре)
    registry = globalChannelRegistry.get(GLOBAL_EVENTS_CHANNEL)
    if (!registry) {
      // Если реестр не создан, создаем его
      globalChannelRegistry.set(GLOBAL_EVENTS_CHANNEL, {
        channelControl: control,
        subscriptionRefCount: 0,
        isAuthorized: true,
        handlers: new Set(),
      })
      registry = globalChannelRegistry.get(GLOBAL_EVENTS_CHANNEL)
      if (!registry) {
        return () => undefined
      }
    }
    registry.handlers.add(handler)
    registry.subscriptionRefCount += 1

    const subscription = createActiveSubscription(
      GLOBAL_EVENTS_CHANNEL,
      'globalEvents',
      handler,
      resolvedComponentTag,
      instanceId
    )

    addSubscription(control, subscription)
    
    logger.debug('[useWebSocket] Created new global events channel (first auth request)', {
      channel: GLOBAL_EVENTS_CHANNEL,
      subscriptionId: subscription.id,
      componentTag: resolvedComponentTag,
      refCount: registry?.subscriptionRefCount ?? 1,
    })

    return () => {
      // removeSubscription автоматически обновит реестр
      removeSubscription(subscription.id)
    }
  }

  const unsubscribeAll = (): void => {
    // Удаляем также отложенные подписки этого компонента
    const pendingToRemove: string[] = []
    pendingSubscriptions.forEach((pending, id) => {
      if (pending.instanceId === instanceId) {
        pendingToRemove.push(id)
      }
    })
    pendingToRemove.forEach(id => pendingSubscriptions.delete(id))
    
    removeSubscriptionsByInstance(instanceId)
    subscriptions.value.clear()
    
    // Удаляем запись из instanceSubscriptionSets после полного отписывания
    // Это предотвращает утечку памяти при длительной работе/навигации по Inertia
    // "Мёртвые" инстансы больше не будут накапливаться в памяти
    instanceSubscriptionSets.delete(instanceId)
    
    // Также удаляем из componentChannelCounts, если остались записи
    // (на случай, если unsubscribeAll вызван до полной очистки через removeSubscriptionsByInstance)
    componentChannelCounts.delete(instanceId)
  }

  return {
    subscribeToZoneCommands,
    subscribeToGlobalEvents,
    unsubscribeAll,
    subscriptions,
    fetchSnapshot: snapshotSync.fetchAndApplySnapshot,
    getSnapshot: (zoneId: number) => getZoneSnapshot(zoneId) || null,
  }
}

// Экспорты для тестирования (только для unit-тестов)
export const __testExports = {
  activeSubscriptions: () => new Map(activeSubscriptions),
  channelSubscribers: () => new Map(channelSubscribers),
  channelControls: () => new Map(channelControls),
  globalChannelRegistry: () => new Map(globalChannelRegistry),
  pendingSubscriptions: () => new Map(pendingSubscriptions),
  getSubscriptionCount: (channelName: string) => channelSubscribers.get(channelName)?.size || 0,
  hasSubscription: (subscriptionId: string) => activeSubscriptions.has(subscriptionId),
  getChannelControl: (channelName: string) => channelControls.get(channelName),
  reset: () => {
    activeSubscriptions.clear()
    channelSubscribers.clear()
    channelControls.clear()
    globalChannelRegistry.clear()
    pendingSubscriptions.clear()
    clearSnapshotRegistry()
    componentChannelCounts.clear()
    instanceSubscriptionSets.clear()
    subscriptionCounter = 0
    componentCounter = 0
  },
}
