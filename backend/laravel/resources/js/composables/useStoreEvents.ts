/**
 * Система событий для координации между stores и компонентами
 * Используется для синхронизации состояния между экранами
 */

import { logger } from '@/utils/logger'
import type { Zone, Device, Recipe } from '@/types'

interface StoreEventPayloadMap {
  'zone:updated': Zone
  'zone:created': Zone
  'zone:deleted': number
  'zone:recipe:attached': { zoneId: number; recipeId: number }
  'zone:recipe:detached': { zoneId: number; recipeId: number }
  'device:updated': Device
  'device:created': Device
  'device:deleted': number | string
  'device:lifecycle:transitioned': { deviceId: number; fromState: string; toState: string }
  'recipe:updated': Recipe
  'recipe:created': Recipe
  'recipe:deleted': number
  'cache:invalidated': string
}

// Простая реализация EventEmitter для браузера
class EventEmitter<TEvents extends object> {
  private events: Map<keyof TEvents & string, Set<(payload: unknown) => void>> = new Map()

  on<K extends keyof TEvents & string>(event: K, listener: (payload: TEvents[K]) => void): void {
    if (!this.events.has(event)) {
      this.events.set(event, new Set())
    }
    this.events.get(event)?.add(listener as (payload: unknown) => void)
  }

  off<K extends keyof TEvents & string>(event: K, listener: (payload: TEvents[K]) => void): void {
    const listeners = this.events.get(event)
    if (!listeners) {
      return
    }
    listeners.delete(listener as (payload: unknown) => void)
  }

  emit<K extends keyof TEvents & string>(event: K, payload: TEvents[K]): void {
    const listeners = this.events.get(event)
    if (!listeners) {
      return
    }

    // Вызываем все слушатели синхронно
    listeners.forEach(listener => {
      try {
        listener(payload)
      } catch (err) {
        logger.error(`[StoreEvents] Error in listener for "${event}":`, err)
      }
    })
  }

  once<K extends keyof TEvents & string>(event: K, listener: (payload: TEvents[K]) => void): void {
    const wrapper = (payload: TEvents[K]) => {
      listener(payload)
      this.off(event, wrapper)
    }
    this.on(event, wrapper)
  }

  removeAllListeners<K extends keyof TEvents & string>(event?: K): void {
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
export const storeEvents = new EventEmitter<StoreEventPayloadMap>()

/**
 * Типы событий для координации
 */
export type StoreEventType = keyof StoreEventPayloadMap

/**
 * Composable для работы с событиями stores
 */
export function useStoreEvents() {
  // Динамический импорт Vue hooks для избежания проблем с SSR
  let onUnmountedHook: ((fn: () => void) => void) | null = null
  
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const vue = require('vue')
    const hasInstance = typeof vue.getCurrentInstance === 'function' && !!vue.getCurrentInstance()
    onUnmountedHook = hasInstance ? vue.onUnmounted : () => {}
  } catch (e) {
    // Если Vue недоступен (например, в SSR), используем заглушки
    onUnmountedHook = () => {}
  }
  
  /**
   * Подписаться на событие
   */
  function subscribe<K extends StoreEventType>(
    event: K,
    listener: (data: StoreEventPayloadMap[K]) => void
  ): () => void {
    // Обёртка для обработки ошибок в listeners
    const wrappedListener = (data: StoreEventPayloadMap[K]) => {
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
  function subscribeWithCleanup<K extends StoreEventType>(
    event: K,
    listener: (data: StoreEventPayloadMap[K]) => void
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
  function unsubscribe<K extends StoreEventType>(
    event: K,
    listener: (data: StoreEventPayloadMap[K]) => void
  ): void {
    storeEvents.off(event, listener)
  }
  
  /**
   * Эмитнуть событие
   */
  function emit<K extends StoreEventType>(event: K, data: StoreEventPayloadMap[K]): void {
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
  updated: (zone: Zone) => storeEvents.emit('zone:updated', zone),
  created: (zone: Zone) => storeEvents.emit('zone:created', zone),
  deleted: (zoneId: number) => storeEvents.emit('zone:deleted', zoneId),
  recipeAttached: (data: { zoneId: number; recipeId: number }) => 
    storeEvents.emit('zone:recipe:attached', data),
  recipeDetached: (data: { zoneId: number; recipeId: number }) => 
    storeEvents.emit('zone:recipe:detached', data),
}

export const deviceEvents = {
  updated: (device: Device) => storeEvents.emit('device:updated', device),
  created: (device: Device) => storeEvents.emit('device:created', device),
  deleted: (deviceId: number | string) => storeEvents.emit('device:deleted', deviceId),
  lifecycleTransitioned: (data: { deviceId: number; fromState: string; toState: string }) => 
    storeEvents.emit('device:lifecycle:transitioned', data),
}

export const recipeEvents = {
  updated: (recipe: Recipe) => storeEvents.emit('recipe:updated', recipe),
  created: (recipe: Recipe) => storeEvents.emit('recipe:created', recipe),
  deleted: (recipeId: number) => storeEvents.emit('recipe:deleted', recipeId),
}
