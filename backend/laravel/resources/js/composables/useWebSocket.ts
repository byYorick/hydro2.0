/**
 * Composable для работы с WebSocket через Laravel Echo
 */
import { ref, onUnmounted, type Ref } from 'vue'
import { logger } from '@/utils/logger'
import type { ToastHandler } from './useApi'

// Расширяем Window для Echo
declare global {
  interface Window {
    Echo?: {
      private: (channel: string) => EchoChannel
      channel: (channel: string) => EchoChannel
      connector?: {
        pusher?: {
          connection?: {
            state?: string
            socket_id?: string
            bind: (eventName: string, handler: () => void) => void
          }
          channels?: {
            channels?: Record<string, unknown>
          }
        }
      }
    }
  }
}

interface EchoChannel {
  listen: (eventName: string, handler: (data: unknown) => void) => void
  stopListening: (event: string) => void
  leave?: () => void
}

interface Subscription {
  channel: EchoChannel
  unsubscribe: () => void
}

interface CommandUpdateEvent {
  commandId: number | string
  status: string
  message?: string
  error?: string
  zoneId?: number
}

interface GlobalZoneEvent {
  id: number
  kind: string
  message: string
  zoneId?: number
  occurredAt: string
}

/**
 * Глобальное хранилище активных подписок для автоматической переподписки при reconnect
 */
interface ActiveSubscription {
  type: 'zone_commands' | 'global_events'
  id?: number
  handler: (event: CommandUpdateEvent | GlobalZoneEvent) => void
}

// Глобальное хранилище (не ref, так как используется вне Vue компонентов)
const activeSubscriptions: ActiveSubscription[] = []

// Отслеживание уже подписанных каналов для предотвращения дублирования
const subscribedChannels = new Set<string>()

// Флаг для предотвращения одновременного выполнения resubscribe
let isResubscribing = false

/**
 * Composable для подписки на WebSocket каналы
 */
