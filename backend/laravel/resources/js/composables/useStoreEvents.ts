/**
 * Система событий для координации между stores и компонентами
 * Используется для синхронизации состояния между экранами
 */

import { logger } from '@/utils/logger'

// Простая реализация EventEmitter для браузера
class EventEmitter {
  private events: Map<string, Array<(...args: any[]) => void>> = new Map()

  on(event: string, listener: (...args: any[]) => void): void {
    if (!this.events.has(event)) {
      this.events.set(event, [])
    }
    const listeners = this.events.get(event)
    if (listeners) {
      listeners.push(listener)
    }
  }

  off(event: string, listener: (...args: any[]) => void): void {
    const listeners = this.events.get(event)
    if (!listeners) return
    
    const index = listeners.indexOf(listener)
    if (index > -1) {
      listeners.splice(index, 1)
    }
  }

  emit(event: string, ...args: any[]): void {
    const listeners = this.events.get(event)
    if (!listeners) return
    
    // Вызываем все слушатели синхронно
    listeners.forEach(listener => {
      try {
        listener(...args)
      } catch (err) {
        logger.error(`[StoreEvents] Error in listener for "${event}":`, err)
      }
    })
  }

  once(event: string, listener: (...args: any[]) => void): void {
    const wrapper = (...args: any[]) => {
      listener(...args)
      this.off(event, wrapper)
    }
    this.on(event, wrapper)
  }

  removeAllListeners(event?: string): void {
    if (event) {
      this.events.delete(event)
    } else {
      this.events.clear()
    }
  }
}

/**
 * Глобальный экземпляр EventEmitter для координации stores
 */
export const storeEvents = new EventEmitter()

/**
 * Типы событий для координации
 */
export type StoreEventType =
  | 'zone:updated'
  | 'zone:created'
  | 'zone:deleted'
  | 'zone:recipe:attached'
  | 'zone:recipe:detached'
  | 'device:updated'
  | 'device:created'
  | 'device:deleted'
  | 'device:lifecycle:transitioned'
  | 'recipe:updated'
  | 'recipe:created'
  | 'recipe:deleted'
  | 'cache:invalidated'

/**
 * Composable для работы с событиями stores
 */
export function useStoreEvents() {
  // Динамический импорт Vue hooks для избежания проблем с SSR
  let onUnmountedHook: ((fn: () => void) => void) | null = null
  
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const vue = require('vue')
    onUnmountedHook = vue.onUnmounted
  } catch (e) {
    // Если Vue недоступен (например, в SSR), используем заглушки
    onUnmountedHook = () => {}
  }
  
  /**
   * Подписаться на событие
   */
  function subscribe<T = any>(
    event: StoreEventType,
    listener: (data: T) => void
  ): () => void {
    // Обёртка для обработки ошибок в listeners
    const wrappedListener = (data: T) => {
      try {
        listener(data)
      } catch (error) {
        console.error(`[StoreEvents] Error in listener for "${event}":`, error)
      }
    }
    
    storeEvents.on(event, wrappedListener)
    
    // Возвращаем функцию для отписки
    return () => {
      storeEvents.off(event, wrappedListener)
    }
  }
  
  /**
   * Подписаться на событие с автоматической отпиской при размонтировании
   */
  function subscribeWithCleanup<T = any>(
    event: StoreEventType,
    listener: (data: T) => void
  ): void {
    const unsubscribe = subscribe(event, listener)
    
    if (onUnmountedHook) {
      onUnmountedHook(() => {
        unsubscribe()
      })
    }
  }
  
  /**
   * Отписаться от события
   */
  function unsubscribe(
    event: StoreEventType,
    listener: (...args: any[]) => void
  ): void {
    storeEvents.off(event, listener)
  }
  
  /**
   * Эмитнуть событие
   */
  function emit<T = any>(event: StoreEventType, data: T): void {
    storeEvents.emit(event, data)
  }
  
  return {
    subscribe,
    subscribeWithCleanup,
    unsubscribe,
    emit,
  }
}

/**
 * Хелперы для конкретных типов событий
 */
export const zoneEvents = {
  updated: (zone: any) => storeEvents.emit('zone:updated', zone),
  created: (zone: any) => storeEvents.emit('zone:created', zone),
  deleted: (zoneId: number) => storeEvents.emit('zone:deleted', zoneId),
  recipeAttached: (data: { zoneId: number; recipeId: number }) => 
    storeEvents.emit('zone:recipe:attached', data),
  recipeDetached: (data: { zoneId: number; recipeId: number }) => 
    storeEvents.emit('zone:recipe:detached', data),
}

export const deviceEvents = {
  updated: (device: any) => storeEvents.emit('device:updated', device),
  created: (device: any) => storeEvents.emit('device:created', device),
  deleted: (deviceId: number | string) => storeEvents.emit('device:deleted', deviceId),
  lifecycleTransitioned: (data: { deviceId: number; fromState: string; toState: string }) => 
    storeEvents.emit('device:lifecycle:transitioned', data),
}

export const recipeEvents = {
  updated: (recipe: any) => storeEvents.emit('recipe:updated', recipe),
  created: (recipe: any) => storeEvents.emit('recipe:created', recipe),
  deleted: (recipeId: number) => storeEvents.emit('recipe:deleted', recipeId),
}
