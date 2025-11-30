import { ref } from 'vue'
import { logger } from '@/utils/logger'
import type { ToastHandler } from './useApi'
import { onWsStateChange, getEchoInstance } from '@/utils/echoClient'
import { readBooleanEnv } from '@/utils/env'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

type ZoneCommandHandler = (event: {
  commandId: number | string
  status: string
  message?: string
  error?: string
  zoneId?: number
}) => void

type GlobalEventHandler = (event: {
  id: number | string
  kind: string
  message: string
  zoneId?: number
  occurredAt: string
}) => void

type ChannelKind = 'zoneCommands' | 'globalEvents'

interface ActiveSubscription {
  id: string
  channelName: string
  kind: ChannelKind
  handler: ZoneCommandHandler | GlobalEventHandler
  componentTag: string
  showToast?: ToastHandler
  instanceId: number
}

interface ChannelControl {
  channelName: string
  channelType: 'private' | 'public'
  kind: ChannelKind
  echoChannel: any | null
  listenerRefs: Record<string, (payload: any) => void>
}

const COMMAND_STATUS_EVENT = '.App\\Events\\CommandStatusUpdated'
const COMMAND_FAILED_EVENT = '.App\\Events\\CommandFailed'
const GLOBAL_EVENT_CREATED = '.App\\Events\\EventCreated'
const GLOBAL_EVENTS_CHANNEL = 'events.global'

const activeSubscriptions = new Map<string, ActiveSubscription>()
const channelSubscribers = new Map<string, Set<string>>()
const channelControls = new Map<string, ChannelControl>()
const componentChannelCounts = new Map<number, Map<string, number>>()
const instanceSubscriptionSets = new Map<number, Set<string>>()

// Глобальный реестр для глобальных каналов (events.global, commands.global)
// Используется для предотвращения множественных запросов на /broadcasting/auth
interface GlobalChannelRegistry {
  channelControl: ChannelControl | null
  subscriptionRefCount: number
  isAuthorized: boolean
  handlers: Set<GlobalEventHandler>
}

const globalChannelRegistry = new Map<string, GlobalChannelRegistry>()

// Очередь отложенных подписок для компонентов, смонтированных до готовности Echo
interface PendingSubscription {
  id: string
  channelName: string
  kind: ChannelKind
  channelType: 'private' | 'public'
  handler: ZoneCommandHandler | GlobalEventHandler
  componentTag: string
  instanceId: number
  showToast?: ToastHandler
}

const pendingSubscriptions = new Map<string, PendingSubscription>()

let subscriptionCounter = 0
let componentCounter = 0
let resubscribeTimer: ReturnType<typeof setTimeout> | null = null

const WS_DISABLED_MESSAGE = 'Realtime отключен в этой сборке'

// Вспомогательная функция для проверки, является ли канал глобальным
function isGlobalChannel(channelName: string): boolean {
  return channelName === GLOBAL_EVENTS_CHANNEL || channelName === 'commands.global'
}

function isBrowser(): boolean {
  return typeof window !== 'undefined'
}

function ensureEchoAvailable(showToast?: ToastHandler): any | null {
  if (!isBrowser()) {
    return null
  }
  const wsEnabled = readBooleanEnv('VITE_ENABLE_WS', true)
  if (!wsEnabled) {
    if (showToast) {
      showToast(WS_DISABLED_MESSAGE, 'warning', TOAST_TIMEOUT.NORMAL)
    }
    logger.warn('[useWebSocket] WebSocket disabled via env flag', {})
    return null
  }
  const echo = window.Echo
  if (!echo) {
    // Не показываем warning, если Echo просто еще не инициализирован
    // Это нормально на начальной загрузке страницы
    // Только логируем в debug режиме для отладки
    // bootstrap.js должен инициализировать Echo автоматически
    // Проверяем, не инициализируется ли Echo прямо сейчас
    const isInitializing = typeof window !== 'undefined' && 
      (window.Echo !== undefined || document.readyState === 'loading')
    
    if (!isInitializing) {
      // Если страница уже загружена и Echo все еще не инициализирован, это может быть проблемой
      // Но не показываем warning, так как это может быть нормальным поведением при отключенном WebSocket
      logger.debug('[useWebSocket] Echo instance not yet initialized', {
        readyState: document.readyState,
        hasWindowEcho: typeof window !== 'undefined' && window.Echo !== undefined,
      })
    } else {
      logger.debug('[useWebSocket] Echo instance not yet initialized, waiting for bootstrap.js', {
        readyState: document.readyState,
      })
    }
    return null
  }
  return echo
}