export function useWebSocket(showToast?: ToastHandler) {
  const subscriptions: Ref<Map<string, Subscription>> = ref(new Map())

  /**
   * Подписаться на канал команд зоны
   */
  function subscribeToZoneCommands(
    zoneId: number,
    onCommandUpdate?: (commandEvent: CommandUpdateEvent) => void
  ): () => void {
    if (!window.Echo) {
      if (showToast) {
        showToast('WebSocket не доступен', 'warning', 3000)
      }
      return () => {}
    }

    const channelName = `commands.${zoneId}`
    
    // Если уже подписаны, отписываемся
    if (subscriptions.value.has(channelName)) {
      const existing = subscriptions.value.get(channelName)!
      existing.unsubscribe()
    }

    // Удаляем старую подписку из активных, если есть
    const index = activeSubscriptions.findIndex(
      s => s.type === 'zone_commands' && s.id === zoneId
    )
    if (index > -1) {
      activeSubscriptions.splice(index, 1)
    }

    try {
      // Проверяем, не подписаны ли уже на этот канал (проверяем subscriptions, а не subscribedChannels)
      if (subscriptions.value.has(channelName)) {
        logger.warn(`[WebSocket] Already subscribed to ${channelName}, skipping`)
        // Возвращаем функцию отписки для существующей подписки
        const existing = subscriptions.value.get(channelName)
        if (existing) {
          return existing.unsubscribe
        }
      }

      const channel = window.Echo.private(channelName)
      
      // Слушаем события обновления статуса команды
      channel.listen('.App\\Events\\CommandStatusUpdated', (event: unknown) => {
        try {
          const e = event as CommandUpdateEvent
          if (onCommandUpdate) {
            onCommandUpdate({
              commandId: e.commandId,
              status: e.status,
              message: e.message,
              error: e.error,
              zoneId: e.zoneId
            })
          }
        } catch (err) {
          logger.error('[WebSocket] Error handling CommandStatusUpdated:', err)
        }
      })

      // Слушаем события ошибок команд
      channel.listen('.App\\Events\\CommandFailed', (evt: unknown) => {
        try {
          const e = evt as CommandUpdateEvent
          if (onCommandUpdate) {
            onCommandUpdate({
              commandId: e.commandId,
              status: 'failed',
              message: e.message,
              error: e.error,
              zoneId: e.zoneId
            })
          }
          if (showToast) {
            showToast(`Команда завершилась с ошибкой: ${e.message || 'Неизвестная ошибка'}`, 'error', 5000)
          }
        } catch (err) {
          logger.error('[WebSocket] Error handling CommandFailed:', err)
        }
      })

      subscribedChannels.add(channelName)

      const unsubscribe = () => {
        try {
          channel.stopListening('.App\\Events\\CommandStatusUpdated')
          channel.stopListening('.App\\Events\\CommandFailed')
          if (typeof channel.leave === 'function') {
            channel.leave()
          }
          subscriptions.value.delete(channelName)
          subscribedChannels.delete(channelName)
          // Удаляем из активных подписок
          const index = activeSubscriptions.findIndex(
            s => s.type === 'zone_commands' && s.id === zoneId
          )
          if (index > -1) {
            activeSubscriptions.splice(index, 1)
          }
        } catch (err) {
          logger.error('[WebSocket] Error during unsubscribe:', err)
        }
      }

      subscriptions.value.set(channelName, {
        channel,
        unsubscribe
      })

      // Добавляем в активные подписки для resubscribe
      if (onCommandUpdate) {
        activeSubscriptions.push({
          type: 'zone_commands',
          id: zoneId,
          handler: onCommandUpdate
        })
      }

      return unsubscribe
    } catch (err) {
      logger.error('[WebSocket] Failed to subscribe to zone commands:', err)
      if (showToast) {
        showToast('Ошибка при подключении к WebSocket', 'error', 5000)
      }
      return () => {}
    }
  }

  /**
   * Подписаться на глобальный канал событий
   */
  function subscribeToGlobalEvents(onEvent?: (globalEvent: GlobalZoneEvent) => void): () => void {
    if (!window.Echo) {
      if (showToast) {
        showToast('WebSocket не доступен', 'warning', 3000)
      }
      return () => {}
    }

    const channelName = 'events.global'
    
    // Если уже подписаны, отписываемся
    if (subscriptions.value.has(channelName)) {
      const existing = subscriptions.value.get(channelName)!
      existing.unsubscribe()
    }

    // Удаляем старую подписку из активных, если есть
    const index = activeSubscriptions.findIndex(s => s.type === 'global_events')
    if (index > -1) {
      activeSubscriptions.splice(index, 1)
    }

    try {
      // Проверяем, не подписаны ли уже на этот канал (проверяем subscriptions, а не subscribedChannels)
      if (subscriptions.value.has(channelName)) {
        logger.warn(`[WebSocket] Already subscribed to ${channelName}, skipping`)
        // Возвращаем функцию отписки для существующей подписки
        const existing = subscriptions.value.get(channelName)
        if (existing) {
          return existing.unsubscribe
        }
      }

      const channel = window.Echo.channel(channelName)
      
      // Слушаем события
      channel.listen('.App\\Events\\EventCreated', (evt: unknown) => {
        try {
          const e = evt as GlobalZoneEvent
          if (onEvent) {
            onEvent({
              id: e.id,
              kind: e.kind || 'INFO',
              message: e.message,
              zoneId: e.zoneId,
              occurredAt: e.occurredAt
            })
          }
        } catch (err) {
          logger.error('[WebSocket] Error handling EventCreated:', err)
        }
      })

      subscribedChannels.add(channelName)

      const unsubscribe = () => {
        try {
          channel.stopListening('.App\\Events\\EventCreated')
          if (typeof channel.leave === 'function') {
            channel.leave()
          }
          subscriptions.value.delete(channelName)
          subscribedChannels.delete(channelName)
          // Удаляем из активных подписок
          const index = activeSubscriptions.findIndex(s => s.type === 'global_events')
          if (index > -1) {
            activeSubscriptions.splice(index, 1)
          }
        } catch (err) {
          logger.error('[WebSocket] Error during unsubscribe:', err)
        }
      }

      subscriptions.value.set(channelName, {
        channel,
        unsubscribe
      })

      // Добавляем в активные подписки для resubscribe
      if (onEvent) {
        activeSubscriptions.push({
          type: 'global_events',
          handler: onEvent
        })
      }

      return unsubscribe
    } catch (err) {
      logger.error('[WebSocket] Failed to subscribe to global events:', err)
      if (showToast) {
        showToast('Ошибка при подключении к WebSocket', 'error', 5000)
      }
      return () => {}
    }
  }

  /**
   * Отписаться от всех каналов
   */
  function unsubscribeAll(): void {
    try {
      for (const [, { unsubscribe }] of subscriptions.value.entries()) {
        unsubscribe()
      }
      subscriptions.value.clear()
      subscribedChannels.clear()
      activeSubscriptions.length = 0
    } catch (err) {
      logger.error('[WebSocket] Error during unsubscribeAll:', err)
    }
  }

  // Автоматическая отписка при размонтировании компонента
  onUnmounted(() => {
    // Отписываемся только от подписок этого компонента
    for (const [channelName, { unsubscribe }] of subscriptions.value.entries()) {
      try {
        unsubscribe()
      } catch (err) {
        logger.error(`[WebSocket] Error during component unmount unsubscribe for ${channelName}:`, err)
      }
    }
    subscriptions.value.clear()
    
    // Очищаем подписки из activeSubscriptions, которые принадлежат этому компоненту
    // Это сложно отследить, поэтому просто очищаем невалидные при следующем resubscribe
  })

  return {
    subscribeToZoneCommands,
    subscribeToGlobalEvents,
    unsubscribeAll,
  }
}

/**
 * Глобальная функция для переподписки на все активные каналы при reconnect
 * Вызывается из bootstrap.js при событии 'connected'
 * 
 * Примечание: Эта функция восстанавливает подписки напрямую через Echo,
 * не используя экземпляры useWebSocket, так как она вызывается глобально
 * при reconnect, когда компоненты могут быть еще не смонтированы.
 */
