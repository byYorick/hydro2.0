/**
 * Composable для работы с WebSocket через Laravel Echo
 */
import { ref, onUnmounted, watch } from 'vue'

/**
 * Composable для подписки на WebSocket каналы
 * @param {Function} showToast - Функция для показа Toast уведомлений
 * @returns {Object} Методы для работы с WebSocket
 */
export function useWebSocket(showToast = null) {
  const subscriptions = ref(new Map()) // Map<channelName, { channel, unsubscribe }>

  /**
   * Подписаться на канал команд зоны
   * @param {number} zoneId - ID зоны
   * @param {Function} onCommandUpdate - Обработчик обновления статуса команды
   * @returns {Function} Функция для отписки
   */
  function subscribeToZoneCommands(zoneId, onCommandUpdate) {
    if (!window.Echo) {
      if (showToast) {
        showToast('WebSocket не доступен', 'warning', 3000)
      }
      return () => {}
    }

    const channelName = `commands.${zoneId}`
    
    // Если уже подписаны, отписываемся
    if (subscriptions.value.has(channelName)) {
      const existing = subscriptions.value.get(channelName)
      existing.unsubscribe()
    }

    try {
      const channel = window.Echo.private(channelName)
      
      // Слушаем события обновления статуса команды
      channel.listen('.App\\Events\\CommandStatusUpdated', (event) => {
        if (onCommandUpdate) {
          onCommandUpdate({
            commandId: event.command_id,
            status: event.status,
            message: event.message,
            error: event.error,
            zoneId: event.zone_id
          })
        }
      })

      // Слушаем события ошибок команд
      channel.listen('.App\\Events\\CommandFailed', (event) => {
        if (onCommandUpdate) {
          onCommandUpdate({
            commandId: event.command_id,
            status: 'failed',
            message: event.message,
            error: event.error,
            zoneId: event.zone_id
          })
        }
        if (showToast) {
          showToast(`Команда завершилась с ошибкой: ${event.message || 'Неизвестная ошибка'}`, 'error', 5000)
        }
      })

      const unsubscribe = () => {
        channel.stopListening('.App\\Events\\CommandStatusUpdated')
        channel.stopListening('.App\\Events\\CommandFailed')
        channel.leave()
        subscriptions.value.delete(channelName)
      }

      subscriptions.value.set(channelName, {
        channel,
        unsubscribe
      })

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
   * @param {Function} onEvent - Обработчик новых событий
   * @returns {Function} Функция для отписки
   */
  function subscribeToGlobalEvents(onEvent) {
    if (!window.Echo) {
      if (showToast) {
        showToast('WebSocket не доступен', 'warning', 3000)
      }
      return () => {}
    }

    const channelName = 'events.global'
    
    // Если уже подписаны, отписываемся
    if (subscriptions.value.has(channelName)) {
      const existing = subscriptions.value.get(channelName)
      existing.unsubscribe()
    }

    try {
      const channel = window.Echo.channel(channelName)
      
      // Слушаем события
      channel.listen('.App\\Events\\EventCreated', (event) => {
        if (onEvent) {
          onEvent({
            id: event.id,
            kind: event.kind || 'INFO',
            message: event.message,
            zoneId: event.zone_id,
            occurredAt: event.occurred_at
          })
        }
      })

      const unsubscribe = () => {
        channel.stopListening('.App\\Events\\EventCreated')
        channel.leave()
        subscriptions.value.delete(channelName)
      }

      subscriptions.value.set(channelName, {
        channel,
        unsubscribe
      })

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
  function unsubscribeAll() {
    for (const [channelName, { unsubscribe }] of subscriptions.value.entries()) {
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

