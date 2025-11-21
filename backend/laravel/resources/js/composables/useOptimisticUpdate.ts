/**
 * Composable для управления оптимистичными обновлениями UI
 * Обновляет интерфейс сразу при действии пользователя, до получения ответа от сервера
 */

import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { logger } from '@/utils/logger'

interface OptimisticUpdateOptions<T> {
  /**
   * Функция для применения оптимистичного обновления
   */
  applyUpdate: () => void
  
  /**
   * Функция для отката изменений при ошибке
   */
  rollback: () => void
  
  /**
   * Функция для получения данных с сервера после успешной операции
   * Если не указана, состояние не синхронизируется с сервером
   */
  syncWithServer?: () => Promise<T>
  
  /**
   * Таймаут для отката изменений (в мс)
   * Если операция не завершилась за это время, изменения откатываются
   */
  timeout?: number
  
  /**
   * Показывать ли индикатор загрузки
   */
  showLoading?: boolean
  
  /**
   * Callback при успешной операции
   */
  onSuccess?: (data: T) => void
  
  /**
   * Callback при ошибке
   */
  onError?: (error: Error) => void
}

interface PendingUpdate {
  id: string
  applyUpdate: () => void
  rollback: () => void
  timeoutId: NodeJS.Timeout | null
  timestamp: number
}

/**
 * Composable для работы с оптимистичными обновлениями
 */
export function useOptimisticUpdate() {
  const pendingUpdates: Ref<Map<string, PendingUpdate>> = ref(new Map())
  const isUpdating: Ref<boolean> = ref(false)
  
  /**
   * Выполнить оптимистичное обновление
   */
  async function performUpdate<T>(
    updateId: string,
    options: OptimisticUpdateOptions<T>
  ): Promise<T> {
    const {
      applyUpdate,
      rollback,
      syncWithServer,
      timeout = 30000, // 30 секунд по умолчанию
      showLoading = true,
      onSuccess,
      onError,
    } = options
    
    // Сохраняем состояние для отката
    applyUpdate()
    
    if (showLoading) {
      isUpdating.value = true
    }
    
    // Создаем запись о pending обновлении
    let timeoutId: NodeJS.Timeout | null = null
    
    if (timeout > 0) {
      timeoutId = setTimeout(() => {
        logger.warn(`[useOptimisticUpdate] Update ${updateId} timed out, rolling back`)
        rollback()
        pendingUpdates.value.delete(updateId)
        if (showLoading) {
          isUpdating.value = false
        }
        if (onError) {
          onError(new Error('Update timeout'))
        }
      }, timeout)
    }
    
    const pendingUpdate: PendingUpdate = {
      id: updateId,
      applyUpdate,
      rollback,
      timeoutId,
      timestamp: Date.now(),
    }
    
    pendingUpdates.value.set(updateId, pendingUpdate)
    
    try {
      // Выполняем операцию на сервере
      let result: T
      
      if (syncWithServer) {
        result = await syncWithServer()
        
        // Если есть синхронизация, применяем данные с сервера
        // (но только если операция успешна)
        // Это можно сделать через applyUpdate с новыми данными
      } else {
        // Если нет синхронизации, считаем операцию успешной
        result = {} as T
      }
      
      // Очищаем timeout
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
      
      // Удаляем из pending
      pendingUpdates.value.delete(updateId)
      
      if (showLoading) {
        isUpdating.value = false
      }
      
      if (onSuccess) {
        onSuccess(result)
      }
      
      return result
    } catch (error) {
      // Ошибка - откатываем изменения
      logger.error(`[useOptimisticUpdate] Update ${updateId} failed, rolling back:`, error)
      
      // Очищаем timeout
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
      
      // Откатываем изменения
      rollback()
      
      // Удаляем из pending
      pendingUpdates.value.delete(updateId)
      
      if (showLoading) {
        isUpdating.value = false
      }
      
      const err = error instanceof Error ? error : new Error(String(error))
      
      if (onError) {
        onError(err)
      }
      
      throw err
    }
  }
  
  /**
   * Откатить все pending обновления
   */
  function rollbackAll(): void {
    for (const [id, update] of pendingUpdates.value.entries()) {
      logger.warn(`[useOptimisticUpdate] Rolling back update ${id}`)
      if (update.timeoutId) {
        clearTimeout(update.timeoutId)
      }
      update.rollback()
    }
    pendingUpdates.value.clear()
    isUpdating.value = false
  }
  
  /**
   * Откатить конкретное обновление
   */
  function rollbackUpdate(updateId: string): void {
    const update = pendingUpdates.value.get(updateId)
    if (update) {
      logger.warn(`[useOptimisticUpdate] Rolling back update ${updateId}`)
      if (update.timeoutId) {
        clearTimeout(update.timeoutId)
      }
      update.rollback()
      pendingUpdates.value.delete(updateId)
    }
  }
  
  /**
   * Проверить, есть ли pending обновления
   */
  function hasPendingUpdates(): boolean {
    return pendingUpdates.value.size > 0
  }
  
  /**
   * Получить список ID pending обновлений
   */
  function getPendingUpdateIds(): string[] {
    return Array.from(pendingUpdates.value.keys())
  }
  
  return {
    performUpdate,
    rollbackAll,
    rollbackUpdate,
    hasPendingUpdates,
    getPendingUpdateIds,
    isUpdating: ref(isUpdating.value),
    pendingUpdatesCount: ref(pendingUpdates.value.size),
  }
}

