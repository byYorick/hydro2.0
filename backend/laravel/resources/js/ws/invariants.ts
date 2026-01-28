/**
 * Инварианты и self-check режим для WebSocket подписок (DEV only)
 * 
 * Предотвращает регрессии reconnect/resubscribe через автоматическую проверку:
 * - Дублирование подписок на один канал/событие
 * - Утечки памяти при unmount
 * - Некорректное состояние реестров
 */
import { logger } from '@/utils/logger'
import { readBooleanEnv } from '@/utils/env'

// Флаг включения self-check режима (только в DEV)
const isDev = import.meta.env.DEV || import.meta.env.MODE === 'development'
const ENABLE_INVARIANTS = isDev && readBooleanEnv('VITE_WS_INVARIANTS', true)

// Реестр активных подписок для проверки дублей
interface SubscriptionRecord {
  channelName: string
  eventName?: string
  handlerId: string
  componentTag?: string
  timestamp: number
}

const activeSubscriptionsRegistry = new Map<string, SubscriptionRecord[]>()
const subscriptionWarnings = new Set<string>()

/**
 * Регистрирует подписку для проверки инвариантов
 */
export function registerSubscription(
  channelName: string,
  handlerId: string,
  eventName?: string,
  componentTag?: string
): void {
  if (!ENABLE_INVARIANTS) {
    return
  }

  const key = `${channelName}:${eventName || 'default'}`
  const records = activeSubscriptionsRegistry.get(key) || []
  
  // Проверяем на дублирование
  const duplicate = records.find(r => r.handlerId === handlerId)
  if (duplicate) {
    const warningKey = `${key}:${handlerId}`
    if (!subscriptionWarnings.has(warningKey)) {
      subscriptionWarnings.add(warningKey)
      logger.warn('[ws/invariants] Duplicate subscription detected', {
        channelName,
        eventName,
        handlerId,
        componentTag,
        existingRecord: duplicate,
      })
      console.warn(
        `[WS Invariants] ⚠️ Duplicate subscription detected:\n` +
        `  Channel: ${channelName}\n` +
        `  Event: ${eventName || 'default'}\n` +
        `  Handler ID: ${handlerId}\n` +
        `  Component: ${componentTag || 'unknown'}\n` +
        `  This may cause duplicate events!`
      )
    }
    return
  }

  // Добавляем новую подписку
  records.push({
    channelName,
    eventName,
    handlerId,
    componentTag,
    timestamp: Date.now(),
  })
  
  activeSubscriptionsRegistry.set(key, records)
  
  logger.debug('[ws/invariants] Subscription registered', {
    channelName,
    eventName,
    handlerId,
    componentTag,
    totalSubscriptions: records.length,
  })
}

/**
 * Удаляет подписку из реестра
 */
export function unregisterSubscription(
  channelName: string,
  handlerId: string,
  eventName?: string
): void {
  if (!ENABLE_INVARIANTS) {
    return
  }

  const key = `${channelName}:${eventName || 'default'}`
  const records = activeSubscriptionsRegistry.get(key) || []
  const filtered = records.filter(r => r.handlerId !== handlerId)
  
  if (filtered.length === records.length) {
    // Подписка не была найдена - возможная утечка или двойная отписка
    const warningKey = `unregister:${key}:${handlerId}`
    if (!subscriptionWarnings.has(warningKey)) {
      subscriptionWarnings.add(warningKey)
      logger.warn('[ws/invariants] Unregistering non-existent subscription', {
        channelName,
        eventName,
        handlerId,
      })
      console.warn(
        `[WS Invariants] ⚠️ Unregistering non-existent subscription:\n` +
        `  Channel: ${channelName}\n` +
        `  Event: ${eventName || 'default'}\n` +
        `  Handler ID: ${handlerId}`
      )
    }
  } else {
    activeSubscriptionsRegistry.set(key, filtered)
    if (filtered.length === 0) {
      activeSubscriptionsRegistry.delete(key)
    }
  }
  
  logger.debug('[ws/invariants] Subscription unregistered', {
    channelName,
    eventName,
    handlerId,
    remainingSubscriptions: filtered.length,
  })
}

/**
 * Получить статистику подписок (для отладки)
 */
export function getSubscriptionStats(): {
  totalChannels: number
  totalSubscriptions: number
  channels: Array<{
    channel: string
    event?: string
    count: number
    subscriptions: SubscriptionRecord[]
  }>
} {
  const channels: Array<{
    channel: string
    event?: string
    count: number
    subscriptions: SubscriptionRecord[]
  }> = []
  
  let totalSubscriptions = 0
  
  activeSubscriptionsRegistry.forEach((records, key) => {
    const [channelName, eventName] = key.split(':')
    const count = records.length
    totalSubscriptions += count
    
    channels.push({
      channel: channelName,
      event: eventName !== 'default' ? eventName : undefined,
      count,
      subscriptions: [...records],
    })
  })
  
  return {
    totalChannels: channels.length,
    totalSubscriptions,
    channels: channels.sort((a, b) => b.count - a.count),
  }
}

/**
 * Проверка инвариантов (вызывается периодически или при подозрении на проблему)
 */
export function checkInvariants(): {
  isValid: boolean
  issues: string[]
} {
  if (!ENABLE_INVARIANTS) {
    return { isValid: true, issues: [] }
  }

  const issues: string[] = []
  
  // Проверка 1: Дублирование подписок
  activeSubscriptionsRegistry.forEach((records, key) => {
    const handlerIds = new Set<string>()
    const duplicates: string[] = []
    
    records.forEach(record => {
      if (handlerIds.has(record.handlerId)) {
        duplicates.push(record.handlerId)
      } else {
        handlerIds.add(record.handlerId)
      }
    })
    
    if (duplicates.length > 0) {
      issues.push(
        `Duplicate subscriptions on ${key}: ${duplicates.join(', ')}`
      )
    }
  })
  
  // Проверка 2: Подозрительно большое количество подписок на один канал
  activeSubscriptionsRegistry.forEach((records, key) => {
    if (records.length > 10) {
      issues.push(
        `Suspiciously high subscription count on ${key}: ${records.length} subscriptions`
      )
    }
  })
  
  const isValid = issues.length === 0
  
  if (!isValid) {
    logger.warn('[ws/invariants] Invariant violations detected', {
      issues,
      stats: getSubscriptionStats(),
    })
  }
  
  return { isValid, issues }
}

/**
 * Очистить реестр (для тестов или при teardown)
 */
export function clearRegistry(): void {
  activeSubscriptionsRegistry.clear()
  subscriptionWarnings.clear()
  logger.debug('[ws/invariants] Registry cleared')
}

// Периодическая проверка инвариантов в DEV режиме
if (ENABLE_INVARIANTS && typeof window !== 'undefined') {
  let checkInterval: ReturnType<typeof setInterval> | null = null
  
  const startPeriodicCheck = () => {
    if (checkInterval) {
      return
    }
    
    // Проверяем каждые 30 секунд
    checkInterval = window.setInterval(() => {
      const result = checkInvariants()
      if (!result.isValid) {
        console.warn('[WS Invariants] ⚠️ Invariant violations detected:', result.issues)
      }
    }, 30000)
  }
  
  // Запускаем проверку после загрузки DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startPeriodicCheck, { once: true })
  } else {
    startPeriodicCheck()
  }
  
  // Экспортируем статистику в window для отладки
  if (typeof window !== 'undefined') {
    (window as any).__wsInvariants = {
      getStats: getSubscriptionStats,
      checkInvariants,
      clearRegistry,
    }
  }
}
