/**
 * Composable для работы с WebSocket через Laravel Echo
 */
import { ref, onUnmounted, type Ref } from 'vue'
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
  leave: () => void
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
      const channel = window.Echo.private(channelName)
      
      // Слушаем события обновления статуса команды
      channel.listen('.App\\Events\\CommandStatusUpdated', (event: unknown) => {
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
      })

      // Слушаем события ошибок команд
      channel.listen('.App\\Events\\CommandFailed', (evt: unknown) => {
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
      })

      const unsubscribe = () => {
        channel.stopListening('.App\\Events\\CommandStatusUpdated')
        channel.stopListening('.App\\Events\\CommandFailed')
        channel.leave()
        subscriptions.value.delete(channelName)
        // Удаляем из активных подписок
        const index = activeSubscriptions.findIndex(
          s => s.type === 'zone_commands' && s.id === zoneId
        )
        if (index > -1) {
          activeSubscriptions.splice(index, 1)
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
      console.error('Failed to subscribe to zone commands:', err)
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
      const channel = window.Echo.channel(channelName)
      
      // Слушаем события
      channel.listen('.App\\Events\\EventCreated', (evt: unknown) => {
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
      })

      const unsubscribe = () => {
        channel.stopListening('.App\\Events\\EventCreated')
        channel.leave()
        subscriptions.value.delete(channelName)
        // Удаляем из активных подписок
        const index = activeSubscriptions.findIndex(s => s.type === 'global_events')
        if (index > -1) {
          activeSubscriptions.splice(index, 1)
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
      console.error('Failed to subscribe to global events:', err)
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
    for (const [, { unsubscribe }] of subscriptions.value.entries()) {
      unsubscribe()
    }
    subscriptions.value.clear()
  }

  // Автоматическая отписка при размонтировании компонента
  onUnmounted(() => {
    unsubscribeAll()
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
  console.log('[WebSocket] Resubscribing to all channels...', activeSubscriptions.length, 'subscriptions')
  
  if (!window.Echo) {
    console.warn('[WebSocket] Echo не доступен для resubscribe')
    return
  }

  // Переподписываемся на все активные каналы
  activeSubscriptions.forEach(sub => {
    try {
      if (sub.type === 'zone_commands' && sub.id) {
        const channelName = `commands.${sub.id}`
        
        // Проверяем, не подписаны ли уже (Pusher автоматически переподписывается, но мы добавляем listeners)
        const channel = window.Echo!.private(channelName)
        
        // Слушаем события обновления статуса команды
        channel.listen('.App\\Events\\CommandStatusUpdated', (event: unknown) => {
          const e = event as CommandUpdateEvent
          sub.handler({
            commandId: e.commandId,
            status: e.status,
            message: e.message,
            error: e.error,
            zoneId: e.zoneId
          })
        })

        // Слушаем события ошибок команд
        channel.listen('.App\\Events\\CommandFailed', (evt: unknown) => {
          const e = evt as CommandUpdateEvent
          sub.handler({
            commandId: e.commandId,
            status: 'failed',
            message: e.message,
            error: e.error,
            zoneId: e.zoneId
          })
        })

        console.log(`[WebSocket] ✓ Resubscribed to zone commands: ${sub.id}`)
      } else if (sub.type === 'global_events') {
        const channelName = 'events.global'
        const channel = window.Echo!.channel(channelName)
        
        // Слушаем события
        channel.listen('.App\\Events\\EventCreated', (evt: unknown) => {
          const e = evt as GlobalZoneEvent
          sub.handler({
            id: e.id,
            kind: e.kind || 'INFO',
            message: e.message,
            zoneId: e.zoneId,
            occurredAt: e.occurredAt
          })
        })

        console.log('[WebSocket] ✓ Resubscribed to global events')
      }
    } catch (err) {
      console.error(`[WebSocket] ✗ Failed to resubscribe to ${sub.type}${sub.id ? ` (id: ${sub.id})` : ''}:`, err)
    }
  })
  
  console.log(`[WebSocket] Resubscribe completed: ${activeSubscriptions.length} channels restored`)
}