export function resubscribeAllChannels(): void {
  // Защита от одновременного выполнения
  if (isResubscribing) {
    logger.warn('[WebSocket] Resubscribe already in progress, skipping')
    return
  }

  if (logger.debug && typeof logger.debug === 'function') {
    logger.debug('[WebSocket] Resubscribing to all channels...', activeSubscriptions.length, 'subscriptions')
  }
  
  if (!window.Echo) {
    logger.warn('[WebSocket] Echo не доступен для resubscribe')
    return
  }

  // Проверяем состояние соединения
  const pusher = window.Echo.connector?.pusher
  if (!pusher?.connection || pusher.connection.state !== 'connected') {
    logger.warn('[WebSocket] Connection not ready for resubscribe, state:', pusher?.connection?.state)
    return
  }

  // Защита от одновременного выполнения
  if (isResubscribing) {
    logger.warn('[WebSocket] Resubscribe already in progress, skipping')
    return
  }

  isResubscribing = true

  // Фильтруем валидные подписки (удаляем те, у которых нет handler) - делаем до try, чтобы была доступна в finally
  const validSubscriptions = activeSubscriptions.filter(sub => {
    if (!sub.handler || typeof sub.handler !== 'function') {
      logger.warn('[WebSocket] Removing invalid subscription:', sub)
      return false
    }
    return true
  })

  // Обновляем массив активных подписок
  activeSubscriptions.length = 0
  activeSubscriptions.push(...validSubscriptions)

  try {

    // Очищаем отслеживание подписанных каналов, так как при reconnect они сбрасываются
    subscribedChannels.clear()

    // Переподписываемся на все активные каналы
    validSubscriptions.forEach(sub => {
      try {
        if (sub.type === 'zone_commands' && sub.id) {
        const channelName = `commands.${sub.id}`
        
        // Проверяем, не подписаны ли уже (после очистки subscribedChannels это всегда false, но оставляем для безопасности)
        if (subscribedChannels.has(channelName)) {
          if (logger.debug && typeof logger.debug === 'function') {
            logger.debug(`[WebSocket] Already subscribed to ${channelName}, skipping`)
          }
          return
        }
        
        const channel = window.Echo!.private(channelName)
        
        // Слушаем события обновления статуса команды
        channel.listen('.App\\Events\\CommandStatusUpdated', (event: unknown) => {
          try {
            const e = event as CommandUpdateEvent
            sub.handler({
              commandId: e.commandId,
              status: e.status,
              message: e.message,
              error: e.error,
              zoneId: e.zoneId
            })
          } catch (err) {
            logger.error('[WebSocket] Error handling CommandStatusUpdated in resubscribe:', err)
          }
        })

        // Слушаем события ошибок команд
        channel.listen('.App\\Events\\CommandFailed', (evt: unknown) => {
          try {
            const e = evt as CommandUpdateEvent
            sub.handler({
              commandId: e.commandId,
              status: 'failed',
              message: e.message,
              error: e.error,
              zoneId: e.zoneId
            })
          } catch (err) {
            logger.error('[WebSocket] Error handling CommandFailed in resubscribe:', err)
          }
        })

        subscribedChannels.add(channelName)

        if (logger.debug && typeof logger.debug === 'function') {
          logger.debug(`[WebSocket] ✓ Resubscribed to zone commands: ${sub.id}`)
        }
      } else if (sub.type === 'global_events') {
        const channelName = 'events.global'
        
        // Проверяем, не подписаны ли уже
        if (subscribedChannels.has(channelName)) {
          if (logger.debug && typeof logger.debug === 'function') {
            logger.debug(`[WebSocket] Already subscribed to ${channelName}, skipping`)
          }
          return
        }
        
        const channel = window.Echo!.channel(channelName)
        
        // Слушаем события
        channel.listen('.App\\Events\\EventCreated', (evt: unknown) => {
          try {
            const e = evt as GlobalZoneEvent
            sub.handler({
              id: e.id,
              kind: e.kind || 'INFO',
              message: e.message,
              zoneId: e.zoneId,
              occurredAt: e.occurredAt
            })
          } catch (err) {
            logger.error('[WebSocket] Error handling EventCreated in resubscribe:', err)
          }
        })

        subscribedChannels.add(channelName)

        if (logger.debug && typeof logger.debug === 'function') {
          logger.debug('[WebSocket] ✓ Resubscribed to global events')
        }
      }
      } catch (err) {
        logger.error(`[WebSocket] ✗ Failed to resubscribe to ${sub.type}${sub.id ? ` (id: ${sub.id})` : ''}:`, err)
      }
    })
    
    if (logger.debug && typeof logger.debug === 'function') {
      logger.debug(`[WebSocket] Resubscribe completed: ${validSubscriptions.length} channels restored`)
    }
  } catch (err) {
    logger.error('[WebSocket] Error during resubscribe:', err)
  } finally {
    isResubscribing = false
  }
}

