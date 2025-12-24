/**
 * Единый модуль подписок WebSocket для зон и алертов
 * Использует единую инфраструктуру onWsStateChange из echoClient.ts для resubscribe
 * 
 * Этот модуль заменяет subscribeZone/subscribeAlerts из bootstrap.js
 * и обеспечивает единый путь для всех подписок WebSocket
 */
import { logger } from '@/utils/logger'
import { onWsStateChange, getEchoInstance } from '@/utils/echoClient'
import { registerSubscription, unregisterSubscription } from '@/ws/invariants'
import type { Zone } from '@/types/Zone'
import type { Alert } from '@/types/Alert'

/**
 * Обработчик событий обновления зоны
 */
export type ZoneUpdateHandler = (zone: Zone) => void

/**
 * Обработчик событий создания алерта
 */
export type AlertCreatedHandler = (alert: Alert) => void

/**
 * Подписаться на обновления зоны
 * Использует единую инфраструктуру useWebSocket для управления lifecycle
 * 
 * @param zoneId - ID зоны
 * @param handler - Обработчик события обновления зоны
 * @returns Функция для отписки
 */
export function subscribeZone(zoneId: number, handler: ZoneUpdateHandler): () => void {
  if (!zoneId || typeof zoneId !== 'number') {
    logger.warn('[ws/subscriptions] Invalid zoneId provided', { zoneId })
    return () => undefined
  }

  if (typeof handler !== 'function') {
    logger.warn('[ws/subscriptions] Invalid handler provided for zone subscription', { zoneId })
    return () => undefined
  }

  const channelName = `hydro.zones.${zoneId}`
  const eventName = '.App\\Events\\ZoneUpdated'
  
  // Генерируем уникальный ID для этой подписки
  const handlerId = `zone-${zoneId}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
  
  // Используем useWebSocket для управления подпиской
  // Но нам нужен прямой доступ к Echo для каналов зон (не commands)
  // Поэтому создаем подписку напрямую через Echo, но используем onWsStateChange для reconnect
  
  let channel: any = null
  let listener: ((event: any) => void) | null = null
  let unsubscribeWsState: (() => void) | null = null
  let stopped = false

  const cleanupChannel = (): void => {
    try {
      if (channel && listener) {
        channel.stopListening(eventName)
      }
      if (channel && typeof window.Echo?.leave === 'function') {
        window.Echo.leave(channelName)
      }
    } catch (error) {
      logger.warn('[ws/subscriptions] subscribeZone cleanup failed', { 
        zoneId,
        error: error instanceof Error ? error.message : String(error)
      })
    } finally {
      channel = null
      listener = null
    }
  }

  const doSubscribe = (): void => {
    if (stopped) {
      return
    }

    const echo = window.Echo || getEchoInstance()
    if (!echo) {
      logger.debug('[ws/subscriptions] Echo not available for zone subscription', { zoneId })
      return
    }

    try {
      // Очищаем старый канал, если есть
      cleanupChannel()

      channel = echo.private(channelName)
      listener = (event: any) => {
        if (stopped) return
        try {
          handler(event.zone || event)
        } catch (error) {
          logger.error('[ws/subscriptions] Zone update handler error', {
            zoneId,
            error: error instanceof Error ? error.message : String(error)
          })
        }
      }
      channel.listen(eventName, listener)
      
      // Регистрируем подписку для проверки инвариантов
      registerSubscription(channelName, handlerId, eventName, `zone-${zoneId}`)
      
      logger.debug('[ws/subscriptions] Subscribed to zone channel', {
        channel: channelName,
        zoneId,
      })
    } catch (error) {
      logger.warn('[ws/subscriptions] Failed to subscribe to zone channel', {
        zoneId,
        error: error instanceof Error ? error.message : String(error)
      })
      cleanupChannel()
    }
  }

  // Пытаемся подписаться сразу, если Echo доступен
  doSubscribe()

  // Подписываемся на изменения состояния WebSocket для автоматического восстановления
  // Это единственный путь для resubscribe - через onWsStateChange из echoClient
  unsubscribeWsState = onWsStateChange((state) => {
    if (stopped) return
    
    if (state === 'connected') {
      logger.debug('[ws/subscriptions] WebSocket connected, resubscribing to zone channel', { zoneId })
      doSubscribe()
    } else if (state === 'disconnected') {
      logger.debug('[ws/subscriptions] WebSocket disconnected, cleaning up zone channel', { zoneId })
      cleanupChannel()
    }
  })

  return () => {
    stopped = true
    
    // Удаляем из реестра инвариантов
    unregisterSubscription(channelName, handlerId, eventName)
    
    // Отписываемся от изменений состояния WebSocket
    if (unsubscribeWsState) {
      unsubscribeWsState()
      unsubscribeWsState = null
    }
    
    // Отписываемся от канала зоны
    cleanupChannel()
    
    logger.debug('[ws/subscriptions] Unsubscribed from zone channel', { zoneId })
  }
}

/**
 * Подписаться на создание алертов
 * Использует единую инфраструктуру useWebSocket для управления lifecycle
 * 
 * @param handler - Обработчик события создания алерта
 * @returns Функция для отписки
 */
export function subscribeAlerts(handler: AlertCreatedHandler): () => void {
  if (typeof handler !== 'function') {
    logger.warn('[ws/subscriptions] Invalid handler provided for alerts subscription')
    return () => undefined
  }

  const channelName = 'hydro.alerts'
  const eventName = '.App\\Events\\AlertCreated'
  
  // Генерируем уникальный ID для этой подписки
  const handlerId = `alerts-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
  
  let channel: any = null
  let listener: ((event: any) => void) | null = null
  let unsubscribeWsState: (() => void) | null = null
  let stopped = false

  const cleanupChannel = (): void => {
    try {
      if (channel && listener) {
        channel.stopListening(eventName)
      }
      if (channel && typeof window.Echo?.leave === 'function') {
        window.Echo.leave(channelName)
      }
    } catch (error) {
      logger.warn('[ws/subscriptions] subscribeAlerts cleanup failed', {
        error: error instanceof Error ? error.message : String(error)
      })
    } finally {
      channel = null
      listener = null
    }
  }

  const doSubscribe = (): void => {
    if (stopped || channel) {
      return
    }

    const echo = window.Echo || getEchoInstance()
    if (!echo) {
      logger.debug('[ws/subscriptions] Echo not available for alerts subscription')
      return
    }

    try {
      channel = echo.private(channelName)
      listener = (event: any) => {
        if (stopped) return
        try {
          handler(event.alert || event)
        } catch (error) {
          logger.error('[ws/subscriptions] Alert created handler error', {
            error: error instanceof Error ? error.message : String(error)
          })
        }
      }
      channel.listen(eventName, listener)
      
      // Регистрируем подписку для проверки инвариантов
      registerSubscription(channelName, handlerId, eventName, 'alerts')
      
      logger.debug('[ws/subscriptions] Subscribed to alerts channel', {
        channel: channelName,
        event: eventName,
      })
    } catch (error) {
      logger.warn('[ws/subscriptions] Failed to subscribe to alerts channel', {
        error: error instanceof Error ? error.message : String(error)
      })
      cleanupChannel()
    }
  }

  // Если Echo уже доступен, подписываемся сразу
  const echo = window.Echo || getEchoInstance()
  if (echo) {
    doSubscribe()
  } else {
    logger.debug('[ws/subscriptions] Echo not available, will subscribe on connect')
  }

  // Подписываемся на изменения состояния WebSocket для автоматического восстановления
  // Это единственный путь для resubscribe - через onWsStateChange из echoClient
  unsubscribeWsState = onWsStateChange((state) => {
    if (stopped) return
    
    if (state === 'connected') {
      logger.debug('[ws/subscriptions] WebSocket connected, resubscribing to alerts')
      doSubscribe()
    } else if (state === 'disconnected') {
      logger.debug('[ws/subscriptions] WebSocket disconnected, cleaning up alerts channel')
      cleanupChannel()
    }
  })

  return () => {
    stopped = true
    
    // Удаляем из реестра инвариантов
    unregisterSubscription(channelName, handlerId, eventName)
    
    // Отписываемся от изменений состояния WebSocket
    if (unsubscribeWsState) {
      unsubscribeWsState()
      unsubscribeWsState = null
    }
    
    // Отписываемся от канала алертов
    cleanupChannel()
    
    logger.debug('[ws/subscriptions] Unsubscribed from alerts channel')
  }
}