function createSubscriptionId(): string {
  subscriptionCounter += 1
  return `sub-${subscriptionCounter}`
}

// Вспомогательная функция для создания отложенной подписки
function createPendingSubscription(
  channelName: string,
  kind: ChannelKind,
  channelType: 'private' | 'public',
  handler: ZoneCommandHandler | GlobalEventHandler,
  componentTag: string,
  instanceId: number,
  showToast?: ToastHandler
): (() => void) {
  const subscriptionId = createSubscriptionId()
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
  
  pendingSubscriptions.set(subscriptionId, pending)
  logger.debug('[useWebSocket] Echo not available, subscription queued', {
    channel: channelName,
    subscriptionId,
    componentTag,
  })
  
  // Пытаемся обработать сразу, если Echo появится
  setTimeout(() => {
    processPendingSubscriptions()
  }, 100)
  
  return () => {
    // Удаляем из очереди при отписке
    pendingSubscriptions.delete(subscriptionId)
    // Также удаляем из активных, если успели подписаться
    removeSubscription(subscriptionId)
  }
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

function getPusherChannel(channelName: string): any | null {
  if (!isBrowser()) {
    return null
  }

  const channels = window.Echo?.connector?.pusher?.channels?.channels
  if (!channels) {
    return null
  }

  // Pusher хранит private/presence каналы с префиксом, поэтому проверяем оба варианта
  return (
    channels[channelName] ||
    channels[`private-${channelName}`] ||
    channels[`presence-${channelName}`] ||
    null
  )
}

function isChannelDead(channelName: string): boolean {
  if (!isBrowser()) {
    return true // Если не в браузере, канал мертв
  }
  
  // Если window.Echo не существует или изменился, все каналы мертвы
  if (!window.Echo) {
    return true
  }
  
  const pusherChannel = getPusherChannel(channelName)
  
  // Если канала нет в текущем window.Echo, он мертв
  // Это важно после teardown/реинициализации, когда создается новый экземпляр Echo
  if (!pusherChannel) {
    return true
  }

  // Проверяем, есть ли активные подписки на канале
  const hasBindings = Array.isArray(pusherChannel.bindings) && pusherChannel.bindings.length > 0
  const hasCallbacks =
    pusherChannel._callbacks && Object.keys(pusherChannel._callbacks).length > 0
  const hasEvents =
    pusherChannel._events && Object.keys(pusherChannel._events).length > 0

  return !(hasBindings || hasCallbacks || hasEvents)
}

function removeChannelListeners(control: ChannelControl): void {
  const channel = control.echoChannel
  if (!channel || !control.listenerRefs) {
    return
  }
  Object.keys(control.listenerRefs).forEach(eventName => {
    try {
      channel.stopListening(eventName)
    } catch {
      // ignore stop listening errors
    }
  })
  control.listenerRefs = {}
}

function attachChannelListeners(control: ChannelControl): void {
  const channel = control.echoChannel
  if (!channel) {
    logger.warn('[useWebSocket] Tried to attach listeners to missing channel', {
      channel: control.channelName,
    })
    return
  }

  removeChannelListeners(control)

  if (control.kind === 'zoneCommands') {
    const statusHandler = (payload: any) => handleCommandEvent(control.channelName, payload, false)
    const failedHandler = (payload: any) => handleCommandEvent(control.channelName, payload, true)
    channel.listen(COMMAND_STATUS_EVENT, statusHandler)
    channel.listen(COMMAND_FAILED_EVENT, failedHandler)
    control.listenerRefs = {
      [COMMAND_STATUS_EVENT]: statusHandler,
      [COMMAND_FAILED_EVENT]: failedHandler,
    }
  } else {
    const eventHandler = (payload: any) => handleGlobalEvent(control.channelName, payload)
    channel.listen(GLOBAL_EVENT_CREATED, eventHandler)
    control.listenerRefs = {
      [GLOBAL_EVENT_CREATED]: eventHandler,
    }
  }
}

function detachChannel(control: ChannelControl, removeControl = false): void {
  removeChannelListeners(control)
  if (isBrowser()) {
    try {
      window.Echo?.leave?.(control.channelName)
    } catch {
      // ignore leave errors
    }
  }
  control.echoChannel = null
  if (removeControl) {
    channelControls.delete(control.channelName)
  }
}

function ensureChannelControl(
  channelName: string,
  kind: ChannelKind,
  channelType: 'private' | 'public'
): ChannelControl | null {
  if (!isBrowser()) {
    return null
  }
  
  // Для глобальных каналов используем реестр для предотвращения множественных auth запросов
  if (isGlobalChannel(channelName)) {
    let registry = globalChannelRegistry.get(channelName)
    if (registry && registry.channelControl) {
      // Проверяем, что канал еще активен (не мертв)
      const channelStillActive = registry.channelControl.echoChannel && !isChannelDead(channelName)
      
      if (channelStillActive) {
        // Канал уже существует и авторизован, переиспользуем его
        logger.debug('[useWebSocket] Reusing existing global channel from registry', {
          channel: channelName,
          refCount: registry.subscriptionRefCount,
          isAuthorized: registry.isAuthorized,
          hasActiveChannel: true,
        })
        return registry.channelControl
      } else if (registry.channelControl.echoChannel === null) {
        // Канал был удален, но реестр остался - очищаем реестр и создадим новый канал
        logger.debug('[useWebSocket] Global channel was detached, clearing registry', {
          channel: channelName,
        })
        globalChannelRegistry.delete(channelName)
      }
    }
  }
  
  let control = channelControls.get(channelName)
  if (!control) {
    control = {
      channelName,
      channelType,
      kind,
      echoChannel: null,
      listenerRefs: {},
    }
    channelControls.set(channelName, control)
  }

  const echo = window.Echo
  if (!echo) {
    // Если window.Echo не существует, очищаем канал из control
    if (control.echoChannel) {
      control.echoChannel = null
    }
    return null
  }

  // Проверяем, что канал существует в текущем window.Echo
  // Если control.echoChannel существует, но канала нет в window.Echo, он мертв
  const shouldRecreate = !control.echoChannel || isChannelDead(channelName)
  
  // Дополнительная проверка: если control.echoChannel существует, но канала нет в window.Echo,
  // значит произошла реинициализация Echo и старый канал мертв
  if (control.echoChannel && !getPusherChannel(channelName)) {
    logger.debug('[useWebSocket] Channel not found in current Echo instance, marking as dead', {
      channel: channelName,
    })
    control.echoChannel = null
  }

  if (shouldRecreate || !control.echoChannel) {
    // Для глобальных каналов проверяем реестр перед созданием нового канала
    // Если канал уже есть в реестре и активен, переиспользуем его
    if (isGlobalChannel(channelName)) {
      const registry = globalChannelRegistry.get(channelName)
      if (registry && registry.channelControl && registry.channelControl.echoChannel && !isChannelDead(channelName)) {
        // Канал уже существует в реестре и активен - переиспользуем его
        logger.debug('[useWebSocket] Reusing global channel from registry (ref-count was 0)', {
          channel: channelName,
          kind,
          refCount: registry.subscriptionRefCount,
        })
        return registry.channelControl
      }
    }
    
    control.echoChannel =
      channelType === 'private' ? echo.private(channelName) : echo.channel(channelName)
    
    // Для глобальных каналов регистрируем в реестре
    if (isGlobalChannel(channelName)) {
      if (!globalChannelRegistry.has(channelName)) {
        globalChannelRegistry.set(channelName, {
          channelControl: control,
          subscriptionRefCount: 0,
          isAuthorized: false,
          handlers: new Set(),
        })
      }
      const registry = globalChannelRegistry.get(channelName)!
      registry.channelControl = control
      registry.isAuthorized = true
      
      logger.debug('[useWebSocket] Created global channel (first auth request)', {
        channel: channelName,
        kind,
      })
    } else {
      logger.debug('[useWebSocket] Created channel subscription', {
        channel: channelName,
        kind,
      })
    }
  }

  if (!Object.keys(control.listenerRefs).length || shouldRecreate) {
    attachChannelListeners(control)
  }

  return control
}

function addSubscription(_control: ChannelControl, subscription: ActiveSubscription): void {
  // control передается для совместимости API, но не используется напрямую
  activeSubscriptions.set(subscription.id, subscription)
  let channelSet = channelSubscribers.get(subscription.channelName)
  if (!channelSet) {
    channelSet = new Set()
    channelSubscribers.set(subscription.channelName, channelSet)
  }
  channelSet.add(subscription.id)
  incrementComponentChannel(subscription.instanceId, subscription.channelName)
  logger.debug('[useWebSocket] Added subscription', {
    channel: subscription.channelName,
    subscriptionId: subscription.id,
    componentTag: subscription.componentTag,
  })
}

function incrementComponentChannel(instanceId: number, channelName: string): void {
  let channelMap = componentChannelCounts.get(instanceId)
  if (!channelMap) {
    channelMap = new Map()
    componentChannelCounts.set(instanceId, channelMap)
  }
  channelMap.set(channelName, (channelMap.get(channelName) ?? 0) + 1)
  const instanceSet = instanceSubscriptionSets.get(instanceId)
  instanceSet?.add(channelName)
}

function decrementComponentChannel(instanceId: number, channelName: string): void {
  const channelMap = componentChannelCounts.get(instanceId)
  if (!channelMap) {
    return
  }
  const next = (channelMap.get(channelName) ?? 0) - 1
  if (next <= 0) {
    channelMap.delete(channelName)
    if (channelMap.size === 0) {
      componentChannelCounts.delete(instanceId)
    }
    // Удаляем канал из instanceSubscriptionSets
    const instanceSet = instanceSubscriptionSets.get(instanceId)
    if (instanceSet) {
      instanceSet.delete(channelName)
      // Если Set пустой, удаляем запись из instanceSubscriptionSets
      // Это предотвращает утечку памяти при длительной работе/навигации
      if (instanceSet.size === 0) {
        instanceSubscriptionSets.delete(instanceId)
      }
    }
  } else {
    channelMap.set(channelName, next)
  }
}

function removeSubscription(subscriptionId: string): void {
  const subscription = activeSubscriptions.get(subscriptionId)
  if (!subscription) {
    return
  }

  // Для глобальных каналов обновляем реестр перед удалением
  if (isGlobalChannel(subscription.channelName)) {
    const registry = globalChannelRegistry.get(subscription.channelName)
    if (registry) {
      // Удаляем handler из реестра
      if (subscription.handler && typeof subscription.handler === 'function') {
        registry.handlers.delete(subscription.handler as GlobalEventHandler)
      }
      registry.subscriptionRefCount = Math.max(0, registry.subscriptionRefCount - 1)
    }
  }

  activeSubscriptions.delete(subscriptionId)
  const channelSet = channelSubscribers.get(subscription.channelName)
  if (channelSet) {
    channelSet.delete(subscriptionId)
    if (channelSet.size === 0) {
      channelSubscribers.delete(subscription.channelName)
      const control = channelControls.get(subscription.channelName)
      if (control) {
        if (!isGlobalChannel(subscription.channelName)) {
          // Для не-глобальных каналов удаляем канал полностью
          detachChannel(control, true)
        } else {
          // Для глобальных каналов НЕ удаляем канал из реестра, даже если ref-count = 0
          // Это позволяет переиспользовать канал при следующей подписке без нового auth запроса
          // Канал останется в реестре и будет переиспользован при следующей навигации
          const registry = globalChannelRegistry.get(subscription.channelName)
          if (registry && registry.subscriptionRefCount === 0) {
            // Обнуляем handlers, но сохраняем канал в реестре для переиспользования
            registry.handlers.clear()
            logger.debug('[useWebSocket] Global channel kept in registry for reuse (ref-count=0)', {
              channel: subscription.channelName,
              hasActiveChannel: !!registry.channelControl?.echoChannel,
            })
            // Канал НЕ удаляется из реестра - он будет переиспользован при следующей подписке
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
    refCount: isGlobalChannel(subscription.channelName) ? globalChannelRegistry.get(subscription.channelName)?.subscriptionRefCount : undefined,
  })
}

function handleCommandEvent(channelName: string, payload: any, isFailure: boolean): void {
  const channelSet = channelSubscribers.get(channelName)
  if (!channelSet) {
    return
  }

  const normalized = {
    commandId: payload?.commandId ?? payload?.command_id,
    status: isFailure ? 'failed' : payload?.status ?? 'unknown',
    message: payload?.message,
    error: payload?.error,
    zoneId: payload?.zoneId ?? payload?.zone_id,
  }

  channelSet.forEach(subscriptionId => {
    const subscription = activeSubscriptions.get(subscriptionId)
    if (!subscription || subscription.kind !== 'zoneCommands') {
      return
    }
    try {
      ;(subscription.handler as ZoneCommandHandler)(normalized)
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

function handleGlobalEvent(channelName: string, payload: any): void {
  const channelSet = channelSubscribers.get(channelName)
  if (!channelSet) {
    return
  }

  const normalized = {
    id: payload?.id ?? payload?.eventId ?? payload?.event_id,
    kind: payload?.kind ?? payload?.type ?? 'INFO',
    message: payload?.message ?? '',
    zoneId: payload?.zoneId ?? payload?.zone_id,
    occurredAt: payload?.occurredAt ?? payload?.occurred_at ?? new Date().toISOString(),
  }

  channelSet.forEach(subscriptionId => {
    const subscription = activeSubscriptions.get(subscriptionId)
    if (!subscription || subscription.kind !== 'globalEvents') {
      return
    }
    try {
      ;(subscription.handler as GlobalEventHandler)(normalized)
    } catch (error) {
      logger.error('[useWebSocket] Global event handler error', {
        channel: channelName,
        componentTag: subscription.componentTag,
      }, error)
    }
  })
}

function removeSubscriptionsByInstance(instanceId: number): void {
  const idsToRemove: string[] = []
  activeSubscriptions.forEach((subscription, id) => {
    if (subscription.instanceId === instanceId) {
      idsToRemove.push(id)
    }
  })
  idsToRemove.forEach(id => removeSubscription(id))
}

function scheduleResubscribe(delay = 500): void {
  if (!isBrowser()) {
    return
  }
  if (resubscribeTimer) {
    clearTimeout(resubscribeTimer)
  }
  resubscribeTimer = window.setTimeout(() => {
    resubscribeTimer = null
    resubscribeAllChannels()
  }, delay)
}

// Обработка отложенных подписок при подключении Echo
function processPendingSubscriptions(): void {
  if (!isBrowser() || pendingSubscriptions.size === 0) {
    return
  }
  
  const echo = window.Echo || getEchoInstance()
  if (!echo) {
    logger.debug('[useWebSocket] Echo still not available, keeping subscriptions pending', {
      pendingCount: pendingSubscriptions.size,
    })
    return
  }
  
  logger.info('[useWebSocket] Processing pending subscriptions', {
    count: pendingSubscriptions.size,
  })
  
  // Обрабатываем все отложенные подписки
  // ВАЖНО: НЕ очищаем очередь до успешного создания канала
  // Если ensureChannelControl вернёт null, подписка останется в очереди для повторной попытки
  const toProcess = Array.from(pendingSubscriptions.entries())
  
  toProcess.forEach(([subscriptionId, pending]) => {
    try {
      // Для глобальных каналов проверяем реестр
      if (isGlobalChannel(pending.channelName)) {
        let registry = globalChannelRegistry.get(pending.channelName)
        if (registry && registry.channelControl && registry.channelControl.echoChannel && !isChannelDead(pending.channelName)) {
          // Канал уже существует и авторизован, просто добавляем handler
          registry.handlers.add(pending.handler as GlobalEventHandler)
          registry.subscriptionRefCount += 1
          
          const subscription = createActiveSubscription(
            pending.channelName,
            pending.kind,
            pending.handler,
            pending.componentTag,
            pending.instanceId,
            pending.showToast
          )
          subscription.id = pending.id // Используем ID из pending
          
          addSubscription(registry.channelControl, subscription)
          
          // Удаляем из очереди только после успешного создания подписки
          pendingSubscriptions.delete(subscriptionId)
          
          logger.debug('[useWebSocket] Processed pending subscription (reused global channel)', {
            channel: pending.channelName,
            subscriptionId: pending.id,
            componentTag: pending.componentTag,
            refCount: registry.subscriptionRefCount,
          })
          return
        }
      }
      
      const control = ensureChannelControl(pending.channelName, pending.kind, pending.channelType)
      if (!control || !control.echoChannel) {
        // Канал не создан (Echo ещё не готов или ошибка авторизации)
        // НЕ удаляем из очереди - оставляем для повторной попытки
        logger.warn('[useWebSocket] Failed to create channel for pending subscription, will retry', {
          channel: pending.channelName,
          subscriptionId: pending.id,
          reason: !control ? 'ensureChannelControl returned null' : 'echoChannel is null',
        })
        return
      }
      
      // Обновляем реестр для глобальных каналов
      if (isGlobalChannel(pending.channelName)) {
        let registry = globalChannelRegistry.get(pending.channelName)
        if (registry) {
          registry.handlers.add(pending.handler as GlobalEventHandler)
          registry.subscriptionRefCount += 1
        }
      }
      
      const subscription = createActiveSubscription(
        pending.channelName,
        pending.kind,
        pending.handler,
        pending.componentTag,
        pending.instanceId,
        pending.showToast
      )
      subscription.id = pending.id // Используем ID из pending
      
      addSubscription(control, subscription)
      
      // Удаляем из очереди только после успешного создания подписки
      pendingSubscriptions.delete(subscriptionId)
      
      logger.debug('[useWebSocket] Processed pending subscription', {
        channel: pending.channelName,
        subscriptionId: pending.id,
        componentTag: pending.componentTag,
      })
    } catch (error) {
      // При ошибке не удаляем из очереди - оставляем для повторной попытки
      logger.error('[useWebSocket] Error processing pending subscription, will retry', {
        channel: pending.channelName,
        subscriptionId: pending.id,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  })
}

if (isBrowser()) {
  try {
    onWsStateChange(state => {
      if (state === 'connected') {
        scheduleResubscribe()
        // Обрабатываем отложенные подписки при подключении
        processPendingSubscriptions()
      }
    })
  } catch {
    // ignore registration errors
  }
  
  // Периодически проверяем доступность Echo для обработки отложенных подписок
  // Это нужно на случай, если компонент смонтировался до инициализации Echo
  let pendingCheckInterval: ReturnType<typeof setInterval> | null = null
  
  const startPendingCheck = () => {
    if (pendingCheckInterval) {
      return
    }
    
    pendingCheckInterval = window.setInterval(() => {
      if (pendingSubscriptions.size > 0) {
        const echo = window.Echo || getEchoInstance()
        if (echo) {
          processPendingSubscriptions()
          // Останавливаем проверку, если все подписки обработаны
          if (pendingSubscriptions.size === 0 && pendingCheckInterval) {
            clearInterval(pendingCheckInterval)
            pendingCheckInterval = null
          }
        }
      } else if (pendingCheckInterval) {
        // Нет отложенных подписок, останавливаем проверку
        clearInterval(pendingCheckInterval)
        pendingCheckInterval = null
      }
    }, 1000) // Проверяем каждую секунду
  }
  
  // Запускаем проверку при загрузке модуля
  startPendingCheck()
  
  // Очистка при HMR
  if ((import.meta as any).hot) {
    (import.meta as any).hot.dispose(() => {
      if (pendingCheckInterval) {
        clearInterval(pendingCheckInterval)
        pendingCheckInterval = null
      }
    })
  }
}

// Функция для очистки всех каналов и реестров при teardown Echo
export function cleanupWebSocketChannels(): void {
  logger.debug('[useWebSocket] Cleaning up all channels and registries', {})
  
  // Очищаем все каналы
  channelControls.forEach(control => {
    try {
      removeChannelListeners(control)
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
  componentChannelCounts.clear()
  instanceSubscriptionSets.clear()
  globalChannelRegistry.clear()
  pendingSubscriptions.clear()
  
  // Очищаем таймеры
  if (resubscribeTimer) {
    clearTimeout(resubscribeTimer)
    resubscribeTimer = null
  }
  
  logger.debug('[useWebSocket] All channels and registries cleaned up', {})
}

export function resubscribeAllChannels(): void {
  if (!isBrowser()) {
    return
  }
  const echo = window.Echo
  if (!echo) {
    // Это нормально на начальной загрузке страницы, когда Echo еще не инициализирован
    // Логируем в debug режиме, а не warning, чтобы не путать пользователя
    logger.debug('[useWebSocket] resubscribe skipped: Echo not yet initialized', {
      readyState: document.readyState,
    })
    return
  }

  channelControls.forEach(control => {
    try {
      // Очищаем старые слушатели перед пересозданием канала
      removeChannelListeners(control)
      
      // Очищаем старый канал, если он существует
      if (control.echoChannel) {
        try {
          if (isBrowser() && window.Echo) {
            window.Echo.leave?.(control.channelName)
          }
        } catch {
          // ignore leave errors
        }
        control.echoChannel = null
      }
      
      // Создаем новый канал в текущем window.Echo
      control.echoChannel =
        control.channelType === 'private'
          ? echo.private(control.channelName)
          : echo.channel(control.channelName)
      
      // Прикрепляем слушатели к новому каналу
      attachChannelListeners(control)
      logger.debug('[useWebSocket] Resubscribed channel', { channel: control.channelName })
    } catch (error) {
      logger.error('[useWebSocket] Failed to resubscribe channel', {
        channel: control.channelName,
      }, error)
    }
  })
}

export function useWebSocket(showToast?: ToastHandler, componentTag?: string) {
  const subscriptions = ref<Set<string>>(new Set())
  componentCounter += 1
  const instanceId = componentCounter
  const resolvedComponentTag = componentTag || `component-${instanceId}`
  instanceSubscriptionSets.set(instanceId, subscriptions.value)

  const subscribeToZoneCommands = (
    zoneId: number,
    handler?: ZoneCommandHandler
  ): (() => void) => {
    if (typeof handler !== 'function') {
      logger.warn('[useWebSocket] Missing zone command handler', { zoneId })
      return () => undefined
    }

    if (typeof zoneId !== 'number' || Number.isNaN(zoneId)) {
      logger.warn('[useWebSocket] Invalid zoneId provided for subscription', { zoneId })
      return () => undefined
    }

    const channelName = `commands.${zoneId}`
    const echo = ensureEchoAvailable(showToast)
    
    // Если Echo не доступен, сохраняем подписку в очередь
    if (!echo) {
      return createPendingSubscription(
        channelName,
        'zoneCommands',
        'private',
        handler,
        resolvedComponentTag,
        instanceId,
        showToast
      )
    }

    const control = ensureChannelControl(channelName, 'zoneCommands', 'private')
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
    }
  }

  const subscribeToGlobalEvents = (
    handler?: GlobalEventHandler
  ): (() => void) => {
    if (typeof handler !== 'function') {
      logger.warn('[useWebSocket] Missing global event handler', {})
      return () => undefined
    }

    // Используем глобальный реестр для предотвращения множественных auth запросов
    let registry = globalChannelRegistry.get(GLOBAL_EVENTS_CHANNEL)
    
    // Если канал уже существует и авторизован, просто добавляем handler без нового auth
    if (registry && registry.channelControl && registry.channelControl.echoChannel && !isChannelDead(GLOBAL_EVENTS_CHANNEL)) {
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
      return createPendingSubscription(
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
    const control = ensureChannelControl(GLOBAL_EVENTS_CHANNEL, 'globalEvents', 'private')
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
      registry = globalChannelRegistry.get(GLOBAL_EVENTS_CHANNEL)!
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
  }
}
