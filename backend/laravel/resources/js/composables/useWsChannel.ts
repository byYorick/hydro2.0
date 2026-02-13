/**
 * useWsChannel - единый helper для WebSocket подписок
 * 
 * Стандартизирует паттерн "одна подписка = один lifecycle" (mount/unmount)
 * Все подписки проходят через registerSubscription/unregisterSubscription
 * 
 * Использование:
 *   const unsubscribe = useWsChannel('commands.34', 'zoneCommands', handler, componentTag)
 *   onUnmounted(() => unsubscribe())
 */
import { onUnmounted } from 'vue'
import { useWebSocket } from './useWebSocket'
import type { ToastHandler } from './useApi'
import type { SnapshotHandler } from '@/types/reconciliation'
import type { GlobalEventHandler, ZoneCommandHandler } from '@/ws/subscriptionTypes'

interface UseWsChannelOptions {
  showToast?: ToastHandler
  componentTag?: string
  onSnapshot?: SnapshotHandler
}

/**
 * Подписка на канал команд зоны
 * 
 * @param zoneId - ID зоны
 * @param handler - Обработчик событий команд
 * @param options - Дополнительные опции
 * @returns Функция отписки (должна быть вызвана в onUnmounted)
 * 
 * @example
 * ```ts
 * const unsubscribe = useWsChannel.zoneCommands(
 *   zoneId.value,
 *   (event) => {
 *     console.log('Command status:', event.status)
 *   },
 *   { componentTag: 'ZoneShow' }
 * )
 * onUnmounted(() => unsubscribe())
 * ```
 */
export function useZoneCommandsChannel(
  zoneId: number,
  handler: ZoneCommandHandler,
  options: UseWsChannelOptions = {}
): () => void {
  const { showToast, componentTag, onSnapshot } = options
  const { subscribeToZoneCommands } = useWebSocket(showToast, componentTag)
  
  // Подписываемся на канал команд зоны
  const unsubscribe = subscribeToZoneCommands(zoneId, handler, onSnapshot)
  
  // Автоматически отписываемся при unmount компонента
  onUnmounted(() => {
    unsubscribe()
  })
  
  return unsubscribe
}

/**
 * Подписка на глобальные события
 * 
 * @param handler - Обработчик глобальных событий
 * @param options - Дополнительные опции
 * @returns Функция отписки (должна быть вызвана в onUnmounted)
 * 
 * @example
 * ```ts
 * const unsubscribe = useWsChannel.globalEvents(
 *   (event) => {
 *     console.log('Global event:', event.message)
 *   },
 *   { componentTag: 'Dashboard' }
 * )
 * onUnmounted(() => unsubscribe())
 * ```
 */
export function useGlobalEventsChannel(
  handler: GlobalEventHandler,
  options: UseWsChannelOptions = {}
): () => void {
  const { showToast, componentTag } = options
  const { subscribeToGlobalEvents } = useWebSocket(showToast, componentTag)
  
  // Подписываемся на глобальные события
  const unsubscribe = subscribeToGlobalEvents(handler)
  
  // Автоматически отписываемся при unmount компонента
  onUnmounted(() => {
    unsubscribe()
  })
  
  return unsubscribe
}

/**
 * Единый helper для WebSocket подписок
 * 
 * Стандартизированный интерфейс для всех типов подписок
 */
export const useWsChannel = {
  /**
   * Подписка на канал команд зоны
   */
  zoneCommands: useZoneCommandsChannel,
  
  /**
   * Подписка на глобальные события
   */
  globalEvents: useGlobalEventsChannel,
  
  /**
   * Получить все подписки для компонента (для отладки)
   */
  getSubscriptions: () => {
    const { subscriptions } = useWebSocket()
    return subscriptions
  },
}
