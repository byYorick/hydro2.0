import { ref } from 'vue'
import { logger } from '@/utils/logger'
import type { ToastHandler } from './useApi'
import { onWsStateChange } from '@/utils/echoClient'
import { readBooleanEnv } from '@/utils/env'

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

let subscriptionCounter = 0
let componentCounter = 0
let resubscribeTimer: ReturnType<typeof setTimeout> | null = null

const WS_DISABLED_MESSAGE = 'Realtime отключен в этой сборке'
const WS_UNAVAILABLE_MESSAGE = 'WebSocket не доступен'

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
    // ИСПРАВЛЕНО: Не показываем warning, если Echo просто еще не инициализирован
    // Это нормально на начальной загрузке страницы
    // Только логируем в debug режиме для отладки
    logger.debug('[useWebSocket] Echo instance not yet initialized', {})
    return null
  }
  return echo
}

function createSubscriptionId(): string {
  subscriptionCounter += 1
  return `sub-${subscriptionCounter}`
}

function isChannelDead(channelName: string): boolean {
  if (!isBrowser()) {
    return false
  }
  const pusherChannel = window.Echo?.connector?.pusher?.channels?.channels?.[channelName]
  if (!pusherChannel) {
    return false
  }

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
    return null
  }

  const shouldRecreate = !control.echoChannel || isChannelDead(channelName)

  if (shouldRecreate) {
    control.echoChannel =
      channelType === 'private' ? echo.private(channelName) : echo.channel(channelName)
    logger.debug('[useWebSocket] Created channel subscription', {
      channel: channelName,
      kind,
    })
  }

  if (!Object.keys(control.listenerRefs).length || shouldRecreate) {
    attachChannelListeners(control)
  }

  return control
}

function addSubscription(control: ChannelControl, subscription: ActiveSubscription): void {
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
    instanceSubscriptionSets.get(instanceId)?.delete(channelName)
  } else {
    channelMap.set(channelName, next)
  }
}

function removeSubscription(subscriptionId: string): void {
  const subscription = activeSubscriptions.get(subscriptionId)
  if (!subscription) {
    return
  }

  activeSubscriptions.delete(subscriptionId)
  const channelSet = channelSubscribers.get(subscription.channelName)
  if (channelSet) {
    channelSet.delete(subscriptionId)
    if (channelSet.size === 0) {
      channelSubscribers.delete(subscription.channelName)
      const control = channelControls.get(subscription.channelName)
      if (control) {
        detachChannel(control, true)
      }
    }
  }

  decrementComponentChannel(subscription.instanceId, subscription.channelName)
  logger.debug('[useWebSocket] Removed subscription', {
    channel: subscription.channelName,
    subscriptionId,
    componentTag: subscription.componentTag,
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

if (isBrowser()) {
  try {
    onWsStateChange(state => {
      if (state === 'connected') {
        scheduleResubscribe()
      }
    })
  } catch {
    // ignore registration errors
  }
}

export function resubscribeAllChannels(): void {
  if (!isBrowser()) {
    return
  }
  const echo = window.Echo
  if (!echo) {
    logger.warn('[useWebSocket] resubscribe skipped: Echo unavailable', {})
    return
  }

  channelControls.forEach(control => {
    try {
      control.echoChannel =
        control.channelType === 'private'
          ? echo.private(control.channelName)
          : echo.channel(control.channelName)
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

    if (!ensureEchoAvailable(showToast)) {
      return () => undefined
    }

    const channelName = `commands.${zoneId}`
    const control = ensureChannelControl(channelName, 'zoneCommands', 'private')
    if (!control) {
      logger.warn('[useWebSocket] Unable to create zone command channel', { channel: channelName })
      return () => undefined
    }

    const subscriptionId = createSubscriptionId()
    const subscription: ActiveSubscription = {
      id: subscriptionId,
      channelName,
      kind: 'zoneCommands',
      handler,
      componentTag: resolvedComponentTag,
      showToast,
      instanceId,
    }

    addSubscription(control, subscription)

    return () => {
      removeSubscription(subscriptionId)
    }
  }

  const subscribeToGlobalEvents = (
    handler?: GlobalEventHandler
  ): (() => void) => {
    if (typeof handler !== 'function') {
      logger.warn('[useWebSocket] Missing global event handler', {})
      return () => undefined
    }

    if (!ensureEchoAvailable(showToast)) {
      return () => undefined
    }

    const control = ensureChannelControl(GLOBAL_EVENTS_CHANNEL, 'globalEvents', 'private')
    if (!control) {
      logger.warn('[useWebSocket] Unable to create global events channel', {})
      return () => undefined
    }

    const subscriptionId = createSubscriptionId()
    const subscription: ActiveSubscription = {
      id: subscriptionId,
      channelName: GLOBAL_EVENTS_CHANNEL,
      kind: 'globalEvents',
      handler,
      componentTag: resolvedComponentTag,
      instanceId,
    }

    addSubscription(control, subscription)

    return () => {
      removeSubscription(subscriptionId)
    }
  }

  const unsubscribeAll = (): void => {
    removeSubscriptionsByInstance(instanceId)
    subscriptions.value.clear()
  }

  return {
    subscribeToZoneCommands,
    subscribeToGlobalEvents,
    unsubscribeAll,
    subscriptions,
  }
}