/**
 * Хелпер для создания оптимистичного обновления зоны
 */
export function createOptimisticZoneUpdate(
  zoneStore: any,
  zoneId: number,
  optimisticData: Partial<any>
): {
  applyUpdate: () => void
  rollback: () => void
} {
  // Сохраняем текущее состояние для отката
  const originalZone = zoneStore.zoneById(zoneId)
  const originalData = originalZone ? { ...originalZone } : null
  
  return {
    applyUpdate: () => {
      // Применяем оптимистичное обновление
      if (originalZone) {
        zoneStore.optimisticUpsert({ ...originalZone, ...optimisticData })
      }
    },
    rollback: () => {
      // Откатываем к исходному состоянию
      if (originalData) {
        zoneStore.rollbackOptimisticUpdate(zoneId, originalData)
      }
    },
  }
}

/**
 * Хелпер для создания оптимистичного обновления устройства
 */
export function createOptimisticDeviceUpdate(
  deviceStore: any,
  deviceId: number | string,
  optimisticData: Partial<any>
): {
  applyUpdate: () => void
  rollback: () => void
} {
  // Сохраняем текущее состояние для отката
  const originalDevice = deviceStore.deviceById(deviceId)
  const originalData = originalDevice ? { ...originalDevice } : null
  
  return {
    applyUpdate: () => {
      // Применяем оптимистичное обновление
      if (originalDevice) {
        deviceStore.optimisticUpsert({ ...originalDevice, ...optimisticData })
      }
    },
    rollback: () => {
      // Откатываем к исходному состоянию
      if (originalData) {
        const identifier = originalData.id || originalData.uid || deviceId
        deviceStore.rollbackOptimisticUpdate(identifier, originalData)
      }
    },
  }
}

/**
 * Хелпер для создания оптимистичного создания (для новых элементов)
 */
export function createOptimisticCreate<T extends { id?: number | string }>(
  store: any,
  optimisticItem: T,
  temporaryId: string | number
): {
  applyUpdate: () => void
  rollback: () => void
} {
  return {
    applyUpdate: () => {
      // Добавляем элемент с временным ID (используем optimisticUpsert если доступен)
      if (store.optimisticUpsert) {
        store.optimisticUpsert({ ...optimisticItem, id: temporaryId, _optimistic: true })
      } else {
        store.upsert({ ...optimisticItem, id: temporaryId, _optimistic: true })
      }
    },
    rollback: () => {
      // Удаляем элемент
      store.remove(temporaryId)
    },
  }
}

